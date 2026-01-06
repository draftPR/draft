#!/usr/bin/env bash
# =============================================================================
# CANARY TESTS FOR SMART KANBAN EXECUTOR INTEGRATION
# =============================================================================
#
# Prerequisites:
#   1. Redis running: redis-server
#   2. Backend running: cd backend && source venv/bin/activate && uvicorn app.main:app --reload
#   3. Worker running: cd backend && source venv/bin/activate && celery -A app.worker worker --loglevel=info
#
# Usage:
#   ./canary_tests.sh [test_number]
#   ./canary_tests.sh        # Run all tests
#   ./canary_tests.sh 1      # Run only Canary 1
#   ./canary_tests.sh 4      # Run only Canary 4

set -e

API_BASE="${API_BASE:-http://localhost:8000}"
POLL_INTERVAL=2
MAX_POLLS=30

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "\n${GREEN}>>> $1${NC}"
}

# Create a goal and return its ID
create_goal() {
    local title="$1"
    local response=$(curl -s -X POST "$API_BASE/goals" \
        -H "Content-Type: application/json" \
        -d "{\"title\": \"$title\"}")
    echo "$response" | jq -r '.id'
}

# Create a ticket and return its ID
create_ticket() {
    local goal_id="$1"
    local title="$2"
    local description="${3:-}"
    local response=$(curl -s -X POST "$API_BASE/tickets" \
        -H "Content-Type: application/json" \
        -d "{\"goal_id\": \"$goal_id\", \"title\": \"$title\", \"description\": \"$description\"}")
    echo "$response" | jq -r '.id'
}

# Get ticket state
get_ticket_state() {
    local ticket_id="$1"
    curl -s "$API_BASE/tickets/$ticket_id" | jq -r '.state'
}

# Get ticket details
get_ticket() {
    local ticket_id="$1"
    curl -s "$API_BASE/tickets/$ticket_id"
}

# Run execute job
run_execute() {
    local ticket_id="$1"
    curl -s -X POST "$API_BASE/tickets/$ticket_id/run"
}

# Run verify job
run_verify() {
    local ticket_id="$1"
    curl -s -X POST "$API_BASE/tickets/$ticket_id/verify"
}

# Run resume (for interactive flow)
run_resume() {
    local ticket_id="$1"
    curl -s -X POST "$API_BASE/tickets/$ticket_id/resume"
}

# Get jobs for ticket
get_jobs() {
    local ticket_id="$1"
    curl -s "$API_BASE/tickets/$ticket_id/jobs"
}

# Get evidence for ticket
get_evidence() {
    local ticket_id="$1"
    curl -s "$API_BASE/tickets/$ticket_id/evidence"
}

# Wait for ticket to reach a state (or one of several states)
wait_for_state() {
    local ticket_id="$1"
    shift
    local expected_states=("$@")
    local polls=0

    log_info "Waiting for ticket to reach state: ${expected_states[*]}"

    while [ $polls -lt $MAX_POLLS ]; do
        local current_state=$(get_ticket_state "$ticket_id")
        
        for expected in "${expected_states[@]}"; do
            if [ "$current_state" = "$expected" ]; then
                log_info "Ticket reached state: $current_state"
                return 0
            fi
        done

        log_info "Current state: $current_state (poll $((polls + 1))/$MAX_POLLS)"
        sleep $POLL_INTERVAL
        ((polls++))
    done

    log_error "Timeout waiting for state. Current: $current_state, Expected: ${expected_states[*]}"
    return 1
}

# Verify evidence exists
verify_evidence() {
    local ticket_id="$1"
    local expected_kinds=("$@")
    
    local evidence=$(get_evidence "$ticket_id")
    local found_kinds=$(echo "$evidence" | jq -r '.evidence[].kind' | sort -u)
    
    log_info "Found evidence kinds: $found_kinds"
    
    for kind in "${expected_kinds[@]:1}"; do
        if ! echo "$found_kinds" | grep -q "$kind"; then
            log_warn "Missing evidence kind: $kind"
        fi
    done
}

