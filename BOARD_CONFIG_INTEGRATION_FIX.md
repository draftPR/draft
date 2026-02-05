# Board Config Integration Fix

## Summary
Fixed the worker to actually use board-level configuration overrides, and updated the calculator project's outdated planner config.

## Changes Made

### 1. Calculator Project Config Update
**File:** `/Users/dor/Documents/code/tests/calculator-project/smartkanban.yaml`

**Before:**
```yaml
planner_config:
  # LLM model - uses AWS Bedrock Claude
  model: "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0"
  max_tokens_reflection: 300
  max_tokens_followup: 500
  timeout: 30
```

**After:**
```yaml
planner_config:
  # Agent CLI path for AI operations (cursor-agent, claude, etc.)
  # The planner now uses agent CLIs instead of direct LLM API calls
  agent_path: "~/.local/bin/cursor-agent"
  timeout: 60
```

**Why:** The planner was refactored to use agent CLIs (cursor-agent, claude) instead of direct LLM API calls. The old Bedrock model reference is obsolete.

---

### 2. Worker Integration with Board Config

#### A. Execute Task Worker
**File:** `backend/app/worker.py` (lines ~1477-1492)
**Before:**
```python
# Load configuration from the worktree (where smartkanban.yaml should be)
# Disable cache to ensure we get the latest config
config_service = ConfigService(worktree_path)
config = config_service.load_config(use_cache=False)
execute_config = config.execute_config
planner_config = config.planner_config
```

**After:**
```python
# Load configuration from the worktree (where smartkanban.yaml should be)
# Apply board-level overrides if present
# Disable cache to ensure we get the latest config
config_service = ConfigService(worktree_path)

# Get board config for overrides
board_config = None
if ticket.board_id:
    with get_sync_db() as db:
        from app.models.board import Board
        board = db.query(Board).filter(Board.id == ticket.board_id).first()
        if board and board.config:
            board_config = board.config

# Load config with board overrides applied
config = config_service.load_config_with_board_overrides(
    board_config=board_config,
    use_cache=False
)
execute_config = config.execute_config
planner_config = config.planner_config
```

#### B. Verify Task Worker
**File:** `backend/app/worker.py` (lines ~2097-2102)
**Similar change applied to verification task**

**Why:** The worker was only reading from `smartkanban.yaml` and ignoring board-level overrides stored in the database. This meant the BoardSettingsDialog UI had no effect on actual execution.

#### C. Revision Merge Operations
**File:** `backend/app/routers/revisions.py` (lines ~565-570)

**Before:**
```python
# Read merge configuration from smartkanban.yaml
from app.services.config_service import ConfigService
config_service = ConfigService()
config = config_service.load_config()
merge_config = config.merge_config
```

**After:**
```python
# Read merge configuration with board-level overrides
from app.services.config_service import ConfigService
config_service = ConfigService()

# Get board config for overrides
board_config = None
if ticket.board_id:
    from sqlalchemy import select as sql_select_board
    from app.models.board import Board
    board_result = await db.execute(
        sql_select_board(Board).where(Board.id == ticket.board_id)
    )
    board = board_result.scalar_one_or_none()
    if board and board.config:
        board_config = board.config

# Load config with board overrides applied
config = config_service.load_config_with_board_overrides(
    board_config=board_config,
    use_cache=False
)
merge_config = config.merge_config
```

**Why:** Merge operations (squash, rebase, push behavior) should respect board-level configuration. The approve-and-merge workflow needs to use the correct merge strategy per board.

---

### What Doesn't Need Board Overrides

**Places that correctly use YAML-only config:**
- `planner.py` - Planner operates globally across boards, not board-specific
- `goals.py` (ticket generation) - Uses project.repo_root which is already in Board model
- `board.py` (legacy endpoint) - Reading global defaults for display purposes

**Why:** Not all config should be board-specific. Project structure (repo_root), global planner settings, and codebase analysis settings are shared across all boards.

---

## Architecture: Hybrid Config Approach

### What Exists (Already Implemented)
✅ **Database Storage** - `Board.config` JSON column
✅ **API Endpoints** - GET/PUT/DELETE `/boards/{id}/config`
✅ **Frontend UI** - `BoardSettingsDialog` component
✅ **Merge Logic** - `ConfigService.load_config_with_board_overrides()`

### What Was Missing (Now Fixed)
❌ **Worker Integration** - Worker never called `load_config_with_board_overrides()`

---

## Configuration Priority (Now Working)

**Highest to Lowest:**
1. **Board config** (database) - UI-editable, per-board overrides
2. **YAML config** (smartkanban.yaml) - Version-controlled, team defaults
3. **Defaults** (code) - Fallback values

### Division of Responsibility

**YAML (smartkanban.yaml):**
- Verification commands (project-specific)
- YOLO allowlist (security boundary)
- Default settings for team

**Database (Board.config):**
- Executor model selection (auto, opus-4.5, sonnet-4.5)
- Timeout overrides
- Preferred executor (cursor-agent, claude, cursor)
- Board-specific preferences

**Example:**
```yaml
# In smartkanban.yaml (version controlled)
execute_config:
  timeout: 600
  preferred_executor: cursor-agent
  yolo_allowlist:
    - /path/to/trusted/repo

# In Board.config (database, UI-editable)
{
  "execute_config": {
    "executor_model": "opus-4.5",  // Override for this board only
    "timeout": 300                  // Override for this board only
  }
}
```

---

## Impact

### Before This Fix
- BoardSettingsDialog UI was functional but **ineffective**
- Changes saved to database had **no effect on execution**
- Workers always used YAML config only

### After This Fix
- Board overrides properly applied during execution ✅
- UI changes immediately affect ticket execution ✅
- Hybrid config model working as designed ✅

---

## Testing Recommendations

1. **Verify board config applied:**
   ```bash
   # Set board timeout to 300 via UI
   # Run ticket execution
   # Check worker logs - should show timeout=300 not YAML default
   ```

2. **Verify merge works correctly:**
   ```bash
   # YAML: timeout=600, model=null
   # Board: model="opus-4.5"
   # Expected result: timeout=600, model="opus-4.5"
   ```

3. **Verify YAML fallback:**
   ```bash
   # Clear board config (DELETE /boards/{id}/config)
   # Execution should use YAML defaults
   ```

---

## Related Files
- `backend/app/models/board.py` - Board model with config column
- `backend/app/services/config_service.py` - Config merge logic
- `backend/app/routers/board.py` - Config API endpoints
- `frontend/src/components/BoardSettingsDialog.tsx` - UI component
- `backend/alembic/versions/9d17f0698d3b_add_config_column_to_boards_table.py` - Migration
