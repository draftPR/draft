# Smart Kanban Demo Walkthrough

Welcome! This guide will walk you through your first experience with Smart Kanban's autonomous code delivery system.

## What You'll Learn

By the end of this walkthrough, you'll understand how Smart Kanban:
1. Analyzes codebases and understands goals
2. Generates concrete, actionable tickets
3. Executes changes autonomously
4. Verifies everything works
5. Provides full transparency for review

## The Scenario

You've inherited a calculator codebase with several bugs:
- Division by zero crashes the app
- Square root doesn't validate negative inputs
- Modulo doesn't handle zero divisor
- Missing test coverage for edge cases
- TODOs everywhere

**Your goal:** Fix all the bugs and add comprehensive tests.

**The catch:** You're not going to write any code manually!

## Step-by-Step Walkthrough

### Step 1: View the Goal (30 seconds)

1. Open Smart Kanban at http://localhost:3000
2. You'll see a pre-created goal: **"Fix the calculator bugs and add missing tests"**
3. Click on the goal to see the full description
4. Notice it references the specific bugs in the codebase

**What's happening:** Smart Kanban has already been set up with a realistic goal.

---

### Step 2: Generate Tickets (1 minute)

1. Click the **"Generate Tickets"** button
2. Watch as the AI analyzes the codebase (check the demo-repo/ files!)
3. Wait for ticket proposals to appear (usually 15-30 seconds)
4. Review the generated tickets

**What's happening:** Smart Kanban's planner is:
- Reading your code files
- Finding TODOs and bugs
- Understanding dependencies
- Creating a plan

**Expected output:** 4-6 tickets like:
- "Add error handling for division by zero"
- "Validate negative input in square_root"
- "Add comprehensive test coverage"
- etc.

---

### Step 3: Review and Accept Tickets (1 minute)

1. Read through each generated ticket
2. Notice they're in PROPOSED state (awaiting your approval)
3. Click **"Accept All"** or individually accept tickets you like
4. Watch tickets move to PLANNED state

**What's happening:** Smart Kanban requires human approval before executing anything. You're in control!

---

### Step 4: Execute Autonomously (2-5 minutes)

1. Select a ticket in PLANNED state
2. Click **"Execute"**
3. Watch the real-time log stream as the AI agent works
4. See the ticket transition: PLANNED → EXECUTING → VERIFYING

**What's happening:** Smart Kanban:
- Creates an isolated git worktree for this ticket
- Runs the AI executor (Claude Code) with the ticket context
- Makes code changes
- Runs verification commands (tests, syntax checks)
- Records everything

**Tip:** Click "View Logs" to see exactly what the agent is doing!

---

### Step 5: Review the Evidence (1 minute)

1. Once a ticket reaches NEEDS_HUMAN state, click to open it
2. Navigate through the evidence tabs:
   - **Plan:** What the agent intended to do
   - **Actions:** Commands it ran
   - **Diffs:** Exact code changes
   - **Tests:** Verification results
   - **Cost:** LLM API costs (if tracked)

**What's happening:** Every action is recorded. Full transparency.

---

### Step 6: Approve or Request Changes (30 seconds)

1. Review the diff - does it look correct?
2. Check test results - did everything pass?
3. Either:
   - **Approve:** Mark the ticket as DONE
   - **Request Changes:** Add a comment and re-execute

**What's happening:** You're the final authority. The AI proposes, you dispose.

---

### Step 7: Merge to Main (30 seconds)

1. Once all tickets are DONE, you'll see a **"Merge All"** option
2. Click it to merge all changes back to your main branch
3. Review the merge checklist:
   - ✅ All tests passing
   - ✅ No sensitive data exposed
   - ✅ Changes reviewed
4. Confirm the merge

**What's happening:** Smart Kanban merges all the isolated worktrees back to your main branch and cleans up.

---

## What You Just Did

Congratulations! You just:
- ✅ Defined a goal in plain English
- ✅ Had AI generate a complete implementation plan
- ✅ Watched autonomous code execution
- ✅ Reviewed comprehensive evidence
- ✅ Merged bug-free changes

**All without writing a single line of code yourself.**

## Next Steps

1. **Try Your Own Goal:** Click "New Goal" and describe something you want in your codebase
2. **Experiment with Executors:** Try different AI agents (Cursor, Aider, etc.) if installed
3. **Explore Settings:** Configure YOLO mode, cost budgets, verification commands
4. **Read the Docs:** Check out CLAUDE.md for the full architecture

## Key Concepts Learned

| Concept | What It Means |
|---------|---------------|
| **Goal** | High-level objective in plain English |
| **Tickets** | Concrete, actionable tasks generated from goals |
| **Autonomous Execution** | AI agent implements changes without prompting |
| **Worktree Isolation** | Each ticket gets its own git workspace |
| **Verification Pipeline** | Automated tests run before human review |
| **Evidence Trail** | Every action, diff, and test recorded |

## Troubleshooting

**Q: Ticket failed with "executor not found"**
A: Install Claude Code CLI: `npm install -g @anthropic-ai/claude-code`

**Q: Tests are failing**
A: That's okay for a demo! The AI should handle it on retry or you can request changes.

**Q: Nothing is happening**
A: Check that Redis is running (or you're in local mode). Look at backend logs.

---

## Ready to Use It for Real?

Smart Kanban works on **any git repository**. Just:

1. Create a board pointing to your repo
2. Define your goals
3. Let the autonomous system handle the rest

Welcome to the future of code delivery! 🚀
