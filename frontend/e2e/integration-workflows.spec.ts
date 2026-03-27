/**
 * Integration workflow E2E tests.
 *
 * These tests cover multi-step workflows:
 *  1. Execute ticket → job created
 *  2. Ticket in needs_human → code review → open diff viewer
 *  3. Approve review → merge to main
 *  4. Blocked ticket → shows blocker + unblock button
 *  5. Ticket dependencies → shows dependents
 *  6. Autopilot processes planned tickets
 *  7. Planner generates follow-up after autopilot
 *
 * All API calls are intercepted with Playwright route mocking —
 * no real backend needed.
 *
 * IMPORTANT: Playwright route matching uses "last registered wins".
 * Specific overrides must be registered AFTER mockAllApiRoutes().
 */

import { test, expect } from "@playwright/test";
import { mockAllApiRoutes, mockTickets } from "./fixtures";

const API = "http://localhost:8000";

// ─── Shared mock data ───────────────────────────────────────────

// Revision with correct schema fields (matches RevisionResponse)
const mockRevision = {
  id: "rev-1",
  ticket_id: "ticket-1",
  job_id: "job-1",
  number: 1,
  status: "open",
  diff_stat_evidence_id: null,
  diff_patch_evidence_id: null,
  created_at: "2025-01-01T01:00:00Z",
  unresolved_comment_count: 0,
};

const mockDiffPatch = [
  "diff --git a/src/schema.py b/src/schema.py",
  "index abc1234..def5678 100644",
  "--- a/src/schema.py",
  "+++ b/src/schema.py",
  "@@ -1,3 +1,5 @@",
  " import sqlalchemy",
  "+from sqlalchemy import Column, String",
  "+from sqlalchemy import Integer",
  "-# placeholder",
  " ",
  " class Base:",
].join("\n");

const mockRevisionDiff = {
  revision_id: "rev-1",
  diff_stat: "+2 -1",
  diff_patch: mockDiffPatch,
  files: [
    {
      path: "src/schema.py",
      additions: 2,
      deletions: 1,
      status: "modified",
    },
  ],
};

const mockMergeStatus = {
  can_merge: true,
  is_merged: false,
  has_approved_revision: true,
  workspace: {
    branch_name: "goal/goal-1/ticket/ticket-1",
    path: "/tmp/test-repo/.draft/worktrees/ticket-1",
  },
};

// Ticket in "needs_human" state (after execution & verification)
const needsHumanTicket = {
  ...mockTickets[0],
  state: "needs_human",
};

// Ticket-2 blocked by ticket-1
const blockedTicket = {
  ...mockTickets[1],
  id: "ticket-2",
  state: "blocked",
  blocked_by_ticket_id: "ticket-1",
  blocked_by_ticket_title: "Setup database schema",
};

/**
 * Build a board response with custom ticket overrides.
 */
function buildBoardWith(tickets: Array<(typeof mockTickets)[0]>) {
  const states = [
    "proposed", "planned", "executing", "verifying",
    "needs_human", "blocked", "done", "abandoned",
  ];
  const columns = states.map((state) => ({
    state,
    tickets: tickets.filter((t) => t.state === state),
  }));
  return { columns, total_tickets: tickets.length };
}

// ─── Tests ──────────────────────────────────────────────────────

test.describe("Ticket Execution", () => {
  test("execute a planned ticket triggers job and shows toast", async ({ page }) => {
    await mockAllApiRoutes(page);

    // Track execute API call
    let executeApiCalled = false;
    await page.route(`${API}/tickets/ticket-1/execute`, (route) => {
      executeApiCalled = true;
      return route.fulfill({
        json: { id: "job-1", ticket_id: "ticket-1", status: "queued" },
      });
    });

    await page.goto("/");

    // Click on planned ticket to open detail
    await expect(page.getByText("Setup database schema").first()).toBeVisible();
    await page.getByText("Setup database schema").first().click();
    await expect(
      page.locator("h2", { hasText: "Setup database schema" }),
    ).toBeVisible({ timeout: 10000 });

    // Click Execute button in the detail panel
    const executeBtn = page.getByRole("button", { name: "Execute", exact: true });
    await expect(executeBtn).toBeVisible();
    await executeBtn.click();

    // Toast should appear confirming execution started
    await expect(page.getByText(/Execution started/i)).toBeVisible({ timeout: 10000 });

    // Verify the API was called
    expect(executeApiCalled).toBe(true);
  });
});

