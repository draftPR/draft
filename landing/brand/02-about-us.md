# Alma Kanban - About Us & Business

## One-liner
Alma Kanban is the autonomous delivery system for codebases - it turns goals into shipped code using AI agents, with humans reviewing every diff.

## What we are
An open-source, self-hostable kanban board purpose-built for AI-driven software delivery. You describe a goal. Alma reads the codebase, generates scoped tickets, plans dependencies, dispatches AI agents in isolated git worktrees, runs verification (tests + lints), and delivers reviewed diffs. You review and merge.

## What we are NOT
- Not a "vibe coding" tool. We don't just throw an AI at code and hope for the best.
- Not a replacement for engineers. We're a force multiplier for engineers who review everything.
- Not another project management tool. Linear and GitHub Issues don't run code. We do.
- Not fully autonomous. Human-in-the-loop is a feature, not a limitation.

## The problem we solve
AI coding agents (Claude Code, Cursor, Codex) are powerful but chaotic. They work on one task at a time, in a single session, with no pipeline. There's no way to:
- Queue up 10 tickets and let agents work through them
- Automatically verify output before a human sees it
- Manage dependencies between tasks
- Review diffs in a structured workflow

Engineers end up being project managers for their AI agents. That doesn't scale.

## How we solve it
Alma is the missing infrastructure layer between "describe what you want" and "merge to main":

1. **Goal -> Tickets**: Reads your codebase, generates scoped tickets with dependency ordering
2. **Autonomous planner**: Builds a DAG, queues work in order, auto-retries failures
3. **Isolated execution**: Each ticket runs in its own git worktree - agents never collide
4. **Verification pipeline**: Tests and lints run automatically after every agent execution
5. **Review & merge**: Built-in diff viewer with inline comments. One click to merge or create a GitHub PR.

## Founding story
[PLACEHOLDER - Dor, what's the origin story? What moment made you think "I need to build this"? Was it managing too many Claude Code sessions? Seeing the gap between AI coding and structured delivery?]

## Team
- **Dor** (@doramirdor) - Founder & solo builder
- [PLACEHOLDER - any other contributors, advisors, or early team members?]

## Business model
| Tier | Price | Target |
|------|-------|--------|
| **Free** | $0 forever | Self-hosted. Unlimited repos, 1 agent at a time, full code review, REST API. |
| **Pro** | $29/mo | Cloud hosted. 5 parallel agents, GitHub PR sync, Slack notifications. |
| **Team** | $99/mo | For engineering teams. Unlimited agents, team workspaces, SSO & audit log. |

**Monetization thesis:** Self-host free to build community and trust. Charge for convenience (hosted), scale (parallel agents), and team features (SSO, workspaces).

## Tech stack
- **Backend:** FastAPI + SQLAlchemy (async) + SQLite
- **Frontend:** React + Vite + TypeScript + Tailwind CSS + shadcn/ui
- **AI Executors:** Claude Code CLI, Cursor Agent CLI (pluggable - bring any agent)
- **License:** BSL 1.1 (source-available, converts to open source after 4 years)

## Competitive positioning
| Capability | Alma | Vibe Kanban tools | Linear / GitHub Issues |
|---|---|---|---|
| Generates tickets from codebase | Yes | No | No |
| Dependency planning (DAG) | Yes | No | No |
| Autonomous planner / autopilot | Yes | No | No |
| Agents execute code | Yes | Yes | No |
| Verification pipeline | Yes | No | No |
| Built-in code review | Yes | Some | No |
| Self-hostable + open source | Yes | Varies | No |

## Key differentiators (in priority order)
1. **Full pipeline, not just execution.** Goal -> tickets -> planning -> execution -> verification -> review -> merge. End to end.
2. **Human-in-the-loop by design.** Every diff gets reviewed. Trust is earned per-change, not assumed.
3. **Self-hostable.** Your code never leaves your infrastructure.
4. **Agent-agnostic.** Claude Code, Codex, or your own tool. Alma orchestrates, not locks in.

## Current stage
- [PLACEHOLDER - what stage? Pre-launch? Early access? How many waitlist signups? Any paying users?]
- [PLACEHOLDER - what's the next milestone? Public launch? First paid customer?]

---

## Open questions for Dor

- [ ] What's the founding story / origin moment?
- [ ] Current traction numbers (waitlist, GitHub stars, self-host installs)?
- [ ] What stage are you at? (Pre-revenue? First customers?)
- [ ] Any advisors, investors, or notable early users?
- [ ] What's the 6-month roadmap priority? (Cloud launch? Enterprise features? Integrations?)
- [ ] BSL 1.1 - is this final, or considering a switch to full OSS?
