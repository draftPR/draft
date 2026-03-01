#!/usr/bin/env python3
"""
Alma Kanban Unified Launcher
Starts Backend + Frontend with a single command.
"""

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

# ANSI color codes for pretty output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Get project root
PROJECT_ROOT = Path(__file__).parent.resolve()
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
VENV_DIR = BACKEND_DIR / "venv"

# Ports
BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")
FRONTEND_PORT = os.getenv("FRONTEND_PORT", "5173")


class ProcessManager:
    """Manages multiple subprocesses with proper cleanup."""

    def __init__(self):
        self.processes: List[subprocess.Popen] = []
        self.shutting_down = False
        self.setup_signal_handlers()

    def setup_signal_handlers(self):
        """Setup handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

    def start_process(self, name: str, cmd: List[str], cwd: Optional[Path] = None,
                     env: Optional[dict] = None, color: str = Colors.OKBLUE) -> subprocess.Popen:
        """Start a subprocess and track it."""
        print(f"{color}{Colors.BOLD}[{name}]{Colors.ENDC} Starting...")

        try:
            # Merge environment variables
            process_env = os.environ.copy()
            if env:
                process_env.update(env)

            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=process_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )

            # Drain stdout in a background thread to prevent pipe buffer
            # from filling up and blocking the subprocess.
            prefix = f"{color}{Colors.BOLD}[{name}]{Colors.ENDC} "
            def _drain(proc: subprocess.Popen, pfx: str):
                try:
                    for line in proc.stdout:
                        print(f"{pfx}{line}", end="", flush=True)
                except (ValueError, OSError):
                    pass  # pipe closed during shutdown

            t = threading.Thread(target=_drain, args=(process, prefix), daemon=True)
            t.start()

            self.processes.append(process)
            print(f"{color}{Colors.BOLD}[{name}]{Colors.ENDC} Started (PID: {process.pid})")
            return process

        except Exception as e:
            print(f"{Colors.FAIL}{Colors.BOLD}[{name}]{Colors.ENDC} Failed to start: {e}")
            sys.exit(1)

    def shutdown(self, signum=None, frame=None):
        """Gracefully shutdown all processes."""
        # Prevent re-entrant calls
        if self.shutting_down:
            return

        self.shutting_down = True

        # Ignore further signals during shutdown
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

        print(f"\n{Colors.WARNING}{Colors.BOLD}[Shutdown]{Colors.ENDC} Stopping all services...")

        for process in reversed(self.processes):
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"{Colors.WARNING}  Process {process.pid} not responding, force killing...{Colors.ENDC}")
                process.kill()
                process.wait()

        print(f"{Colors.OKGREEN}{Colors.BOLD}[Shutdown]{Colors.ENDC} All services stopped")
        sys.exit(0)

    def wait_for_all(self):
        """Wait for all processes (blocks until shutdown signal)."""
        try:
            while True:
                # Check if any process died
                for process in self.processes:
                    if process.poll() is not None:
                        print(f"{Colors.FAIL}{Colors.BOLD}[Error]{Colors.ENDC} "
                              f"Process {process.pid} exited unexpectedly")
                        self.shutdown()

                time.sleep(1)

        except KeyboardInterrupt:
            self.shutdown()


def check_prerequisites():
    """Check if all required tools are installed."""
    print(f"{Colors.HEADER}{Colors.BOLD}=== Alma Kanban Launcher ==={Colors.ENDC}\n")

    checks = []

    # Check Python
    if sys.version_info < (3, 11):
        print(f"{Colors.FAIL}✗ Python 3.11+ required (found {sys.version_info.major}.{sys.version_info.minor}){Colors.ENDC}")
        checks.append(False)
    else:
        print(f"{Colors.OKGREEN}✓ Python {sys.version_info.major}.{sys.version_info.minor}{Colors.ENDC}")
        checks.append(True)

    # Check Node.js
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        node_version = result.stdout.strip()
        print(f"{Colors.OKGREEN}✓ Node.js {node_version}{Colors.ENDC}")
        checks.append(True)
    except FileNotFoundError:
        print(f"{Colors.FAIL}✗ Node.js not found (required for frontend){Colors.ENDC}")
        checks.append(False)

    # Check virtual environment
    if not VENV_DIR.exists():
        print(f"{Colors.FAIL}✗ Virtual environment not found at {VENV_DIR}{Colors.ENDC}")
        print(f"{Colors.WARNING}  Run: make setup{Colors.ENDC}")
        checks.append(False)
    else:
        print(f"{Colors.OKGREEN}✓ Virtual environment found{Colors.ENDC}")
        checks.append(True)

    # Check frontend node_modules
    if not (FRONTEND_DIR / "node_modules").exists():
        print(f"{Colors.FAIL}✗ Frontend dependencies not installed{Colors.ENDC}")
        print(f"{Colors.WARNING}  Run: cd frontend && npm install{Colors.ENDC}")
        checks.append(False)
    else:
        print(f"{Colors.OKGREEN}✓ Frontend dependencies installed{Colors.ENDC}")
        checks.append(True)

    print()  # Empty line

    if not all(checks):
        print(f"{Colors.FAIL}{Colors.BOLD}Prerequisites check failed{Colors.ENDC}")
        print(f"\nRun these commands to set up:")
        print(f"  {Colors.OKCYAN}make setup{Colors.ENDC}    # Install all dependencies")
        sys.exit(1)

    print(f"{Colors.OKGREEN}{Colors.BOLD}✓ All prerequisites met{Colors.ENDC}\n")


def start_backend(pm: ProcessManager):
    """Start FastAPI backend server."""
    python_path = VENV_DIR / "bin" / "python"

    pm.start_process(
        "Backend",
        [str(python_path), "-m", "uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", BACKEND_PORT, "--reload"],
        cwd=BACKEND_DIR,
        color=Colors.OKBLUE
    )


def start_frontend(pm: ProcessManager):
    """Start Vite frontend dev server."""
    pm.start_process(
        "Frontend",
        ["npm", "run", "dev", "--", "--port", FRONTEND_PORT, "--host"],
        cwd=FRONTEND_DIR,
        env={"VITE_BACKEND_URL": f"http://localhost:{BACKEND_PORT}"},
        color=Colors.HEADER
    )


def print_status():
    """Print service URLs and status."""
    print(f"\n{Colors.OKGREEN}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.OKGREEN}{Colors.BOLD}  Alma Kanban is running!{Colors.ENDC}")
    print(f"{Colors.OKGREEN}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")

    print(f"  {Colors.BOLD}Frontend:{Colors.ENDC}  {Colors.OKCYAN}http://localhost:{FRONTEND_PORT}{Colors.ENDC}")
    print(f"  {Colors.BOLD}Backend:{Colors.ENDC}   {Colors.OKCYAN}http://localhost:{BACKEND_PORT}{Colors.ENDC}")
    print(f"  {Colors.BOLD}API Docs:{Colors.ENDC}  {Colors.OKCYAN}http://localhost:{BACKEND_PORT}/docs{Colors.ENDC}")
    print(f"  {Colors.BOLD}Health:{Colors.ENDC}    {Colors.OKCYAN}http://localhost:{BACKEND_PORT}/health{Colors.ENDC}")

    print(f"\n{Colors.WARNING}Press Ctrl+C to stop all services{Colors.ENDC}\n")


def main():
    """Main entry point."""
    # Check prerequisites
    check_prerequisites()

    # Create process manager
    pm = ProcessManager()

    try:
        # Start services
        print(f"{Colors.HEADER}{Colors.BOLD}Starting services...{Colors.ENDC}\n")

        start_backend(pm)
        time.sleep(3)  # Wait for backend to be ready

        start_frontend(pm)
        time.sleep(2)

        # Print status
        print_status()

        # Wait for shutdown signal
        pm.wait_for_all()

    except Exception as e:
        print(f"{Colors.FAIL}{Colors.BOLD}[Error]{Colors.ENDC} {e}")
        pm.shutdown()


if __name__ == "__main__":
    main()