# =============================================================================
# CANARY 1: Trivial Change (Claude Headless)
# =============================================================================
# Expected flow:
#   proposed → executing → verifying → needs_human (default on_success)
# Evidence:
#   executor_stdout, executor_meta, git_diff_stat, git_diff_patch,
#   verify_stdout, verify_meta
# =============================================================================
canary_1() {
    log_step "CANARY 1: Trivial Change (Claude Headless)"
    
    log_info "Creating goal..."
    local goal_id=$(create_goal "Canary Test Goal 1")
    log_info "Goal ID: $goal_id"
    
    log_info "Creating ticket..."
    local ticket_id=$(create_ticket "$goal_id" "Add a comment to README" "Add a comment at the top of README.md")
    log_info "Ticket ID: $ticket_id"
    
    log_info "Transitioning to executing state..."
    curl -s -X POST "$API_BASE/tickets/$ticket_id/transition" \
        -H "Content-Type: application/json" \
        -d '{"to_state": "executing", "actor_type": "human", "reason": "Starting canary test"}'
    
    log_info "Running execute job..."
    local execute_response=$(run_execute "$ticket_id")
    log_info "Execute job: $(echo "$execute_response" | jq -c '{id, status}')"
    
    # Wait for verification to complete (auto-triggered)
    # First wait for verifying, then wait for needs_human (or blocked if failure)
    wait_for_state "$ticket_id" "verifying" "blocked" "needs_human"
    
    local state=$(get_ticket_state "$ticket_id")
    if [ "$state" = "verifying" ]; then
        log_info "In verifying state, waiting for verification to complete..."
        wait_for_state "$ticket_id" "needs_human" "blocked" "done"
    fi
    
    # Check final state
    local final_state=$(get_ticket_state "$ticket_id")
    log_info "Final state: $final_state"
    
    # Verify evidence
    log_info "Checking evidence..."
    verify_evidence "$ticket_id" executor_meta executor_stdout git_diff_stat git_diff_patch verify_meta verify_stdout
    
    # Show evidence summary
    local evidence=$(get_evidence "$ticket_id")
    log_info "Evidence count: $(echo "$evidence" | jq '.total')"
    
    if [ "$final_state" = "needs_human" ] || [ "$final_state" = "done" ]; then
        log_info "✅ CANARY 1 PASSED: Ticket reached expected state ($final_state)"
    elif [ "$final_state" = "blocked" ]; then
        log_warn "⚠️  CANARY 1 PARTIAL: Ticket blocked (possibly no changes or executor failed)"
        log_info "Check job logs for details"
    else
        log_error "❌ CANARY 1 FAILED: Unexpected state ($final_state)"
        return 1
    fi
}

# =============================================================================
# CANARY 2: No-op (No Changes)
# =============================================================================
# Expected flow:
#   proposed → executing → blocked (reason: no changes)
# =============================================================================
canary_2() {
    log_step "CANARY 2: No-op (No Changes)"
    
    log_info "Creating goal..."
    local goal_id=$(create_goal "Canary Test Goal 2")
    log_info "Goal ID: $goal_id"
    
    log_info "Creating ticket..."
    local ticket_id=$(create_ticket "$goal_id" "Review code, no changes needed" "Just review the code structure, don't make any changes")
    log_info "Ticket ID: $ticket_id"
    
    log_info "Transitioning to executing state..."
    curl -s -X POST "$API_BASE/tickets/$ticket_id/transition" \
        -H "Content-Type: application/json" \
        -d '{"to_state": "executing", "actor_type": "human", "reason": "Starting canary test"}'
    
    log_info "Running execute job..."
    local execute_response=$(run_execute "$ticket_id")
    log_info "Execute job: $(echo "$execute_response" | jq -c '{id, status}')"
    
    # Wait for blocked state (no changes should result in blocked)
    wait_for_state "$ticket_id" "blocked" "verifying" "needs_human"
    
    # Check final state
    local final_state=$(get_ticket_state "$ticket_id")
    log_info "Final state: $final_state"
    
    # Get events to check reason
    local events=$(curl -s "$API_BASE/tickets/$ticket_id/events")
    local last_reason=$(echo "$events" | jq -r '.events[-1].reason')
    log_info "Last transition reason: $last_reason"
    
    if [ "$final_state" = "blocked" ]; then
        if echo "$last_reason" | grep -qi "no.*change"; then
            log_info "✅ CANARY 2 PASSED: Ticket blocked with 'no changes' reason"
        else
            log_warn "⚠️  CANARY 2 PARTIAL: Ticket blocked but reason unclear"
        fi
    else
        log_warn "⚠️  CANARY 2 UNEXPECTED: State is $final_state (expected blocked)"
    fi
}

