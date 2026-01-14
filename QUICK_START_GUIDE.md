# Quick Start Guide: New Features

## 🎉 What's New

You now have two powerful new features:
1. **Log Normalization** - Beautiful, structured display of agent logs
2. **GitHub PR Integration** - One-click PR creation and tracking

---

## Setup

### 1. Install GitHub CLI (for PR integration)

```bash
# macOS
brew install gh

# Authenticate
gh auth login
```

### 2. Start Services

```bash
# Terminal 1: Backend
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2: Celery Worker
cd backend
source venv/bin/activate
celery -A app.celery_app worker --loglevel=info

# Terminal 3: Celery Beat (for PR polling)
cd backend
source venv/bin/activate
celery -A app.celery_app beat --loglevel=info

# Terminal 4: Frontend
cd frontend
npm run dev
```

---

## Feature 1: Log Normalization

### How It Works
Agent logs are automatically parsed into structured entries:
- 🧠 **Thinking blocks** - Collapsible AI reasoning
- 📝 **File changes** - Diffs with syntax highlighting
- 💻 **Commands** - With exit codes and output
- ❌ **Errors** - With tracebacks

### Using It
1. Run any ticket execution
2. Open ticket detail drawer
3. View job logs
4. Logs are automatically normalized (or click "Normalize" if manual)
5. Expand/collapse sections

### API Endpoints
```bash
# Get normalized logs
GET http://localhost:8000/jobs/{job_id}/normalized-logs

# Trigger normalization
POST http://localhost:8000/jobs/{job_id}/normalize-logs?agent_type=claude
```

---

## Feature 2: GitHub PR Integration

### How It Works
1. Complete a ticket (state: DONE)
2. Click "Create Pull Request" in ticket drawer
3. PR is created on GitHub from the ticket's branch
4. Background task checks PR status every 5 minutes
5. Ticket auto-transitions to DONE when PR merges

### Using It

#### Create a PR
1. Ensure ticket has workspace with changes
2. Open ticket detail drawer
3. Click "Create Pull Request" button
4. PR appears on GitHub
5. Badge shows PR status

#### Monitor PR Status
- **Automatic:** Background polling every 5 minutes
- **Manual:** Click refresh icon on PR badge
- **View on GitHub:** Click external link icon

#### Auto-Transition
When your PR is merged on GitHub:
- Background task detects merge within 5 minutes
- Ticket state changes to DONE automatically
- System event is created in ticket history

### API Endpoints
```bash
# Create PR
POST http://localhost:8000/pull-requests
{
  "ticket_id": "abc-123",
  "title": "Optional PR title",
  "body": "Optional PR description",
  "base_branch": "main"
}

# Get PR status
GET http://localhost:8000/pull-requests/{ticket_id}

# Manually refresh PR status
POST http://localhost:8000/pull-requests/{ticket_id}/refresh
```

---

## Testing the Features

### Test Log Normalization

1. **Create a test ticket:**
```bash
curl -X POST http://localhost:8000/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "goal_id": "your-goal-id",
    "title": "Test log normalization",
    "description": "Create a simple function"
  }'
```

2. **Execute the ticket** (via UI or API)

3. **View normalized logs:**
```bash
curl http://localhost:8000/jobs/{job_id}/normalized-logs
```

4. **Check frontend:** Open ticket drawer and view logs

### Test GitHub PR Integration

1. **Prerequisites:**
   - Have a completed ticket with workspace
   - Ensure gh CLI is authenticated
   - Ensure repo has a remote

2. **Create PR via API:**
```bash
curl -X POST http://localhost:8000/pull-requests \
  -H "Content-Type: application/json" \
  -d '{
    "ticket_id": "your-ticket-id",
    "base_branch": "main"
  }'
```

3. **Check GitHub:** PR should appear in your repo

4. **Test auto-transition:**
   - Merge the PR on GitHub
   - Wait up to 5 minutes
   - Check ticket state (should be DONE)

5. **Check frontend:**
   - Open ticket drawer
   - See PR badge with status
   - Click refresh to manually sync

---