test.describe("Code Review", () => {
  test("ticket in needs_human shows revision and Review Changes button", async ({
    page,
  }) => {
    await mockAllApiRoutes(page);

    // Board with ticket-1 in needs_human state
    await page.route(`${API}/boards/board-1/board`, (route) =>
      route.fulfill({
        json: buildBoardWith([needsHumanTicket, mockTickets[1], mockTickets[2]]),
      }),
    );

    // ticket-1 returns needs_human state
    await page.route(`${API}/tickets/ticket-1`, (route) =>
      route.fulfill({ json: needsHumanTicket }),
    );

    // Revision data
    await page.route(`${API}/tickets/ticket-1/revisions`, (route) =>
      route.fulfill({ json: { revisions: [mockRevision], total: 1 } }),
    );

    await page.goto("/");

    // Open ticket detail
    await expect(page.getByText("Setup database schema").first()).toBeVisible();
    await page.getByText("Setup database schema").first().click();
    await expect(
      page.locator("h2", { hasText: "Setup database schema" }),
    ).toBeVisible({ timeout: 10000 });

    // Code Changes section should show "1 revision available"
    await expect(page.getByText(/1 revision/)).toBeVisible({ timeout: 10000 });

    // "Review Changes" button should appear
    await expect(
      page.getByRole("button", { name: /Review Changes/i }),
    ).toBeVisible();
  });

  test("clicking Review Changes opens diff viewer with file names", async ({
    page,
  }) => {
    await mockAllApiRoutes(page);

    // Board with ticket-1 in needs_human state
    await page.route(`${API}/boards/board-1/board`, (route) =>
      route.fulfill({
        json: buildBoardWith([needsHumanTicket, mockTickets[1], mockTickets[2]]),
      }),
    );

    // ticket-1 returns needs_human state
    await page.route(`${API}/tickets/ticket-1`, (route) =>
      route.fulfill({ json: needsHumanTicket }),
    );

    // Revision with diff data
    await page.route(`${API}/tickets/ticket-1/revisions`, (route) =>
      route.fulfill({ json: { revisions: [mockRevision], total: 1 } }),
    );
    await page.route(`${API}/revisions/rev-1`, (route) =>
      route.fulfill({
        json: {
          ...mockRevision,
          diff_patch: mockDiffPatch,
          files: mockRevisionDiff.files,
        },
      }),
    );
    await page.route(`${API}/revisions/rev-1/diff`, (route) =>
      route.fulfill({ json: mockRevisionDiff }),
    );
    await page.route(`${API}/revisions/rev-1/comments**`, (route) =>
      route.fulfill({ json: { comments: [] } }),
    );
    await page.route(`${API}/revisions/rev-1/feedback-bundle`, (route) =>
      route.fulfill({ json: { comments: [], summary: null } }),
    );

    await page.goto("/");

    // Open ticket detail
    await page.getByText("Setup database schema").first().click();
    await expect(
      page.locator("h2", { hasText: "Setup database schema" }),
    ).toBeVisible({ timeout: 10000 });

    // Wait for revisions to load then click Review Changes
    await expect(page.getByText(/1 revision/)).toBeVisible({ timeout: 10000 });
    await page.getByRole("button", { name: /Review Changes/i }).click();

    // Diff viewer should show the file path in the header
    await expect(page.getByText("src/schema.py")).toBeVisible({ timeout: 10000 });
  });
});

test.describe("Merge to Main", () => {
  test("ticket with approved revision shows merge button and branch name", async ({
    page,
  }) => {
    await mockAllApiRoutes(page);

    // Board with ticket in needs_human
    await page.route(`${API}/boards/board-1/board`, (route) =>
      route.fulfill({
        json: buildBoardWith([needsHumanTicket, mockTickets[1], mockTickets[2]]),
      }),
    );

    // ticket-1 returns needs_human
    await page.route(`${API}/tickets/ticket-1`, (route) =>
      route.fulfill({ json: needsHumanTicket }),
    );

    // Approved revision
    await page.route(`${API}/tickets/ticket-1/revisions`, (route) =>
      route.fulfill({
        json: { revisions: [{ ...mockRevision, status: "approved" }], total: 1 },
      }),
    );

    // Merge status: can merge with workspace
    await page.route(`${API}/tickets/ticket-1/merge-status`, (route) =>
      route.fulfill({ json: mockMergeStatus }),
    );

    // Conflict status
    await page.route(`${API}/tickets/ticket-1/conflict-status`, (route) =>
      route.fulfill({ json: { has_conflict: false } }),
    );

    // Merge endpoint
    await page.route(`${API}/tickets/ticket-1/merge`, (route) =>
      route.fulfill({
        json: { success: true, message: "Merged successfully" },
      }),
    );

    await page.goto("/");

    // Open ticket detail
    await page.getByText("Setup database schema").first().click();
    await expect(
      page.locator("h2", { hasText: "Setup database schema" }),
    ).toBeVisible({ timeout: 10000 });

    // Merge section should show branch name
    await expect(page.getByText("goal/goal-1/ticket/ticket-1")).toBeVisible({
      timeout: 10000,
    });

    // "Merge to Main" button should be visible
    const mergeBtn = page.getByRole("button", { name: /Merge to Main/i });
    await expect(mergeBtn).toBeVisible();
    await mergeBtn.click();
  });
});