# =============================================================================
# CANARY 3: YOLO Refusal
# =============================================================================
# Expected flow:
#   executing → needs_human (YOLO refused due to empty allowlist)
#
# NOTE: This test requires yolo_mode: true in smartkanban.yaml
#       with an empty yolo_allowlist
# =============================================================================
canary_3() {
    log_step "CANARY 3: YOLO Refusal (requires yolo_mode: true, empty allowlist)"
    
    log_warn "This test requires modifying smartkanban.yaml:"
    log_warn "  yolo_mode: true"
    log_warn "  yolo_allowlist: []"
    log_warn ""
    log_warn "If not configured, this test will behave like Canary 1."
    
    log_info "Creating goal..."
    local goal_id=$(create_goal "Canary Test Goal 3")
    log_info "Goal ID: $goal_id"
    
    log_info "Creating ticket..."
    local ticket_id=$(create_ticket "$goal_id" "Test YOLO refusal" "This should be refused if YOLO is enabled with empty allowlist")
    log_info "Ticket ID: $ticket_id"
    
    log_info "Transitioning to executing state..."
    curl -s -X POST "$API_BASE/tickets/$ticket_id/transition" \
        -H "Content-Type: application/json" \
        -d '{"to_state": "executing", "actor_type": "human", "reason": "Starting canary test"}'
    
    log_info "Running execute job..."
    local execute_response=$(run_execute "$ticket_id")
    log_info "Execute job: $(echo "$execute_response" | jq -c '{id, status}')"
    
    # Wait for needs_human (YOLO refused) or other states
    wait_for_state "$ticket_id" "needs_human" "verifying" "blocked"
    
    # Check final state
    local final_state=$(get_ticket_state "$ticket_id")
    log_info "Final state: $final_state"
    
    # Get events to check reason
    local events=$(curl -s "$API_BASE/tickets/$ticket_id/events")
    local last_reason=$(echo "$events" | jq -r '.events[-1].reason')
    log_info "Last transition reason: $last_reason"
    
    if [ "$final_state" = "needs_human" ]; then
        if echo "$last_reason" | grep -qi "yolo.*refused\|allowlist"; then
            log_info "✅ CANARY 3 PASSED: YOLO refused with proper reason"
        else
            log_warn "⚠️  CANARY 3 UNCERTAIN: needs_human but reason doesn't mention YOLO"
            log_info "Reason: $last_reason"
        fi
    else
        log_warn "⚠️  CANARY 3 NOTE: YOLO mode may not be enabled ($final_state)"
    fi
}

