/**
 * Vite plugin that manages the backend server lifecycle.
 *
 * Exposes `GET /__api/wake-backend` — the frontend calls this when the
 * backend is unreachable.  The plugin checks if the backend is already
 * running, and if not, spawns `uvicorn` as a detached child process.
 *
 * Also runs a background health monitor that auto-restarts the backend
 * if it crashes (checked every 30 s).
 */

import { spawn, type ChildProcess } from "node:child_process";
import { createWriteStream } from "node:fs";
import { join } from "node:path";
import type { Plugin } from "vite";

const HEALTH_ENDPOINT = "http://localhost:8000/health";
const POLL_INTERVAL_MS = 500;
const STARTUP_TIMEOUT_MS = 15_000;
const HEALTH_CHECK_INTERVAL_MS = 30_000;

async function isBackendRunning(): Promise<boolean> {
  try {
    const res = await fetch(HEALTH_ENDPOINT, {
      signal: AbortSignal.timeout(2_000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

function waitForBackend(): Promise<boolean> {
  return new Promise((resolve) => {
    const deadline = Date.now() + STARTUP_TIMEOUT_MS;

    const check = async () => {
      if (Date.now() > deadline) {
        resolve(false);
        return;
      }
      if (await isBackendRunning()) {
        resolve(true);
        return;
      }
      setTimeout(check, POLL_INTERVAL_MS);
    };

    check();
  });
}

function spawnBackend(projectRoot: string): ChildProcess | null {
  try {
    const backendDir = join(projectRoot, "backend");
    const venvPython = join(backendDir, "venv", "bin", "python");
    const logFile = join(backendDir, "uvicorn.log");

    // Log to file so crashes are diagnosable (rotated on each spawn)
    const logStream = createWriteStream(logFile, { flags: "a" });

    const child = spawn(
      venvPython,
      ["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
      {
        cwd: backendDir,
        detached: true,
        stdio: ["ignore", logStream, logStream],
      },
    );
    child.unref();
    // Close our handle — the child keeps writing via its inherited fd
    logStream.close();
    return child;
  } catch {
    return null;
  }
}

export default function backendLauncher(): Plugin {
  let projectRoot = "";
  let healthCheckTimer: ReturnType<typeof setInterval> | undefined;
  // Track whether we've ever started the backend (don't auto-restart
  // a backend we didn't start — the user might be running it manually).
  let weStartedBackend = false;

  return {
    name: "backend-launcher",

    configResolved(config) {
      // Vite's root is frontend/ — project root is one level up
      projectRoot = join(config.root, "..");
    },

    configureServer(server) {
      // Start health monitor that auto-restarts the backend if it crashes
      healthCheckTimer = setInterval(async () => {
        if (!weStartedBackend) return;
        if (await isBackendRunning()) return;

        console.log("[backend-launcher] Backend is down, auto-restarting...");
        spawnBackend(projectRoot);
      }, HEALTH_CHECK_INTERVAL_MS);

      // Clean up on server close
      server.httpServer?.on("close", () => {
        if (healthCheckTimer) clearInterval(healthCheckTimer);
      });

      server.middlewares.use(async (req, res, next) => {
        if (req.url !== "/__api/wake-backend") {
          next();
          return;
        }

        // Already running?
        if (await isBackendRunning()) {
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ status: "already_running" }));
          return;
        }

        // Spawn the backend
        const child = spawnBackend(projectRoot);
        if (!child) {
          res.writeHead(500, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ status: "spawn_failed" }));
          return;
        }
        weStartedBackend = true;

        // Wait for it to come up
        const ok = await waitForBackend();

        if (ok) {
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ status: "started" }));
        } else {
          res.writeHead(503, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ status: "timeout" }));
        }
      });
    },
  };
}
