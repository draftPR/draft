#!/usr/bin/env node

/**
 * alma-kanban CLI — one-command launcher for Alma Kanban.
 *
 * Usage:
 *   npx alma-kanban          # launch in current directory
 *   npx alma-kanban --port 9000
 *   npx alma-kanban --help
 */

const { execSync, spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");
const http = require("http");

// ── Config ──────────────────────────────────────────────────────────
const ALMA_HOME = path.join(os.homedir(), ".alma-kanban");
const VENV_DIR = path.join(ALMA_HOME, "venv");
const DEFAULT_PORT = 8000;

const PKG_ROOT = path.resolve(__dirname, "..");

/**
 * Resolve the application root containing backend/ and frontend/.
 * When installed via npm/npx, these live under npx-cli/app/.
 * In the monorepo (local dev), they're one level above npx-cli/.
 */
function resolveAppRoot() {
  // 1) Bundled app/ directory (npm published package)
  const bundled = path.join(PKG_ROOT, "app");
  if (
    fs.existsSync(path.join(bundled, "backend", "requirements.txt")) &&
    fs.existsSync(path.join(bundled, "frontend"))
  ) {
    return bundled;
  }

  // 2) Monorepo parent (local development: npx-cli sits beside backend/ frontend/)
  const mono = path.resolve(PKG_ROOT, "..");
  if (
    fs.existsSync(path.join(mono, "backend", "requirements.txt")) &&
    fs.existsSync(path.join(mono, "frontend", "package.json"))
  ) {
    return mono;
  }

  return null;
}

/**
 * Check if a pre-built frontend exists (production mode).
 */
function hasPrebuiltFrontend(appRoot) {
  return fs.existsSync(path.join(appRoot, "frontend", "dist", "index.html"));
}

// ── Helpers ─────────────────────────────────────────────────────────

function log(msg) {
  console.log(`\x1b[36m[alma]\x1b[0m ${msg}`);
}

function logError(msg) {
  console.error(`\x1b[31m[alma]\x1b[0m ${msg}`);
}

function logSuccess(msg) {
  console.log(`\x1b[32m[alma]\x1b[0m ${msg}`);
}

function commandExists(cmd) {
  try {
    execSync(`command -v ${cmd}`, { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

function getVersion(cmd) {
  try {
    return execSync(`${cmd} --version`, { encoding: "utf-8" }).trim();
  } catch {
    return null;
  }
}

function parseMajorVersion(versionStr) {
  const match = versionStr?.match(/(\d+)/);
  return match ? parseInt(match[1], 10) : 0;
}

/**
 * Wait for a local HTTP server to respond on /health.
 */
function waitForHealth(port, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const check = () => {
      const req = http.get(`http://localhost:${port}/health`, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else if (Date.now() - start > timeoutMs) {
          reject(new Error(`Backend did not become healthy within ${timeoutMs / 1000}s`));
        } else {
          setTimeout(check, 500);
        }
      });
      req.on("error", () => {
        if (Date.now() - start > timeoutMs) {
          reject(new Error(`Backend did not start within ${timeoutMs / 1000}s`));
        } else {
          setTimeout(check, 500);
        }
      });
      req.end();
    };
    check();
  });
}

// ── Prerequisite checks ─────────────────────────────────────────────

function checkPrerequisites(needsNode) {
  log("Checking prerequisites...");

  // Python 3.10+
  const pythonCmd = commandExists("python3") ? "python3" : commandExists("python") ? "python" : null;
  if (!pythonCmd) {
    logError("Python 3 not found. Install Python 3.10+ from https://www.python.org/");
    process.exit(1);
  }
  const pyVersion = getVersion(pythonCmd);
  const pyMajorMinor = pyVersion?.match(/(\d+)\.(\d+)/);
  if (pyMajorMinor) {
    const major = parseInt(pyMajorMinor[1]);
    const minor = parseInt(pyMajorMinor[2]);
    if (major < 3 || (major === 3 && minor < 10)) {
      logError(`Python 3.10+ required, found ${pyVersion}`);
      process.exit(1);
    }
  }
  log(`  Python: ${pyVersion}`);

  // Node 18+ (only required if running in dev mode)
  if (needsNode) {
    const nodeVersion = getVersion("node");
    if (parseMajorVersion(nodeVersion) < 18) {
      logError(`Node.js 18+ required, found ${nodeVersion}`);
      process.exit(1);
    }
    log(`  Node.js: ${nodeVersion}`);
  }

  // Git
  if (!commandExists("git")) {
    logError("Git not found. Install git from https://git-scm.com/");
    process.exit(1);
  }
  log(`  Git: ${getVersion("git")?.split("\n")[0]}`);

  return pythonCmd;
}

// ── Setup ───────────────────────────────────────────────────────────

function ensureVenv(pythonCmd) {
  if (fs.existsSync(path.join(VENV_DIR, "bin", "python"))) {
    return; // Already exists
  }

  log("Creating Python virtual environment...");
  fs.mkdirSync(ALMA_HOME, { recursive: true });
  execSync(`${pythonCmd} -m venv "${VENV_DIR}"`, { stdio: "inherit" });
}

function installBackendDeps(appRoot) {
  const reqFile = path.join(appRoot, "backend", "requirements.txt");
  if (!fs.existsSync(reqFile)) {
    logError(`requirements.txt not found at ${reqFile}`);
    process.exit(1);
  }

  const pip = path.join(VENV_DIR, "bin", "pip");
  log("Installing backend dependencies...");
  try {
    execSync(`"${pip}" install -q -r "${reqFile}"`, { stdio: "inherit" });
  } catch (e) {
    logError(`Failed to install backend dependencies: ${e.message}`);
    process.exit(1);
  }
}

function installFrontendDeps(appRoot) {
  const pkgJson = path.join(appRoot, "frontend", "package.json");
  const nodeModules = path.join(appRoot, "frontend", "node_modules");

  if (!fs.existsSync(pkgJson)) {
    logError(`frontend/package.json not found at ${pkgJson}`);
    process.exit(1);
  }

  if (fs.existsSync(nodeModules)) {
    return; // Already installed
  }

  log("Installing frontend dependencies...");
  try {
    execSync("npm install --legacy-peer-deps", {
      cwd: path.join(appRoot, "frontend"),
      stdio: "inherit",
    });
  } catch (e) {
    logError(`Failed to install frontend dependencies: ${e.message}`);
    process.exit(1);
  }
}

function runMigrations(appRoot) {
  const alembicCfg = path.join(appRoot, "backend", "alembic.ini");
  if (!fs.existsSync(alembicCfg)) {
    return; // No migrations to run
  }

  const python = path.join(VENV_DIR, "bin", "python");
  log("Running database migrations...");
  try {
    execSync(`"${python}" -m alembic upgrade head`, {
      cwd: path.join(appRoot, "backend"),
      stdio: "inherit",
    });
  } catch {
    log("  (migrations skipped — may already be up to date)");
  }
}

/**
 * Symlink smartkanban.yaml into the user's CWD if it doesn't exist.
 * This lets ConfigService find it from the repo root.
 */
function ensureConfig(appRoot) {
  const userConfig = path.join(process.cwd(), "smartkanban.yaml");
  const bundledConfig = path.join(appRoot, "smartkanban.yaml");

  // User already has a config — use theirs
  if (fs.existsSync(userConfig)) {
    return;
  }

  // Copy bundled default config to CWD so ConfigService finds it
  if (fs.existsSync(bundledConfig)) {
    fs.copyFileSync(bundledConfig, userConfig);
    log("Created default smartkanban.yaml in current directory");
  }
}

// ── Run ─────────────────────────────────────────────────────────────

function startProductionMode(appRoot, port) {
  const python = path.join(VENV_DIR, "bin", "python");
  const backendDir = path.join(appRoot, "backend");

  // Symlink frontend/dist into backend so FastAPI can serve it
  const backendFrontendDir = path.join(backendDir, "frontend");
  const backendFrontendDist = path.join(backendFrontendDir, "dist");
  const sourceDist = path.join(appRoot, "frontend", "dist");

  // Ensure a clean symlink — remove stale directory/symlink if present
  try {
    const stat = fs.lstatSync(backendFrontendDist);
    if (stat.isSymbolicLink() || stat.isDirectory()) {
      fs.rmSync(backendFrontendDist, { recursive: true });
    }
  } catch {
    // Path doesn't exist, which is fine
  }
  fs.mkdirSync(backendFrontendDir, { recursive: true });
  fs.symlinkSync(sourceDist, backendFrontendDist);

  logSuccess("Starting Alma Kanban (production mode — single process)");
  logSuccess(`  App:      http://localhost:${port}`);
  logSuccess(`  API Docs: http://localhost:${port}/docs`);
  console.log("");

  const backend = spawn(
    python,
    ["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", String(port)],
    {
      cwd: backendDir,
      stdio: "inherit",
      env: {
        ...process.env,
        VIRTUAL_ENV: VENV_DIR,
        PATH: `${VENV_DIR}/bin:${process.env.PATH}`,
        PORT: String(port),
      },
    }
  );

  // Open browser after backend is healthy
  waitForHealth(port, 30000)
    .then(() => {
      try {
        const url = `http://localhost:${port}`;
        const platform = process.platform;
        if (platform === "darwin") execSync(`open "${url}"`, { stdio: "ignore" });
        else if (platform === "linux") execSync(`xdg-open "${url}"`, { stdio: "ignore" });
        else if (platform === "win32") execSync(`start "${url}"`, { stdio: "ignore" });
      } catch {
        // Browser open failed silently
      }
    })
    .catch((err) => {
      logError(err.message);
    });

  // Graceful shutdown
  const cleanup = () => {
    log("Shutting down...");
    backend.kill("SIGTERM");
    process.exit(0);
  };

  process.on("SIGINT", cleanup);
  process.on("SIGTERM", cleanup);

  backend.on("exit", (code) => {
    if (code !== 0 && code !== null) logError(`Backend exited with code ${code}`);
    process.exit(code || 0);
  });
}

function startDevMode(appRoot, backendPort, frontendPort) {
  const python = path.join(VENV_DIR, "bin", "python");
  const backendDir = path.join(appRoot, "backend");
  const frontendDir = path.join(appRoot, "frontend");

  logSuccess("Starting Alma Kanban (development mode — two processes)");
  logSuccess(`  Backend:  http://localhost:${backendPort}`);
  logSuccess(`  Frontend: http://localhost:${frontendPort}`);
  logSuccess(`  API Docs: http://localhost:${backendPort}/docs`);
  console.log("");

  const backend = spawn(
    python,
    ["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", String(backendPort), "--reload"],
    {
      cwd: backendDir,
      stdio: "inherit",
      env: {
        ...process.env,
        VIRTUAL_ENV: VENV_DIR,
        PATH: `${VENV_DIR}/bin:${process.env.PATH}`,
      },
    }
  );

  const frontend = spawn("npx", ["vite", "--host", "--port", String(frontendPort)], {
    cwd: frontendDir,
    stdio: "inherit",
  });

  // Open browser after a short delay
  setTimeout(() => {
    try {
      const url = `http://localhost:${frontendPort}`;
      const platform = process.platform;
      if (platform === "darwin") execSync(`open "${url}"`, { stdio: "ignore" });
      else if (platform === "linux") execSync(`xdg-open "${url}"`, { stdio: "ignore" });
      else if (platform === "win32") execSync(`start "${url}"`, { stdio: "ignore" });
    } catch {
      // Browser open failed silently
    }
  }, 3000);

  // Graceful shutdown
  const cleanup = () => {
    log("Shutting down...");
    backend.kill("SIGTERM");
    frontend.kill("SIGTERM");
    process.exit(0);
  };

  process.on("SIGINT", cleanup);
  process.on("SIGTERM", cleanup);

  backend.on("exit", (code) => {
    if (code !== 0 && code !== null) logError(`Backend exited with code ${code}`);
    frontend.kill("SIGTERM");
  });

  frontend.on("exit", (code) => {
    if (code !== 0 && code !== null) logError(`Frontend exited with code ${code}`);
    backend.kill("SIGTERM");
  });
}

// ── CLI ─────────────────────────────────────────────────────────────

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    port: DEFAULT_PORT,
    frontendPort: 5173,
    help: false,
    version: false,
    skipSetup: false,
    dev: false,
  };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case "--help":
      case "-h":
        opts.help = true;
        break;
      case "--version":
      case "-v":
        opts.version = true;
        break;
      case "--port":
      case "-p":
        opts.port = parseInt(args[++i], 10) || DEFAULT_PORT;
        break;
      case "--frontend-port":
        opts.frontendPort = parseInt(args[++i], 10) || 5173;
        break;
      case "--skip-setup":
        opts.skipSetup = true;
        break;
      case "--dev":
        opts.dev = true;
        break;
    }
  }

  return opts;
}