# =============================================================================
# CANARY 4: Cursor Interactive + Resume
# =============================================================================
# Expected flow:
#   executing → needs_human (interactive executor)
#   [human makes changes]
#   resume → verifying → needs_human (or blocked if no changes)
#
# NOTE: This test requires preferred_executor: "cursor" in smartkanban.yaml
#       OR cursor CLI must be the only available executor
# =============================================================================
canary_4() {
    log_step "CANARY 4: Cursor Interactive + Resume"
    
    log_warn "This test requires either:"
    log_warn "  1. preferred_executor: 'cursor' in smartkanban.yaml"
    log_warn "  2. OR: Only Cursor CLI available (no Claude CLI)"
    log_warn ""
    log_warn "If Claude is available and preferred, this test will behave like Canary 1."
    
    log_info "Creating goal..."
    local goal_id=$(create_goal "Canary Test Goal 4")
    log_info "Goal ID: $goal_id"
    
    log_info "Creating ticket..."
    local ticket_id=$(create_ticket "$goal_id" "Interactive change test" "This requires human interaction if using Cursor")
    log_info "Ticket ID: $ticket_id"
    
    log_info "Transitioning to executing state..."
    curl -s -X POST "$API_BASE/tickets/$ticket_id/transition" \
        -H "Content-Type: application/json" \
        -d '{"to_state": "executing", "actor_type": "human", "reason": "Starting canary test"}'
    
    log_info "Running execute job..."
    local execute_response=$(run_execute "$ticket_id")
    log_info "Execute job: $(echo "$execute_response" | jq -c '{id, status}')"
    
    # Wait for initial state
    wait_for_state "$ticket_id" "needs_human" "verifying" "blocked"
    
    local state_after_execute=$(get_ticket_state "$ticket_id")
    log_info "State after execute: $state_after_execute"
    
    if [ "$state_after_execute" = "needs_human" ]; then
        log_info "Ticket is in needs_human state (interactive mode)"
        
        # Get events to see why
        local events=$(curl -s "$API_BASE/tickets/$ticket_id/events")
        local last_reason=$(echo "$events" | jq -r '.events[-1].reason')
        
        if echo "$last_reason" | grep -qi "interactive\|cursor"; then
            log_info "Confirmed: Interactive executor (Cursor)"
            log_info ""
            log_info "=== MANUAL STEP REQUIRED ==="
            log_info "1. Make some changes in the worktree"
            log_info "2. Then call: curl -X POST $API_BASE/tickets/$ticket_id/resume"
            log_info "==========================="
            log_info ""
            
            # Ask if user wants to test resume
            read -p "Did you make changes? Run resume? (y/N): " do_resume
            
            if [ "$do_resume" = "y" ] || [ "$do_resume" = "Y" ]; then
                log_info "Running resume..."
                local resume_response=$(run_resume "$ticket_id")
                log_info "Resume job: $(echo "$resume_response" | jq -c '{id, status}')"
                
                # Wait for final state
                wait_for_state "$ticket_id" "verifying" "blocked" "needs_human"
                
                local state_after_resume=$(get_ticket_state "$ticket_id")
                if [ "$state_after_resume" = "verifying" ]; then
                    log_info "Resumed successfully, now in verifying"
                    wait_for_state "$ticket_id" "needs_human" "done" "blocked"
                fi
                
                local final_state=$(get_ticket_state "$ticket_id")
                log_info "Final state: $final_state"
                
                if [ "$final_state" = "needs_human" ] || [ "$final_state" = "done" ]; then
                    log_info "✅ CANARY 4 PASSED: Full interactive flow completed"
                elif [ "$final_state" = "blocked" ]; then
                    log_warn "⚠️  CANARY 4 PARTIAL: Blocked (possibly no changes in worktree)"
                fi
            else
                log_info "Skipping resume step"
                log_info "✅ CANARY 4 PARTIAL: Interactive detection worked"
            fi
        else
            log_warn "needs_human but not due to interactive executor"
            log_info "Reason: $last_reason"
        fi
    else
        log_warn "⚠️  CANARY 4 NOTE: Did not enter interactive mode"
        log_info "This means Claude (headless) executor was used"
    fi
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    echo "=============================================="
    echo "    SMART KANBAN CANARY TESTS"
    echo "=============================================="
    echo ""
    echo "API Base: $API_BASE"
    echo ""
    
    # Check if API is reachable
    if ! curl -s "$API_BASE/board" > /dev/null 2>&1; then
        log_error "Cannot reach API at $API_BASE"
        log_error "Make sure the backend is running"
        exit 1
    fi
    log_info "API is reachable"
    
    local test_num="${1:-all}"
    
    case "$test_num" in
        1) canary_1 ;;
        2) canary_2 ;;
        3) canary_3 ;;
        4) canary_4 ;;
        all)
            canary_1
            echo ""
            canary_2
            echo ""
            canary_3
            echo ""
            canary_4
            ;;
        *)
            log_error "Unknown test: $test_num"
            echo "Usage: $0 [1|2|3|4|all]"
            exit 1
            ;;
    esac
    
    echo ""
    echo "=============================================="
    echo "    CANARY TESTS COMPLETE"
    echo "=============================================="
}

main "$@"

