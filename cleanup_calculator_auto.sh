#!/bin/bash
set -e

# Non-interactive cleanup script for calculator-project board
# Automatically resets everything without prompts

BOARD_ID="ca149d15-91a6-4bce-9f88-d9ee2df4764d"
REPO_PATH="/Users/dor/Documents/code/tests/calculator-project"
BACKEND_URL="http://localhost:8000"
DELETE_BOARD="${1:-no}"  # Pass "delete-board" as first arg to remove board

echo "=========================================="
echo "Calculator Board Auto-Cleanup"
echo "=========================================="
echo ""

# Check backend
echo "Checking backend..."
if ! curl -s --max-time 2 "$BACKEND_URL/health" > /dev/null 2>&1; then
    echo "ERROR: Backend not responding at $BACKEND_URL"
    exit 1
fi
echo "✓ Backend is running"
echo ""

# Get and delete all goals (this cascades to tickets, jobs, etc.)
echo "Deleting goals and tickets..."
GOALS=$(curl -s "$BACKEND_URL/goals" | jq -r ".goals[]? | select(.board_id == \"$BOARD_ID\") | .id")

if [ -z "$GOALS" ]; then
    echo "  No goals found for this board"
else
    GOAL_COUNT=$(echo "$GOALS" | wc -l | tr -d ' ')
    echo "  Found $GOAL_COUNT goal(s) to delete"

    for GOAL_ID in $GOALS; do
        echo "  Deleting goal: $GOAL_ID"
        curl -s -X DELETE "$BACKEND_URL/goals/$GOAL_ID" > /dev/null 2>&1 || echo "    Warning: Failed to delete goal $GOAL_ID"
    done
fi
echo ""

# Clean worktrees
echo "Cleaning worktrees..."
if [ -d "$REPO_PATH/.smartkanban/worktrees" ]; then
    cd "$REPO_PATH"

    # List and remove all worktrees
    WORKTREE_COUNT=0
    git worktree list | grep "\.smartkanban/worktrees" | awk '{print $1}' | while read -r WORKTREE; do
        echo "  Removing: $WORKTREE"
        git worktree remove --force "$WORKTREE" 2>/dev/null || true
        WORKTREE_COUNT=$((WORKTREE_COUNT + 1))
    done

    # Prune stale references
    git worktree prune

    # Remove directory
    if [ -d ".smartkanban/worktrees" ]; then
        rm -rf .smartkanban/worktrees
        echo "  ✓ Removed worktrees directory"
    fi
else
    echo "  No worktree directory found"
fi
echo ""

# Clean branches
echo "Cleaning branches..."
cd "$REPO_PATH"
BRANCH_COUNT=0
git branch | grep "goal/" | tr -d ' *' | while read -r BRANCH; do
    echo "  Deleting: $BRANCH"
    git branch -D "$BRANCH" 2>/dev/null || true
    BRANCH_COUNT=$((BRANCH_COUNT + 1))
done

if [ $BRANCH_COUNT -eq 0 ]; then
    echo "  No feature branches found"
fi
echo ""

# Reset code
echo "Resetting code changes..."
cd "$REPO_PATH"

# Stash any uncommitted changes
if ! git diff-index --quiet HEAD 2>/dev/null; then
    STASH_NAME="auto_cleanup_$(date +%Y%m%d_%H%M%S)"
    git stash push -m "$STASH_NAME" 2>/dev/null && echo "  ✓ Changes stashed as: $STASH_NAME" || true
fi

# Checkout and reset to main/master
if git rev-parse --verify main >/dev/null 2>&1; then
    git checkout main 2>/dev/null || true
    MAIN_BRANCH="main"
elif git rev-parse --verify master >/dev/null 2>&1; then
    git checkout master 2>/dev/null || true
    MAIN_BRANCH="master"
fi

git reset --hard HEAD 2>/dev/null || true
git clean -fd 2>/dev/null || true
echo "  ✓ Reset to $MAIN_BRANCH branch"
echo ""

# Delete board if requested
if [ "$DELETE_BOARD" = "delete-board" ]; then
    echo "Deleting board..."
    curl -s -X DELETE "$BACKEND_URL/boards/$BOARD_ID" > /dev/null 2>&1 && echo "  ✓ Board deleted" || echo "  Warning: Failed to delete board"
    echo ""
fi

echo "=========================================="
echo "✓ Cleanup Complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - Goals and tickets: Deleted"
echo "  - Worktrees: Cleaned"
echo "  - Feature branches: Removed"
echo "  - Code changes: Reset to $MAIN_BRANCH"
if [ "$DELETE_BOARD" = "delete-board" ]; then
    echo "  - Board: Deleted"
else
    echo "  - Board: Kept (use 'delete-board' arg to remove)"
fi
echo ""
echo "Usage:"
echo "  ./cleanup_calculator_auto.sh              # Keep board"
echo "  ./cleanup_calculator_auto.sh delete-board # Remove board"