## Troubleshooting

### Log Normalization Issues

**Problem:** Logs not parsing correctly  
**Solution:** 
- Check agent output format matches expected patterns
- Look for parser errors in backend logs
- Try manual normalization: `POST /jobs/{id}/normalize-logs`

**Problem:** Missing log entries  
**Solution:**
- Ensure job has output logs
- Check database migration applied: `8ef5054dc280`

### GitHub PR Issues

**Problem:** "GitHub CLI not found"  
**Solution:**
```bash
brew install gh
gh auth login
```

**Problem:** "Not authenticated"  
**Solution:**
```bash
gh auth status
# If not logged in:
gh auth login
```

**Problem:** PR creation fails  
**Solution:**
- Ensure workspace has a valid git branch
- Check if remote is configured: `git remote -v`
- Verify branch has commits: `git log`

**Problem:** Auto-transition not working  
**Solution:**
- Ensure Celery Beat is running
- Check backend logs for polling errors
- Manually refresh: Click refresh icon on PR badge

---

## Database Migrations

Both features require database migrations:

```bash
cd backend
source venv/bin/activate

# Apply migrations
alembic upgrade head

# Verify
alembic current
# Should show: 8ef5054dc280 (normalized logs) and 03220f0b93ae (PR fields)
```

---

## Architecture Overview

### Log Normalization Flow
```
Agent Execution → Raw Logs → LogNormalizerService → DB → API → Frontend Components
```

### PR Integration Flow
```
Ticket (DONE) → CreatePR Button → GitHub Service → gh CLI → GitHub PR
                                                                  ↓
Background Task (every 5 min) ← Celery Beat ← Poll Status ← Check PR State
        ↓
Auto-transition Ticket to DONE (if merged)
```

---

## Configuration

### Environment Variables

Add to `.env` (if not already present):
```bash
# GitHub (optional, gh CLI uses system auth)
GITHUB_TOKEN=ghp_xxxxx  # Optional, gh CLI preferred

# Celery Beat schedule (optional, default 5 min)
PR_POLL_INTERVAL=300  # seconds
```

### Celery Beat Schedule

Edit `backend/app/celery_app.py` to adjust polling frequency:
```python
"poll-pr-statuses": {
    "task": "poll_pr_statuses",
    "schedule": 300.0,  # Change this (seconds)
},
```

---

## Next Steps

### Optional Enhancements
1. **Add normalized log toggle to UI** - Switch between raw/normalized views
2. **GitHub webhooks** - Real-time PR events instead of polling
3. **PR review comments** - Display in ticket UI
4. **Multi-agent parsers** - Support Cursor, Windsurf, Aider logs

### Testing Checklist
- [ ] Create ticket → Execute → View normalized logs
- [ ] Create PR from ticket
- [ ] Merge PR → Verify auto-transition
- [ ] Manual PR refresh works
- [ ] PR badge displays correctly

---

## Files to Know

### Backend
- `backend/app/services/log_normalizer.py` - Log parsing logic
- `backend/app/services/github_service.py` - GitHub integration
- `backend/app/routers/pull_requests.py` - PR API endpoints
- `backend/app/worker.py` - Background polling task

### Frontend
- `frontend/src/components/NormalizedConversation/` - Log display components
- `frontend/src/components/PullRequest/` - PR UI components
- `frontend/src/services/api.ts` - API client methods

### Database
- `backend/alembic/versions/8ef5054dc280_*.py` - Normalized logs migration
- `backend/alembic/versions/03220f0b93ae_*.py` - PR fields migration

---

## Getting Help

If you encounter issues:
1. Check backend logs: `tail -f backend/logs/*.log`
2. Check Celery logs for background task errors
3. Verify database migrations: `alembic current`
4. Test GitHub CLI manually: `gh pr list`

For detailed implementation info, see:
- `IMPLEMENTATION_COMPLETE.md` - Full technical details
- `LOG_NORMALIZATION_IMPLEMENTATION.md` - Log parser guide
- `GITHUB_PR_IMPLEMENTATION.md` - PR integration guide
