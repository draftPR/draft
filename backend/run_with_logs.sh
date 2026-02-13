#!/bin/bash
# Run backend with full logging to file

LOG_FILE="ticket_generation_debug.log"

echo "Starting backend with logging to $LOG_FILE"
echo "Tail the log file with: tail -f $LOG_FILE"

# Set Python to unbuffered mode and run uvicorn with all logs
PYTHONUNBUFFERED=1 python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug 2>&1 | tee "$LOG_FILE"
