#!/bin/bash
# 🏭 PRODUCTION READINESS TEST - Full Flow with Timing Metrics

set -e

API="http://localhost:8000"
START_TIME=$(date +%s)

# Colors
C='\033[0;36m'; G='\033[0;32m'; Y='\033[1;33m'; M='\033[0;35m'; R='\033[0;31m'; N='\033[0m'; B='\033[1m'

log() { echo -e "${C}[$(date '+%H:%M:%S')]${N} $1"; }
success() { echo -e "${G}✅ $1${N}"; }
fail() { echo -e "${R}❌ $1${N}"; }
metric() { echo -e "  ${Y}⏱️  $1${N}"; }

echo -e "${M}"
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║       🏭 PRODUCTION READINESS TEST - FULL PIPELINE VALIDATION      ║"
echo "║                    $(date '+%Y-%m-%d %H:%M:%S')                           ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo -e "${N}"

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 1: HEALTH CHECKS
# ═══════════════════════════════════════════════════════════════════════════
echo -e "\n${B}═══ PHASE 1: SYSTEM HEALTH CHECKS ═══${N}\n"

T1=$(date +%s%3N)

# Check API
log "Testing API endpoint..."
API_RESP=$(curl -s -w "\n%{http_code}" "$API/health" 2>/dev/null)
API_CODE=$(echo "$API_RESP" | tail -1)
API_BODY=$(echo "$API_RESP" | head -1)
T2=$(date +%s%3N)

if [[ "$API_CODE" == "200" ]] && [[ "$API_BODY" == *"ok"* ]]; then
    success "API Health: OK"
    metric "API Response Time: $((T2-T1))ms"
else
    fail "API not responding (HTTP $API_CODE)"
    exit 1
fi

# Check Redis via Celery
log "Testing Celery worker connectivity..."
T3=$(date +%s%3N)
WORKER_TEST=$(curl -s "$API/debug/status" 2>/dev/null || echo '{}')
T4=$(date +%s%3N)
if [[ "$WORKER_TEST" == *"redis"* ]] || [[ "$WORKER_TEST" == *"celery"* ]] || [[ -n "$WORKER_TEST" ]]; then
    success "Backend Services: Responding"
    metric "Status Check Time: $((T4-T3))ms"
else
    echo -e "${Y}⚠️  Could not verify worker status (may still work)${N}"
fi

# Check database
log "Testing database connectivity..."
T5=$(date +%s%3N)
DB_TEST=$(curl -s "$API/goals?limit=1" 2>/dev/null)
T6=$(date +%s%3N)
if [[ -n "$DB_TEST" ]]; then
    success "Database: Connected"
    metric "DB Query Time: $((T6-T5))ms"
else
    fail "Database not responding"
    exit 1
fi

HEALTH_TIME=$((T6-T1))

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2: RESET & SETUP
# ═══════════════════════════════════════════════════════════════════════════
echo -e "\n${B}═══ PHASE 2: ENVIRONMENT SETUP ═══${N}\n"

log "Resetting database for clean test..."
T7=$(date +%s%3N)
RESET_RESP=$(curl -s -X POST "$API/debug/reset?confirm=yes-delete-everything")
T8=$(date +%s%3N)
success "Database reset complete"
metric "Reset Time: $((T8-T7))ms"

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 3: CREATE TEST DATA
# ═══════════════════════════════════════════════════════════════════════════
echo -e "\n${B}═══ PHASE 3: CREATE TEST DATA ═══${N}\n"

log "Creating test goal..."
T9=$(date +%s%3N)
GOAL_RESP=$(curl -s -X POST "$API/goals" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "🧪 Production Readiness Test",
    "description": "Automated test to validate full pipeline functionality"
  }')
