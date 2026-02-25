/**
 * Vite plugin that can start the backend server on demand.
 *
 * Exposes `GET /__api/wake-backend` — the frontend calls this when the
 * backend is unreachable.  The plugin checks if the backend is already
 * running, and if not, spawns `uvicorn` as a detached child process.
 */

import { spawn } from "node:child_process";
import { join } from "node:path";
import type { Plugin } from "vite";

const HEALTH_ENDPOINT = "http://localhost:8000/health";
const POLL_INTERVAL_MS = 500;
const STARTUP_TIMEOUT_MS = 15_000;

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

export default function backendLauncher(): Plugin {
  let projectRoot = "";

  return {
    name: "backend-launcher",

    configResolved(config) {
      // Vite's root is frontend/ — project root is one level up
      projectRoot = join(config.root, "..");
    },

    configureServer(server) {
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
        try {
          const backendDir = join(projectRoot, "backend");
          const venvPython = join(backendDir, "venv", "bin", "python");

          const child = spawn(
            venvPython,
            ["-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
            {
              cwd: backendDir,
              detached: true,
              stdio: "ignore",
            },
          );
          child.unref();
        } catch (err) {
          res.writeHead(500, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ status: "spawn_failed", error: String(err) }));
          return;
        }

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
