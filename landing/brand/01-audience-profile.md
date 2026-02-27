# Alma Kanban - Audience Profile

## Primary ICP: The Engineering Lead

**Name:** Alex
**Role:** Engineering Lead / Senior Staff Engineer
**Company size:** 10-200 engineers (startup or scale-up)
**Reports to:** VP Engineering or CTO

### Demographics
- 28-42 years old
- 5-15 years of software engineering experience
- Has managed at least one team of 3+ engineers
- Based in US, EU, or Israel (tech hubs)

### Current tooling
- Already uses AI coding tools: Claude Code, Cursor, Codex, or similar
- Project management: Linear, GitHub Issues, Jira
- Git workflow: GitHub or GitLab with PR-based review
- CI/CD in place (GitHub Actions, CircleCI, etc.)

### Pain points
1. **AI agents are powerful but unmanaged.** Alex can use Claude Code for individual tasks, but there's no way to queue up 10 tickets and let agents work through them autonomously.
2. **Context-switching tax.** Every AI coding session requires Alex to set up context, monitor progress, review output, and manually move work forward. That overhead doesn't scale.
3. **No pipeline, just sessions.** AI coding tools are single-player. There's no dependency ordering, no verification step, no structured review workflow.
4. **Trust gap.** Alex doesn't want to auto-merge AI-generated code. They want to review diffs, run tests, and approve before anything hits main.
5. **Team visibility.** When multiple people (or agents) are working in parallel, Alex needs a dashboard - what's running, what's blocked, what needs review.

### What they want
- A system that takes a high-level goal and breaks it into work, automatically
- Agents that run in isolation (no stepping on each other's work)
- A review workflow built in (not bolted on)
- Control over what gets auto-approved vs. what requires human sign-off
- Self-hostable (data stays in their infra) with an option for hosted convenience

### How they evaluate tools
- **Does it work with my existing stack?** (Git, GitHub, my preferred AI agent)
- **Can I trust it?** (Isolation, verification, review before merge)
- **Is it open source?** (Can I audit it, extend it, self-host it?)
- **Does it save me time?** (Not just move complexity around)

### Where they hang out
- Hacker News, X/Twitter (dev community), GitHub trending
- Engineering blogs (company blogs, personal blogs of tech leads)
- Podcasts: [PLACEHOLDER - which dev podcasts does Dor listen to?]
- Communities: [PLACEHOLDER - any specific Discord/Slack communities?]

---

## Secondary ICP: The Solo Builder

**Name:** Sam
**Role:** Solo developer / Indie hacker / Early-stage founder
**Company size:** 1-3 people

### Demographics
- 24-38 years old
- Comfortable self-hosting
- Ships fast, values automation over process

### Pain points
1. **Limited bandwidth.** Sam is one person doing the work of five. AI coding agents help, but managing them is still manual work.
2. **Wants a force multiplier.** Not just "AI writes code" but "AI manages the entire pipeline while I focus on product."
3. **Hates process overhead.** Won't adopt anything that adds more steps. It has to be simpler than the alternative.

### What they want
- "Give it a goal, come back to review diffs"
- Free self-hosted tier (budget-conscious)
- Three commands to get started, not a 20-step setup

---

## Anti-personas (who we are NOT for)

1. **The non-technical PM** who wants AI to build an app from a Figma mockup. Alma is for engineers who understand code and want to review diffs.
2. **The "fully autonomous" believer** who wants zero human involvement. Alma is human-in-the-loop by design.
3. **Enterprise procurement buyers** (for now). No SOC 2, no SSO yet on free tier, no sales team.

---

## Open questions for Dor

- [ ] Which specific communities or channels do you see the most engagement from? (HN, X, specific Discords?)
- [ ] Do you have any existing user interviews or waitlist survey data?
- [ ] Are there specific company sizes or verticals you're prioritizing for launch?
- [ ] Is there a third persona (e.g., agency/consultancy running AI agents for clients)?
- [ ] What's the split you're seeing between self-host interest vs. hosted/cloud interest?