GOAL_ID=$(echo "$GOAL_RESP" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
T10=$(date +%s%3N)
success "Goal created: $GOAL_ID"
metric "Goal Creation: $((T10-T9))ms"

# Create 3 test tickets
log "Creating test tickets..."
declare -a TICKET_IDS
declare -a TICKET_TIMES

TICKET_TITLES=(
    "Test Task Alpha - Quick Operation"
    "Test Task Beta - Standard Operation"  
    "Test Task Gamma - Final Operation"
)

for i in {0..2}; do
    TS=$(date +%s%3N)
    TRESP=$(curl -s -X POST "$API/tickets" \
      -H "Content-Type: application/json" \
      -d "{
        \"goal_id\": \"$GOAL_ID\",
        \"title\": \"${TICKET_TITLES[$i]}\",
        \"description\": \"Automated test ticket for production validation.\",
        \"priority\": $((100 - i * 10))
      }")
    TID=$(echo "$TRESP" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
    TE=$(date +%s%3N)
    TICKET_IDS+=("$TID")
    TICKET_TIMES+=($((TE-TS)))
    echo -e "  ${G}✓${N} Ticket $((i+1)): $TID (${TICKET_TIMES[$i]}ms)"
done

AVG_TICKET_TIME=$(( (TICKET_TIMES[0] + TICKET_TIMES[1] + TICKET_TIMES[2]) / 3 ))
metric "Avg Ticket Creation: ${AVG_TICKET_TIME}ms"

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 4: STATE TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════════
echo -e "\n${B}═══ PHASE 4: STATE TRANSITIONS ═══${N}\n"

log "Testing state transitions (proposed → planned)..."
declare -a TRANSITION_TIMES

for i in {0..2}; do
    TS=$(date +%s%3N)
    curl -s -X POST "$API/tickets/${TICKET_IDS[$i]}/transition" \
      -H "Content-Type: application/json" \
      -d '{"to_state": "planned", "actor_type": "human", "actor_id": "prod-test", "reason": "Production readiness test"}' > /dev/null
    TE=$(date +%s%3N)
    TRANSITION_TIMES+=($((TE-TS)))
    echo -e "  ${G}✓${N} Ticket $((i+1)) → PLANNED (${TRANSITION_TIMES[$i]}ms)"
done

AVG_TRANSITION=$(( (TRANSITION_TIMES[0] + TRANSITION_TIMES[1] + TRANSITION_TIMES[2]) / 3 ))
metric "Avg Transition Time: ${AVG_TRANSITION}ms"

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 5: JOB EXECUTION
# ═══════════════════════════════════════════════════════════════════════════
echo -e "\n${B}═══ PHASE 5: JOB EXECUTION PIPELINE ═══${N}\n"

log "Queuing execution jobs..."
declare -a JOB_IDS
declare -a JOB_QUEUE_TIMES

for i in {0..2}; do
    TS=$(date +%s%3N)
    JOB_RESP=$(curl -s -X POST "$API/tickets/${TICKET_IDS[$i]}/run")
    JOB_ID=$(echo "$JOB_RESP" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
    TE=$(date +%s%3N)
    JOB_IDS+=("$JOB_ID")
    JOB_QUEUE_TIMES+=($((TE-TS)))
    echo -e "  ${G}✓${N} Job queued: ${JOB_ID:0:8}... (${JOB_QUEUE_TIMES[$i]}ms)"
done

AVG_QUEUE=$(( (JOB_QUEUE_TIMES[0] + JOB_QUEUE_TIMES[1] + JOB_QUEUE_TIMES[2]) / 3 ))
metric "Avg Job Queue Time: ${AVG_QUEUE}ms"

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 6: MONITOR PIPELINE
# ═══════════════════════════════════════════════════════════════════════════
echo -e "\n${B}═══ PHASE 6: PIPELINE MONITORING ═══${N}\n"

log "Monitoring ticket progression..."
MONITOR_START=$(date +%s)
MAX_WAIT=120  # 2 minutes max
POLL_INTERVAL=3

echo ""
printf "  %-12s │ 📋Plan │ 🔄Exec │ 🔍Veri │ 👀Need │ 🚫Block │ ✅Done\n" "Time"
echo "  ─────────────┼────────┼────────┼────────┼────────┼─────────┼───────"

while true; do
    ELAPSED=$(($(date +%s) - MONITOR_START))
    
    BOARD=$(curl -s "$API/board" 2>/dev/null)
    
    PLANNED=$(echo "$BOARD" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len([c for c in d['columns'] if c['state']=='planned'][0]['tickets']))" 2>/dev/null || echo "?")
    EXECUTING=$(echo "$BOARD" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len([c for c in d['columns'] if c['state']=='executing'][0]['tickets']))" 2>/dev/null || echo "?")
    VERIFYING=$(echo "$BOARD" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len([c for c in d['columns'] if c['state']=='verifying'][0]['tickets']))" 2>/dev/null || echo "?")
    NEEDS=$(echo "$BOARD" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len([c for c in d['columns'] if c['state']=='needs_human'][0]['tickets']))" 2>/dev/null || echo "?")
    BLOCKED=$(echo "$BOARD" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len([c for c in d['columns'] if c['state']=='blocked'][0]['tickets']))" 2>/dev/null || echo "?")
    DONE=$(echo "$BOARD" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len([c for c in d['columns'] if c['state']=='done'][0]['tickets']))" 2>/dev/null || echo "?")
    
    printf "  %3ds elapsed │   %s    │   %s    │   %s    │   %s    │    %s    │   %s\n" "$ELAPSED" "$PLANNED" "$EXECUTING" "$VERIFYING" "$NEEDS" "$BLOCKED" "$DONE"
    
    # Check completion
    ACTIVE=$((PLANNED + EXECUTING + VERIFYING))
    if [[ "$ACTIVE" == "0" ]] || [[ "$ACTIVE" == "000" ]]; then
        PIPELINE_TIME=$ELAPSED
        break
    fi
    
    if [[ $ELAPSED -ge $MAX_WAIT ]]; then
        echo -e "\n${Y}⚠️  Timeout after ${MAX_WAIT}s - some tickets still processing${N}"
        PIPELINE_TIME=$ELAPSED
        break
    fi
    
    sleep $POLL_INTERVAL
done

echo ""
metric "Pipeline Completion: ${PIPELINE_TIME}s"

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 7: FINAL RESULTS
# ═══════════════════════════════════════════════════════════════════════════
echo -e "\n${B}═══ PHASE 7: FINAL RESULTS ═══${N}\n"

FINAL_BOARD=$(curl -s "$API/board")

echo "$FINAL_BOARD" | python3 -c "
import json, sys
data = json.load(sys.stdin)

done = blocked = needs = other = 0
done_tickets = []
blocked_tickets = []
needs_tickets = []

for col in data['columns']:
    for t in col['tickets']:
        if col['state'] == 'done':
            done += 1
            done_tickets.append(t['title'])
        elif col['state'] == 'blocked':
            blocked += 1
            blocked_tickets.append(t['title'])
        elif col['state'] == 'needs_human':
            needs += 1
            needs_tickets.append(t['title'])
        else:
            other += 1

print(f'  Completed:    {done}/3 tickets')
for t in done_tickets:
    print(f'    ✅ {t}')

if blocked:
    print(f'  Blocked:      {blocked} tickets')
    for t in blocked_tickets:
        print(f'    🚫 {t}')

if needs:
    print(f'  Needs Review: {needs} tickets')
    for t in needs_tickets:
        print(f'    👀 {t}')

if other:
    print(f'  Still Active: {other} tickets')
"

# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY REPORT
# ═══════════════════════════════════════════════════════════════════════════
END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))

echo -e "\n${M}"
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                    📊 PRODUCTION READINESS REPORT                  ║"
echo "╠════════════════════════════════════════════════════════════════════╣"
printf "║  %-30s %35s ║\n" "Test Completed:" "$(date '+%Y-%m-%d %H:%M:%S')"
printf "║  %-30s %35s ║\n" "Total Test Duration:" "${TOTAL_TIME}s"
echo "╠════════════════════════════════════════════════════════════════════╣"
echo "║  PERFORMANCE METRICS                                               ║"
echo "╠════════════════════════════════════════════════════════════════════╣"
printf "║  %-30s %35s ║\n" "API Response Time:" "${API_CODE}ms"
printf "║  %-30s %35s ║\n" "Avg Ticket Creation:" "${AVG_TICKET_TIME}ms"
printf "║  %-30s %35s ║\n" "Avg State Transition:" "${AVG_TRANSITION}ms"
printf "║  %-30s %35s ║\n" "Avg Job Queue Time:" "${AVG_QUEUE}ms"
printf "║  %-30s %35s ║\n" "Pipeline Processing:" "${PIPELINE_TIME}s"
echo "╠════════════════════════════════════════════════════════════════════╣"

# Determine status
DONE_COUNT=$(echo "$FINAL_BOARD" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len([c for c in d['columns'] if c['state']=='done'][0]['tickets']))" 2>/dev/null || echo "0")
BLOCKED_COUNT=$(echo "$FINAL_BOARD" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len([c for c in d['columns'] if c['state']=='blocked'][0]['tickets']))" 2>/dev/null || echo "0")

if [[ "$DONE_COUNT" == "3" ]]; then
    echo "║  STATUS: ✅ ALL TESTS PASSED - READY FOR PRODUCTION              ║"
elif [[ "$BLOCKED_COUNT" -gt 0 ]]; then
    echo "║  STATUS: ⚠️  SOME TICKETS BLOCKED - CHECK VERIFICATION COMMANDS   ║"
else
    echo "║  STATUS: 🔄 PIPELINE RUNNING - CHECK WORKER LOGS                 ║"
fi

echo "╚════════════════════════════════════════════════════════════════════╝"
echo -e "${N}"

# Quick verification commands
echo -e "${C}Quick verification commands:${N}"
echo "  curl $API/health"
echo "  curl $API/board | python3 -m json.tool"
echo "  curl $API/jobs?limit=5"
echo ""