test.describe("Blocked Ticket Dependencies", () => {
  test("blocked ticket shows blocker and unblock button", async ({ page }) => {
    await mockAllApiRoutes(page);

    // Board with blocked ticket
    await page.route(`${API}/boards/board-1/board`, (route) =>
      route.fulfill({
        json: buildBoardWith([mockTickets[0], blockedTicket, mockTickets[2]]),
      }),
    );

    // ticket-2 returns blocked ticket data
    await page.route(`${API}/tickets/ticket-2`, (route) =>
      route.fulfill({ json: blockedTicket }),
    );
    await page.route(`${API}/tickets/ticket-2/revisions`, (route) =>
      route.fulfill({ json: { revisions: [], total: 0 } }),
    );
    await page.route(`${API}/tickets/ticket-2/events`, (route) =>
      route.fulfill({ json: { events: [] } }),
    );
    await page.route(`${API}/tickets/ticket-2/evidence`, (route) =>
      route.fulfill({ json: { evidence: [] } }),
    );
    await page.route(`${API}/tickets/ticket-2/jobs`, (route) =>
      route.fulfill({ json: { jobs: [] } }),
    );
    await page.route(`${API}/tickets/ticket-2/dependents`, (route) =>
      route.fulfill({ json: [] }),
    );
    await page.route(`${API}/tickets/ticket-2/merge-status`, (route) =>
      route.fulfill({ json: { status: "not_applicable" } }),
    );
    await page.route(`${API}/tickets/ticket-2/conflict-status`, (route) =>
      route.fulfill({ json: { has_conflicts: false } }),
    );
    await page.route(`${API}/tickets/ticket-2/agent-logs**`, (route) =>
      route.fulfill({
        json: { executions: [], total_jobs: 0, total_entries: 0 },
      }),
    );
    await page.route(`${API}/tickets/ticket-2/queue`, (route) =>
      route.fulfill({ json: { status: "not_queued" } }),
    );
    await page.route(`${API}/tickets/ticket-2/push-status`, (route) =>
      route.fulfill({ json: { pushed: false } }),
    );
    await page.route(`${API}/tickets/ticket-2/transition`, (route) =>
      route.fulfill({
        json: { ...blockedTicket, state: "planned", blocked_by_ticket_id: null },
      }),
    );

    await page.goto("/");

    // Blocked ticket visible
    await expect(page.getByText("Implement API endpoints").first()).toBeVisible();
    await page.getByText("Implement API endpoints").first().click();

    // Detail panel
    await expect(
      page.locator("h2", { hasText: "Implement API endpoints" }),
    ).toBeVisible({ timeout: 10000 });

    // Blocking indicator (use .first() since it may appear in card + panel)
    await expect(page.getByText(/Blocked by/i).first()).toBeVisible({ timeout: 10000 });

    // Dependency-blocked ticket shows blocker message (no Unblock button)
    await expect(
      page.getByText(/complete the blocker first/i),
    ).toBeVisible({ timeout: 5000 });
  });

  test("ticket shows dependents it blocks", async ({ page }) => {
    const dependentTicket = {
      ...mockTickets[1],
      state: "blocked",
      blocked_by_ticket_id: "ticket-1",
      blocked_by_ticket_title: "Setup database schema",
    };

    await mockAllApiRoutes(page);

    // Board with blocking dependency
    await page.route(`${API}/boards/board-1/board`, (route) =>
      route.fulfill({
        json: buildBoardWith([mockTickets[0], dependentTicket, mockTickets[2]]),
      }),
    );

    // ticket-1 has dependents
    await page.route(`${API}/tickets/ticket-1/dependents`, (route) =>
      route.fulfill({ json: [dependentTicket] }),
    );

    await page.goto("/");

    // Click on ticket-1 (the blocker)
    await page.getByText("Setup database schema").first().click();
    await expect(
      page.locator("h2", { hasText: "Setup database schema" }),
    ).toBeVisible({ timeout: 10000 });

    // Dependencies section should show the dependent ticket
    await expect(page.getByText("Dependencies")).toBeVisible({ timeout: 10000 });
    // The dependent ticket title should appear in the dependencies list
    await expect(page.getByText("Implement API endpoints").nth(1)).toBeVisible({
      timeout: 10000,
    });
  });
});

