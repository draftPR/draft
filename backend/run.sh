#!/bin/bash
# Auto-restart wrapper for uvicorn backend
# Restarts automatically if the process dies unexpectedly

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv if present
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
fi

RESTART_DELAY=3

echo "Starting uvicorn with auto-restart (Ctrl+C to stop)..."

while true; do
    python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "uvicorn exited cleanly (code 0). Stopping."
        break
    fi
    
    echo "uvicorn exited with code $EXIT_CODE. Restarting in ${RESTART_DELAY}s..."
    sleep "$RESTART_DELAY"
done
