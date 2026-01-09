#!/bin/bash
# ⚡ Quick Kanban Status - one-liner board view

curl -s "http://localhost:8000/board" 2>/dev/null | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    e = {'proposed':'⚪','planned':'📋','executing':'🔄','verifying':'🔍','needs_human':'👀','blocked':'🚫','done':'✅','abandoned':'❌'}
    counts = {col['state']: len(col['tickets']) for col in d['columns']}
    parts = [f\"{e.get(k,'•')}{v}\" for k,v in counts.items() if v > 0]
    print(f\"🎯 {' │ '.join(parts)} │ Total: {d['total_tickets']}\")
except Exception as ex:
    print(f'❌ Error: {ex}')
" || echo "❌ Cannot connect to API"
