#!/bin/bash
# =============================================================================
# Smart Kanban - Clean Slate Script
# =============================================================================
# This script:
#   1. Deletes all existing boards (cascades to goals, tickets, jobs, workspaces)
#   2. Creates a new goal
#   3. Optionally generates tickets for the goal
#
# Usage:
#   ./scripts/clean_slate.sh                              # Interactive mode
#   ./scripts/clean_slate.sh "Goal title" "Goal description"     # With goal
#   ./scripts/clean_slate.sh --generate "Title" "Desc"    # Generate tickets
#   ./scripts/clean_slate.sh --yes --generate "Title" "Desc"  # Auto-accept all
#
# Requirements:
#   - Backend running at localhost:8000
#   - jq installed (for JSON parsing)
# =============================================================================

set -e

API_URL="${API_URL:-http://localhost:8000}"
GENERATE_TICKETS=false
AUTO_ACCEPT=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}ℹ ${NC}$1"; }
log_success() { echo -e "${GREEN}✓ ${NC}$1"; }
log_warn() { echo -e "${YELLOW}⚠ ${NC}$1"; }
log_error() { echo -e "${RED}✗ ${NC}$1"; }

# Check if jq is available
if ! command -v jq &> /dev/null; then
    log_error "jq is required but not installed. Install with: brew install jq"
    exit 1
fi

# Check if API is running
if ! curl -s "${API_URL}/health" > /dev/null 2>&1; then
    log_error "API not running at ${API_URL}. Start with: make dev-backend"
    exit 1
fi

log_success "Connected to API at ${API_URL}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --generate|-g)
            GENERATE_TICKETS=true
            shift
            ;;
        --yes|-y)
            AUTO_ACCEPT=true
            shift
            ;;
        *)
            break
            ;;
    esac
done

GOAL_TITLE="${1:-}"
GOAL_DESCRIPTION="${2:-}"

# =============================================================================
# Step 1: Nuclear reset - delete ALL data
# =============================================================================
echo ""
log_info "Performing nuclear reset - deleting ALL data..."

RESET_RESPONSE=$(curl -s -X POST "${API_URL}/debug/reset?confirm=yes-delete-everything")

# Check if reset was successful
if echo "$RESET_RESPONSE" | jq -e '.message' > /dev/null 2>&1; then
    TICKETS_DELETED=$(echo "$RESET_RESPONSE" | jq '.tickets_deleted')
    GOALS_DELETED=$(echo "$RESET_RESPONSE" | jq '.goals_deleted')
    JOBS_DELETED=$(echo "$RESET_RESPONSE" | jq '.jobs_deleted')
    
    log_success "Reset complete!"
    log_info "  Tickets deleted: ${TICKETS_DELETED}"
    log_info "  Goals deleted: ${GOALS_DELETED}"
    log_info "  Jobs deleted: ${JOBS_DELETED}"
else
    log_error "Reset failed:"
    echo "$RESET_RESPONSE" | jq .
    exit 1
fi

# =============================================================================
# Step 2: Get goal details
# =============================================================================
echo ""

if [ -z "$GOAL_TITLE" ]; then
    echo -e "${YELLOW}Enter your goal details:${NC}"
    read -p "Goal title: " GOAL_TITLE
    read -p "Goal description: " GOAL_DESCRIPTION
    
    if [ -z "$GOAL_TITLE" ]; then
        # Default example goal
        GOAL_TITLE="Add power function to calculator"
        GOAL_DESCRIPTION="Implement a power function (base^exponent) that handles positive and negative exponents, zero edge cases, and includes unit tests."
        log_info "Using default goal: ${GOAL_TITLE}"
    fi
fi

# =============================================================================
# Step 3: Create the goal
# =============================================================================
echo ""
log_info "Creating goal: ${GOAL_TITLE}"

GOAL_RESPONSE=$(curl -s -X POST "${API_URL}/goals" \
    -H "Content-Type: application/json" \
    -d "{
        \"title\": \"${GOAL_TITLE}\",
        \"description\": \"${GOAL_DESCRIPTION}\"
    }")

GOAL_ID=$(echo "$GOAL_RESPONSE" | jq -r '.id')

if [ "$GOAL_ID" == "null" ] || [ -z "$GOAL_ID" ]; then
    log_error "Failed to create goal"
    echo "$GOAL_RESPONSE" | jq .
    exit 1
fi

log_success "Created goal: ${GOAL_ID}"
echo ""
echo "$GOAL_RESPONSE" | jq .

# =============================================================================
# Step 4: Optionally generate tickets
# =============================================================================
if [ "$GENERATE_TICKETS" = true ]; then
    echo ""
    log_info "Generating tickets for goal..."
    log_warn "This may take 30-60 seconds (LLM call)"
    
    TICKETS_RESPONSE=$(curl -s -X POST "${API_URL}/goals/${GOAL_ID}/generate-tickets" \
        -H "Content-Type: application/json" \
        -d '{}')
    
    # Check if it's an error
    if echo "$TICKETS_RESPONSE" | jq -e '.detail' > /dev/null 2>&1; then
        log_error "Failed to generate tickets:"
        echo "$TICKETS_RESPONSE" | jq .
    else
        TICKET_COUNT=$(echo "$TICKETS_RESPONSE" | jq '.tickets | length')
        log_success "Generated ${TICKET_COUNT} proposed ticket(s)"
        echo ""
        echo "$TICKETS_RESPONSE" | jq '.tickets[] | {title, priority, priority_bucket}'
        
        # Prompt to accept tickets (skip if --yes)
        echo ""
        if [ "$AUTO_ACCEPT" = true ]; then
            ACCEPT="y"
        else
            read -p "Accept all proposed tickets? (y/N): " ACCEPT
        fi
        
        if [[ "$ACCEPT" =~ ^[Yy]$ ]]; then
            # Get ticket IDs
            TICKET_IDS_JSON=$(echo "$TICKETS_RESPONSE" | jq '[.tickets[].id]')
            
            log_info "Accepting ${TICKET_COUNT} tickets..."
            
            ACCEPT_RESPONSE=$(curl -s -X POST "${API_URL}/tickets/accept" \
                -H "Content-Type: application/json" \
                -d "{\"ticket_ids\": ${TICKET_IDS_JSON}}")
            
            ACCEPTED=$(echo "$ACCEPT_RESPONSE" | jq '.accepted_count')
            log_success "Accepted ${ACCEPTED} ticket(s) - now in 'planned' state"
        fi
    fi
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Clean Slate Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Goal ID: ${GOAL_ID}"
echo "Title:   ${GOAL_TITLE}"
echo ""
echo "Next steps:"
echo "  1. View board:            curl ${API_URL}/board | jq"
echo "  2. Generate tickets:      curl -X POST ${API_URL}/goals/${GOAL_ID}/generate-tickets"
echo "  3. Start planner:         curl -X POST ${API_URL}/planner/start"
echo "  4. Open UI:               http://localhost:5173"
echo ""