function showHelp() {
  console.log(`
\x1b[1mAlma Kanban\x1b[0m — AI-powered local-first kanban board

\x1b[1mUsage:\x1b[0m
  npx alma-kanban [options]

\x1b[1mOptions:\x1b[0m
  -p, --port <port>          Server port (default: 8000)
  --frontend-port <port>     Frontend dev port, only in --dev mode (default: 5173)
  --skip-setup               Skip dependency installation
  --dev                      Force development mode (vite + uvicorn --reload)
  -v, --version              Show version
  -h, --help                 Show this help message

\x1b[1mPrerequisites:\x1b[0m
  - Python 3.10+
  - Git

\x1b[1mAI Agents (optional):\x1b[0m
  - Claude Code CLI (claude): https://docs.anthropic.com/en/docs/claude-code
  - Cursor Agent CLI: https://www.cursor.com/
  - Any supported executor configured in smartkanban.yaml
`);
}

// ── Main ────────────────────────────────────────────────────────────

function main() {
  const opts = parseArgs();

  if (opts.version) {
    const pkg = require(path.join(PKG_ROOT, "package.json"));
    console.log(`alma-kanban v${pkg.version}`);
    process.exit(0);
  }

  if (opts.help) {
    showHelp();
    process.exit(0);
  }

  const pkg = require(path.join(PKG_ROOT, "package.json"));

  console.log("");
  console.log("  \x1b[1m\x1b[36m╔═══════════════════════════════════╗\x1b[0m");
  console.log(`  \x1b[1m\x1b[36m║      Alma Kanban v${pkg.version.padEnd(15)}║\x1b[0m`);
  console.log("  \x1b[1m\x1b[36m║   AI-Powered Local Kanban Board   ║\x1b[0m");
  console.log("  \x1b[1m\x1b[36m╚═══════════════════════════════════╝\x1b[0m");
  console.log("");

  const appRoot = resolveAppRoot();
  if (!appRoot) {
    logError("Could not find backend/ and frontend/ directories.");
    logError("If installed via npm, the package may be incomplete.");
    logError("Try reinstalling: npm install -g alma-kanban");
    process.exit(1);
  }
  log(`App root: ${appRoot}`);

  const isProduction = hasPrebuiltFrontend(appRoot) && !opts.dev;
  log(`Mode: ${isProduction ? "production" : "development"}`);

  const pythonCmd = checkPrerequisites(!isProduction);

  if (!opts.skipSetup) {
    ensureVenv(pythonCmd);
    installBackendDeps(appRoot);
    if (!isProduction) {
      installFrontendDeps(appRoot);
    }
    runMigrations(appRoot);
    ensureConfig(appRoot);
  }

  logSuccess("Setup complete!");
  console.log("");

  if (isProduction) {
    startProductionMode(appRoot, opts.port);
  } else {
    startDevMode(appRoot, opts.port, opts.frontendPort);
  }
}

main();
