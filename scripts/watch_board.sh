#!/bin/bash
# 📺 Live Kanban Board Monitor
# Usage: ./watch_board.sh [interval_seconds]

API="http://localhost:8000"
INTERVAL="${1:-2}"

# Colors
C='\033[0;36m'  # Cyan
G='\033[0;32m'  # Green
Y='\033[1;33m'  # Yellow
M='\033[0;35m'  # Magenta
R='\033[0;31m'  # Red
N='\033[0m'     # No color

clear

while true; do
    # Move cursor to top
    tput cup 0 0 2>/dev/null || echo ""
    
    TIMESTAMP=$(date '+%H:%M:%S')
    
    echo -e "${M}╔═══════════════════════════════════════════════════════════════════╗${N}"
    echo -e "${M}║${N}       ${C}📊 KANBAN LIVE DASHBOARD${N}          ${Y}⏰ $TIMESTAMP${N}          ${M}║${N}"
    echo -e "${M}╠═══════════════════════════════════════════════════════════════════╣${N}"
    
    # Get board data
    BOARD=$(curl -s "$API/board" 2>/dev/null)
    
    if [ -z "$BOARD" ]; then
        echo -e "${M}║${N}  ${R}❌ Cannot connect to API${N}                                        ${M}║${N}"
    else
        echo "$BOARD" | python3 -c "
import json, sys
data = json.load(sys.stdin)
state_cfg = {
    'proposed': ('⚪', 'Proposed'),
    'planned': ('📋', 'Planned'),
    'executing': ('🔄', 'Executing'),
    'verifying': ('🔍', 'Verifying'),
    'needs_human': ('👀', 'Needs Review'),
    'blocked': ('🚫', 'Blocked'),
    'done': ('✅', 'Done'),
    'abandoned': ('❌', 'Abandoned')
}

for col in data['columns']:
    state = col['state']
    tickets = col['tickets']
    emoji, label = state_cfg.get(state, ('•', state))
    count = len(tickets)
    
    bar = '█' * min(count, 20)
    
    if count > 0:
        color = '\033[0;32m' if state == 'done' else '\033[1;33m' if state == 'executing' else '\033[0;36m'
    else:
        color = '\033[0;90m'  # Gray for empty
    
    print(f'  {emoji} {label:14} {color}{bar:20}{count:3}\033[0m')

print('')
print('  ─────────────────────────────────────────────────────────────')
print(f'  Total: {data[\"total_tickets\"]} tickets')
" 2>/dev/null
    fi
    
    # Jobs info
    JOBS=$(curl -s "$API/jobs?status=running&limit=5" 2>/dev/null)
    QUEUED=$(curl -s "$API/jobs?status=queued&limit=5" 2>/dev/null)
    
    echo ""
    echo -e "${M}╠═══════════════════════════════════════════════════════════════════╣${N}"
    echo -e "${M}║${N}  ${Y}🏃 ACTIVE JOBS${N}                                                    ${M}║${N}"
    echo -e "${M}╠═══════════════════════════════════════════════════════════════════╣${N}"
    
    echo "$JOBS" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    jobs = data.get('jobs', [])
    if not jobs:
        print('  \033[0;90m(no running jobs)\033[0m')
    else:
        for j in jobs[:3]:
            print(f'  🔵 {j[\"job_type\"]} | {j[\"id\"][:8]}... | {j[\"status\"]}')
except:
    print('  \033[0;90m(no running jobs)\033[0m')
" 2>/dev/null
    
    echo -e "${M}╚═══════════════════════════════════════════════════════════════════╝${N}"
    echo ""
    echo -e "  ${C}Press Ctrl+C to exit${N} | Refreshing every ${INTERVAL}s"
    
    sleep $INTERVAL
done
