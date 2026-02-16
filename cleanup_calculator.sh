#!/bin/bash
set -e

# Cleanup script for calculator-project board
# This script removes all Alma Kanban data and resets code changes for the calculator project

BOARD_ID="ca149d15-91a6-4bce-9f88-d9ee2df4764d"
REPO_PATH="/Users/dor/Documents/code/tests/calculator-project"
BACKEND_URL="http://localhost:8000"

echo "=========================================="
echo "Calculator Board Cleanup Script"
echo "=========================================="
echo ""
echo "Board ID: $BOARD_ID"
echo "Repo Path: $REPO_PATH"
echo ""

# Check if backend is running
echo "[1/6] Checking backend status..."
if ! curl -s --max-time 2 "$BACKEND_URL/health" > /dev/null 2>&1; then
    echo "ERROR: Backend is not responding at $BACKEND_URL"
    echo "Please start the backend first: make dev-backend"
    exit 1
fi
echo "✓ Backend is running"
echo ""

# Get all goals for this board
echo "[2/6] Finding goals and tickets for calculator board..."
GOALS=$(curl -s "$BACKEND_URL/goals" | jq -r ".goals[]? | select(.board_id == \"$BOARD_ID\") | .id")

if [ -z "$GOALS" ]; then
    echo "No goals found for this board"
else
    GOAL_COUNT=$(echo "$GOALS" | wc -l | tr -d ' ')
    echo "Found $GOAL_COUNT goal(s)"

    # For each goal, get tickets and cancel running jobs
    for GOAL_ID in $GOALS; do
        echo ""
        echo "Processing goal: $GOAL_ID"

        # Get tickets for this goal
        TICKETS=$(curl -s "$BACKEND_URL/tickets" | jq -r ".tickets[]? | select(.goal_id == \"$GOAL_ID\") | .id")

        if [ ! -z "$TICKETS" ]; then
            TICKET_COUNT=$(echo "$TICKETS" | wc -l | tr -d ' ')
            echo "  Found $TICKET_COUNT ticket(s)"

            # Cancel running jobs for each ticket
            for TICKET_ID in $TICKETS; do
                JOBS=$(curl -s "$BACKEND_URL/jobs" | jq -r ".jobs[]? | select(.ticket_id == \"$TICKET_ID\" and (.status == \"running\" or .status == \"queued\")) | .id")

                if [ ! -z "$JOBS" ]; then
                    for JOB_ID in $JOBS; do
                        echo "  Canceling job: $JOB_ID"
                        curl -s -X POST "$BACKEND_URL/jobs/$JOB_ID/cancel" > /dev/null
                    done
                fi
            done
        fi

        # Delete the goal (cascades to tickets, jobs, etc.)
        echo "  Deleting goal: $GOAL_ID"
        curl -s -X DELETE "$BACKEND_URL/goals/$GOAL_ID" > /dev/null
    done
fi
echo ""

# Clean up worktrees
echo "[3/6] Cleaning up worktrees..."
if [ -d "$REPO_PATH/.smartkanban/worktrees" ]; then
    cd "$REPO_PATH"

    # List and remove all worktrees
    WORKTREES=$(git worktree list | grep "\.smartkanban/worktrees" | awk '{print $1}' || true)

    if [ ! -z "$WORKTREES" ]; then
        echo "$WORKTREES" | while read -r WORKTREE; do
            echo "  Removing worktree: $WORKTREE"
            git worktree remove --force "$WORKTREE" 2>/dev/null || true
        done

        # Prune stale worktree references
        git worktree prune
    else
        echo "  No worktrees found"
    fi

    # Remove worktree directory
    if [ -d ".smartkanban/worktrees" ]; then
        rm -rf .smartkanban/worktrees
        echo "  Removed .smartkanban/worktrees directory"
    fi
else
    echo "  No worktree directory found"
fi
echo ""

# Clean up branches
echo "[4/6] Cleaning up feature branches..."
cd "$REPO_PATH"
BRANCHES=$(git branch | grep "goal/" || true)

if [ ! -z "$BRANCHES" ]; then
    echo "$BRANCHES" | while read -r BRANCH; do
        BRANCH=$(echo "$BRANCH" | tr -d ' *')
        echo "  Deleting branch: $BRANCH"
        git branch -D "$BRANCH" 2>/dev/null || true
    done
else
    echo "  No feature branches found"
fi
echo ""

# Reset code changes
echo "[5/6] Resetting code changes in main repo..."
cd "$REPO_PATH"

# Show current status
echo "  Current git status:"
git status --short | head -10

# Ask for confirmation before resetting
echo ""
read -p "  Reset all changes to main branch? (y/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Stash any changes
    git stash push -m "cleanup_calculator_$(date +%Y%m%d_%H%M%S)" || true

    # Checkout main/master branch
    if git rev-parse --verify main >/dev/null 2>&1; then
        git checkout main
    elif git rev-parse --verify master >/dev/null 2>&1; then
        git checkout master
    fi

    # Reset to HEAD
    git reset --hard HEAD
    git clean -fd

    echo "  ✓ Code changes reset"
else
    echo "  Skipped code reset"
fi
echo ""

# Optional: Delete the board itself
echo "[6/6] Board cleanup..."
read -p "Delete the board entirely from Alma Kanban? (y/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "  Deleting board: $BOARD_ID"
    curl -s -X DELETE "$BACKEND_URL/boards/$BOARD_ID" > /dev/null
    echo "  ✓ Board deleted"
else
    echo "  Board kept (goals/tickets removed)"
fi
echo ""

echo "=========================================="
echo "Cleanup Complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - Goals and tickets deleted"
echo "  - Worktrees cleaned up"
echo "  - Feature branches removed"
echo "  - Code changes $([ $REPLY == 'y' ] || [ $REPLY == 'Y' ] && echo 'reset' || echo 'preserved')"
echo ""
echo "The calculator board is now clean."
