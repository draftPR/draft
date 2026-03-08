#!/usr/bin/env node

/**
 * Draft launcher for npx distribution.
 *
 * Usage:
 *   npx telem          # Start with default settings
 *   npx telem --port 9000  # Custom port
 */

const { execSync, spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const ROOT = path.resolve(__dirname, "..");

function checkPython() {
  try {
    const version = execSync("python3 --version", { encoding: "utf-8" }).trim();
    const match = version.match(/Python (\d+)\.(\d+)/);
    if (match) {
      const major = parseInt(match[1]);
      const minor = parseInt(match[2]);
      if (major >= 3 && minor >= 10) {
        return "python3";
      }
    }
  } catch {
    // python3 not found
  }

  try {
    const version = execSync("python --version", { encoding: "utf-8" }).trim();
    const match = version.match(/Python (\d+)\.(\d+)/);
    if (match && parseInt(match[1]) >= 3 && parseInt(match[2]) >= 10) {
      return "python";
    }
  } catch {
    // python not found
  }

  console.error("Error: Python 3.10+ is required but not found.");
  console.error("Install Python from https://python.org or via your package manager.");
  process.exit(1);
}

function main() {
  const python = checkPython();

  // Check if backend venv exists
  const venvDir = path.join(ROOT, "backend", "venv");
  if (!fs.existsSync(venvDir)) {
    console.log("First run: installing backend dependencies...");
    execSync(`cd "${path.join(ROOT, "backend")}" && ${python} -m venv venv`, {
      stdio: "inherit",
    });
    execSync(
      `cd "${path.join(ROOT, "backend")}" && . venv/bin/activate && pip install -r requirements.txt`,
      { stdio: "inherit", shell: true }
    );
    console.log("Backend dependencies installed.");
  }

  // Run the launcher
  const launcher = path.join(ROOT, "run.py");
  const child = spawn(python, [launcher, ...process.argv.slice(2)], {
    cwd: ROOT,
    stdio: "inherit",
    env: {
      ...process.env,
      TASK_BACKEND: process.env.TASK_BACKEND || "sqlite",
    },
  });

  child.on("close", (code) => process.exit(code));
  child.on("error", (err) => {
    console.error(`Failed to start: ${err.message}`);
    process.exit(1);
  });

  // Forward signals
  process.on("SIGINT", () => child.kill("SIGINT"));
  process.on("SIGTERM", () => child.kill("SIGTERM"));
}

main();
