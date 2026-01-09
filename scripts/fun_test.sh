#!/bin/bash
# 🎮 Fun Kanban System Test - Watch tickets flow through the pipeline!

set -e

API="http://localhost:8000"
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

echo -e "${MAGENTA}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║      🎯 KANBAN SYSTEM STRESS TEST - TICKET RACE! 🏁          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check health
echo -e "${CYAN}[1/5] 🏥 Checking system health...${NC}"
HEALTH=$(curl -s "$API/health" | grep -o '"status":"ok"' || echo "FAIL")
if [[ "$HEALTH" == *"ok"* ]]; then
    echo -e "  ${GREEN}✅ System is healthy!${NC}"
else
    echo "  ❌ System not responding. Start with: make dev-backend && make dev-worker"
    exit 1
fi

# Reset (optional - comment out to keep existing data)
echo -e "\n${CYAN}[2/5] 🧹 Clearing the board...${NC}"
curl -s -X POST "$API/debug/reset?confirm=yes-delete-everything" > /dev/null
echo -e "  ${GREEN}✅ Fresh start!${NC}"

# Create a fun goal
echo -e "\n${CYAN}[3/5] 🎯 Creating goal: Speed Demon Calculator...${NC}"
GOAL_RESP=$(curl -s -X POST "$API/goals" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "⚡ Speed Demon Calculator",
    "description": "Build lightning-fast math operations that would make your CPU cry tears of joy!"
  }')
GOAL_ID=$(echo "$GOAL_RESP" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo -e "  ${GREEN}✅ Goal created: $GOAL_ID${NC}"

# Create 5 quick tickets
echo -e "\n${CYAN}[4/5] 🎫 Creating 5 race tickets...${NC}"

declare -a TICKET_IDS
declare -a TICKET_NAMES
TICKET_NAMES=(
    "🏎️ Add function: blaze_add(a, b)"
    "🔥 Add function: turbo_multiply(a, b)"
    "💨 Add function: sonic_subtract(a, b)"
    "⚡ Add function: lightning_divide(a, b)"
    "🌟 Add function: mega_power(base, exp)"
)

for i in {0..4}; do
    TICKET_RESP=$(curl -s -X POST "$API/tickets" \
      -H "Content-Type: application/json" \
      -d "{
        \"goal_id\": \"$GOAL_ID\",
        \"title\": \"${TICKET_NAMES[$i]}\",
        \"description\": \"Create a blazing fast calculator function.\n\nRequirements:\n- Type hints\n- Docstring\n- Handle edge cases\n- Be FAST!\",
        \"priority\": $((100 - i * 10))
      }")
    TID=$(echo "$TICKET_RESP" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
    TICKET_IDS+=("$TID")
    echo -e "  ${YELLOW}[$((i+1))/5]${NC} ${TICKET_NAMES[$i]} → ${GREEN}$TID${NC}"
done

# Transition all to planned
echo -e "\n${CYAN}[5/5] 🚀 Moving all tickets to PLANNED state...${NC}"
for i in {0..4}; do
    curl -s -X POST "$API/tickets/${TICKET_IDS[$i]}/transition" \
      -H "Content-Type: application/json" \
      -d '{"to_state": "planned", "actor_type": "human", "actor_id": "test-runner", "reason": "Ready to race!"}' > /dev/null
    echo -e "  ${GREEN}✅${NC} ${TICKET_NAMES[$i]} → PLANNED"
done

echo -e "\n${MAGENTA}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                   🎉 SETUP COMPLETE! 🎉                      ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Goal ID: $GOAL_ID                  ║"
echo "║  Tickets: 5 tickets in PLANNED state                         ║"
echo "║                                                              ║"
echo "║  📺 Watch the action:                                        ║"
echo "║     → Frontend: http://localhost:5173                        ║"
echo "║     → API Board: curl $API/board | jq                      ║"
echo "║                                                              ║"
echo "║  🏁 To start the race (kick off execution):                  ║"
echo "║     curl -X POST $API/tickets/{id}/run                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Show board state
echo -e "${CYAN}📊 Current Board State:${NC}"
curl -s "$API/board" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for col in data['columns']:
    count = len(col['tickets'])
    if count > 0:
        print(f\"  • {col['state']}: {count} tickets\")
"

echo ""
echo -e "${YELLOW}💡 Want to auto-run all tickets? Run:${NC}"
echo "   for id in ${TICKET_IDS[*]}; do curl -s -X POST \"\$API/tickets/\$id/run\" > /dev/null && echo \"Started: \$id\"; done"
echo ""