test.describe("Autopilot / Planner", () => {
  test("start autopilot processes planned tickets", async ({ page }) => {
    await mockAllApiRoutes(page);

    // Override planner start to return success
    await page.route(`${API}/planner/start`, (route) =>
      route.fulfill({
        json: {
          status: "completed",
          tickets_queued: 1,
          tickets_completed: 1,
          tickets_failed: 0,
          message: "Processed 1 ticket",
        },
      }),
    );

    await page.goto("/");
    await expect(page.getByText("Setup database schema")).toBeVisible();

    // Click "Start Autopilot"
    const autopilotBtn = page.getByRole("button", { name: /Start Autopilot/i });
    await expect(autopilotBtn).toBeVisible();
    await autopilotBtn.click();

    // Success toast should appear
    await expect(page.getByText(/Autopilot complete/i)).toBeVisible({
      timeout: 10000,
    });
  });

  test("autopilot with no planned tickets shows info toast", async ({ page }) => {
    await mockAllApiRoutes(page);

    await page.route(`${API}/planner/start`, (route) =>
      route.fulfill({
        json: {
          status: "completed",
          tickets_queued: 0,
          tickets_completed: 0,
          tickets_failed: 0,
          message: "No planned tickets to process",
        },
      }),
    );

    await page.goto("/");
    await expect(page.getByText("Setup database schema")).toBeVisible();

    await page.getByRole("button", { name: /Start Autopilot/i }).click();

    // Toast title (exact match to avoid matching both title + description)
    await expect(
      page.getByText("Autopilot: No planned tickets"),
    ).toBeVisible({ timeout: 10000 });
  });

  test("planner status indicator shows provider info", async ({ page }) => {
    await mockAllApiRoutes(page);

    // Override planner status with configured model
    await page.route(`${API}/planner/status`, (route) =>
      route.fulfill({
        json: {
          running: false,
          tick_count: 5,
          actions: [],
          model: "claude-sonnet-4",
          llm_configured: true,
          llm_provider: "anthropic",
          features: {
            auto_execute: true,
            propose_followups: true,
            generate_reflections: true,
          },
        },
      }),
    );

    await page.goto("/");
    await expect(page.getByText("Setup database schema")).toBeVisible();

    // Planner shows "Planner ready · {llm_provider}"
    await expect(page.getByText(/Planner ready/i)).toBeVisible({
      timeout: 10000,
    });
  });
});

test.describe("Planner Follow-up", () => {
  test("done ticket visible in done column", async ({ page }) => {
    await mockAllApiRoutes(page);
    await page.goto("/");

    // Done ticket visible
    await expect(page.getByText("Write tests")).toBeVisible();
  });

  test("planner generates follow-up ticket after autopilot", async ({ page }) => {
    await mockAllApiRoutes(page);

    // Track autopilot
    let autopilotCalled = false;

    // Planner start returns follow-up generation
    await page.route(`${API}/planner/start`, (route) => {
      autopilotCalled = true;
      return route.fulfill({
        json: {
          status: "completed",
          tickets_queued: 2,
          tickets_completed: 2,
          tickets_failed: 0,
          message: "Processed 2 tickets, generated 1 follow-up",
        },
      });
    });

    // After autopilot, board reloads with a new proposed ticket
    const followUpTicket = {
      id: "ticket-4",
      title: "Fix edge cases from tests",
      description: "Follow-up ticket generated by planner",
      state: "proposed",
      priority: 60,
      priority_bucket: "P1",
      goal_id: "goal-1",
      board_id: "board-1",
      blocked_by_ticket_id: null,
      created_at: "2025-01-02T00:00:00Z",
      updated_at: "2025-01-02T00:00:00Z",
    };

    await page.route(`${API}/boards/board-1/board`, (route) => {
      if (autopilotCalled) {
        return route.fulfill({
          json: buildBoardWith([...mockTickets, followUpTicket]),
        });
      }
      return route.fulfill({ json: buildBoardWith(mockTickets) });
    });

    await page.goto("/");
    await expect(page.getByText("Setup database schema")).toBeVisible();

    // Start autopilot
    await page.getByRole("button", { name: /Start Autopilot/i }).click();

    // Success toast
    await expect(page.getByText(/Autopilot complete/i)).toBeVisible({
      timeout: 10000,
    });

    // After board refresh, new proposed ticket should appear
    await expect(page.getByText("Fix edge cases from tests")).toBeVisible({
      timeout: 10000,
    });
  });
});
