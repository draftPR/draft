/**
 * Demo recording script — walks through key Alma Kanban features
 * with human-like pacing for a README video/GIF.
 *
 * Run with:
 *   npx playwright test e2e/demo-recording.spec.ts --project demo
 *
 * Output: frontend/demo-output/video/
 */
import { test, expect, type Page } from "@playwright/test";

// ---------- Rich mock data for an appealing demo ----------

const mockBoard = {
  id: "board-1",
  name: "alma-calculator",
  description: "Calculator microservice — add, subtract, multiply, divide",
  repo_root: "/home/dev/alma-calculator",
  default_branch: "main",
  created_at: "2025-06-10T09:00:00Z",
  updated_at: "2025-06-12T14:30:00Z",
};

const mockGoals = [
  {
    id: "goal-1",
    title: "Implement core arithmetic operations",
    description:
      "Build the core calculator engine supporting addition, subtraction, multiplication, and division with proper error handling.",
    board_id: "board-1",
    created_at: "2025-06-10T09:00:00Z",
    updated_at: "2025-06-12T14:30:00Z",
    ticket_count: 8,
    done_count: 3,
    cost_budget_cents: 5000,
    cost_spent_cents: 1850,
    max_auto_tickets: 15,
    max_concurrent_tickets: 2,
    autonomy_level: "supervised",
  },
  {
    id: "goal-2",
    title: "Add REST API and documentation",
    description:
      "Expose calculator operations via a REST API with OpenAPI docs, input validation, and rate limiting.",
    board_id: "board-1",
    created_at: "2025-06-11T10:00:00Z",
    updated_at: "2025-06-12T11:00:00Z",
    ticket_count: 4,
    done_count: 0,
    cost_budget_cents: 3000,
    cost_spent_cents: 0,
    max_auto_tickets: 10,
    max_concurrent_tickets: 1,
    autonomy_level: "autonomous",
  },
];

const mockTickets = [
  // Proposed
  {
    id: "ticket-8",
    title: "Add percentage calculation support",
    description: "Support percentage operations (e.g. 15% of 200).",
    state: "proposed",
    priority: 40,
    priority_bucket: "P2",
    goal_id: "goal-1",
    board_id: "board-1",
    blocked_by_ticket_id: null,
    created_at: "2025-06-12T14:00:00Z",
    updated_at: "2025-06-12T14:00:00Z",
  },
  // Planned
  {
    id: "ticket-4",
    title: "Implement multiply and divide functions",
    description:
      "Create multiply() and divide() in calculator.py with decimal precision handling and division-by-zero guard.",
    state: "planned",
    priority: 90,
    priority_bucket: "P0",
    goal_id: "goal-1",
    board_id: "board-1",
    blocked_by_ticket_id: null,
    created_at: "2025-06-10T09:10:00Z",
    updated_at: "2025-06-12T08:00:00Z",
  },
  {
    id: "ticket-5",
    title: "Create REST API endpoint for calculations",
    description:
      "Build POST /calculate endpoint accepting operation type and operands, returning JSON result.",
    state: "planned",
    priority: 70,
    priority_bucket: "P1",
    goal_id: "goal-2",
    board_id: "board-1",
    blocked_by_ticket_id: "ticket-4",
    blocked_by_ticket_title: "Implement multiply and divide functions",
    created_at: "2025-06-11T10:05:00Z",
    updated_at: "2025-06-12T08:00:00Z",
  },
  // Executing
  {
    id: "ticket-6",
    title: "Add input validation and error handling",
    description:
      "Validate numeric inputs, handle overflow, and return structured error responses.",
    state: "executing",
    priority: 80,
    priority_bucket: "P0",
    goal_id: "goal-2",
    board_id: "board-1",
    blocked_by_ticket_id: null,
    created_at: "2025-06-11T10:10:00Z",
    updated_at: "2025-06-12T13:45:00Z",
  },
  // Verifying
  {
    id: "ticket-7",
    title: "Write unit tests for add and subtract",
    description:
      "Add pytest tests covering normal cases, edge cases (zero, negatives), and floating point precision.",
    state: "verifying",
    priority: 75,
    priority_bucket: "P1",
    goal_id: "goal-1",
    board_id: "board-1",
    blocked_by_ticket_id: null,
    created_at: "2025-06-10T09:20:00Z",
    updated_at: "2025-06-12T14:00:00Z",
  },
  // Needs Review
  {
    id: "ticket-3",
    title: "Implement subtract function",
    description:
      "Create subtract() function with support for negative results and floating point numbers.",
    state: "needs_human",
    priority: 85,
    priority_bucket: "P0",
    goal_id: "goal-1",
    board_id: "board-1",
    blocked_by_ticket_id: null,
    created_at: "2025-06-10T09:08:00Z",
    updated_at: "2025-06-12T12:30:00Z",
  },
  // Done
  {
    id: "ticket-1",
    title: "Create project scaffolding with pyproject.toml",
    description:
      "Initialize Python project structure: src/, tests/, pyproject.toml with ruff + pytest config.",
    state: "done",
    priority: 95,
    priority_bucket: "P0",
    goal_id: "goal-1",
    board_id: "board-1",
    blocked_by_ticket_id: null,
    created_at: "2025-06-10T09:00:00Z",
    updated_at: "2025-06-11T10:00:00Z",
  },
  {
    id: "ticket-2",
    title: "Implement add function in calculator module",
    description:
      "Create calculator.py with add() supporting integers and floats, with type hints and docstrings.",
    state: "done",
    priority: 90,
    priority_bucket: "P0",
    goal_id: "goal-1",
    board_id: "board-1",
    blocked_by_ticket_id: null,
    created_at: "2025-06-10T09:05:00Z",
    updated_at: "2025-06-11T14:00:00Z",
  },
  {
    id: "ticket-9",
    title: "Set up CI pipeline with GitHub Actions",
    description:
      "Configure .github/workflows/ci.yml with lint, type-check, and test steps.",
    state: "done",
    priority: 60,
    priority_bucket: "P1",
    goal_id: "goal-1",
    board_id: "board-1",
    blocked_by_ticket_id: null,
    created_at: "2025-06-10T09:25:00Z",
    updated_at: "2025-06-12T09:00:00Z",
  },
];

function buildBoardResponse() {
  const states = [
    "proposed",
    "planned",
    "executing",
    "verifying",
    "needs_human",
    "blocked",
    "done",
    "abandoned",
  ];
  return {
    columns: states.map((state) => ({
      state,
      tickets: mockTickets.filter((t) => t.state === state),
    })),
    total_tickets: mockTickets.length,
  };
}

const API = "http://localhost:8000";

async function setupDemoMocks(page: Page) {
  await page.route(`${API}/health`, (r) =>
    r.fulfill({ json: { status: "ok" } }),
  );
  await page.route(`${API}/boards`, (r) => {
    if (r.request().method() === "POST")
      return r.fulfill({ json: mockBoard, status: 201 });
    return r.fulfill({ json: { boards: [mockBoard] } });
  });
  await page.route(`${API}/boards/board-1`, (r) =>
    r.fulfill({ json: mockBoard }),
  );
  await page.route(`${API}/boards/board-1/board`, (r) =>
    r.fulfill({ json: buildBoardResponse() }),
  );
  await page.route(`${API}/boards/board-1/config`, (r) =>
    r.fulfill({ json: {} }),
  );
  await page.route(`${API}/goals`, (r) => {
    if (r.request().method() === "POST")
      return r.fulfill({ json: mockGoals[0], status: 201 });
    return r.fulfill({ json: { goals: mockGoals } });
  });
  await page.route(`${API}/goals/goal-**`, (r) =>
    r.fulfill({ json: mockGoals[0] }),
  );
  await page.route(`${API}/tickets`, (r) => {
    if (r.request().method() === "POST")
      return r.fulfill({ json: mockTickets[1], status: 201 });
    return r.fulfill({ json: { tickets: mockTickets } });
  });
  await page.route(`${API}/tickets/ticket-**`, (r) => {
    const url = r.request().url();
    if (url.includes("/events"))
      return r.fulfill({ json: { events: [] } });
    if (url.includes("/evidence"))
      return r.fulfill({ json: { evidence: [] } });
    if (url.includes("/revisions"))
      return r.fulfill({ json: { revisions: [] } });
    if (url.includes("/jobs"))
      return r.fulfill({ json: { jobs: [] } });
    if (url.includes("/dependents"))
      return r.fulfill({ json: [] });
    if (url.includes("/merge-status"))
      return r.fulfill({ json: { status: "not_applicable" } });
    if (url.includes("/conflict-status"))
      return r.fulfill({ json: { has_conflicts: false } });
    if (url.includes("/agent-logs"))
      return r.fulfill({
        json: { executions: [], total_jobs: 0, total_entries: 0 },
      });
    if (url.includes("/queue"))
      return r.fulfill({ json: { status: "not_queued" } });
    if (url.includes("/push-status"))
      return r.fulfill({ json: { pushed: false } });
    if (url.includes("/transition"))
      return r.fulfill({ json: { ...mockTickets[1], state: "executing" } });
    if (url.includes("/execute"))
      return r.fulfill({
        json: { id: "job-1", ticket_id: "ticket-4", status: "queued" },
      });
    if (r.request().method() === "DELETE")
      return r.fulfill({ status: 204 });
    // Default: return the "multiply and divide" ticket for detail view
    return r.fulfill({ json: mockTickets[1] });
  });
  await page.route(`${API}/jobs/queue`, (r) =>
    r.fulfill({
      json: { queued: [], running: [], total_queued: 0, total_running: 0 },
    }),
  );
  await page.route(`${API}/executors/available`, (r) =>
    r.fulfill({
      json: [
        { name: "claude", display_name: "Claude Code", available: true },
        { name: "cursor_agent", display_name: "Cursor Agent", available: true },
      ],
    }),
  );
  await page.route(`${API}/executors/profiles`, (r) =>
    r.fulfill({ json: [] }),
  );
  await page.route(`${API}/planner/status`, (r) =>
    r.fulfill({ json: { running: false, tick_count: 0, actions: [] } }),
  );
  await page.route(`${API}/planner/start`, (r) =>
    r.fulfill({ json: { message: "started" } }),
  );
  await page.route(`${API}/settings`, (r) => r.fulfill({ json: {} }));
  await page.route(`${API}/settings/planner`, (r) =>
    r.fulfill({ json: {} }),
  );
  await page.route(`${API}/settings/planner/check`, (r) =>
    r.fulfill({ json: { healthy: true } }),
  );
  await page.route("**/__api/wake-backend", (r) =>
    r.fulfill({ json: { ok: true } }),
  );

  await page.addInitScript(() => {
    localStorage.setItem("smart-kanban-walkthrough-completed", "1.0");
  });
}

// Human-like pause
const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ---------- Demo scenario ----------

test("Alma Kanban — demo walkthrough", async ({ page }) => {
  test.setTimeout(120_000);
  await setupDemoMocks(page);

  // 1. Load the kanban board
  await page.goto("/");
  await expect(page.getByText("Implement multiply and divide functions").first()).toBeVisible();
  await pause(2500);

  // 2. Click a ticket to open the detail panel
  await page.getByText("Implement multiply and divide functions").first().first().click();
  await expect(
    page.locator("h2", { hasText: "Implement multiply and divide functions" }),
  ).toBeVisible({ timeout: 10000 });
  await pause(2500);

  // 3. Close the detail panel
  await page.keyboard.press("Escape");
  await pause(1000);

  // 4. Open Command Palette with Ctrl+K
  await page.keyboard.press("Control+k");
  await expect(page.getByText("Create New Ticket")).toBeVisible();
  await pause(1500);

  // 5. Type in the search to filter
  await page.keyboard.type("goal", { delay: 80 });
  await pause(1500);

  // 6. Close palette with Escape
  await page.keyboard.press("Escape");
  await pause(800);

  // 7. Open "New Goal" dialog
  await page.getByRole("button", { name: /New Goal/i }).click();
  await expect(
    page.getByRole("heading", { name: /Create New Goal/i }),
  ).toBeVisible();
  await pause(2000);

  // 8. Close goal dialog
  await page.keyboard.press("Escape");
  await pause(800);

  // 9. Open "New Ticket" dialog
  await page.getByRole("button", { name: /New Ticket/i }).click();
  await expect(
    page.getByRole("heading", { name: /Create New Ticket/i }),
  ).toBeVisible();
  await pause(2000);

  // 10. Close ticket dialog
  await page.keyboard.press("Escape");
  await pause(800);

  // 11. Open Goals list
  await page
    .locator("header")
    .getByRole("button", { name: /^Goals$/i })
    .click();
  await expect(
    page.getByText("Implement core arithmetic operations").first(),
  ).toBeVisible();
  await pause(2500);

  // 12. Close goals list
  await page.keyboard.press("Escape");
  await pause(800);

  // 13. Open keyboard shortcuts help with ?
  await page.keyboard.press("?");
  await expect(
    page.getByRole("heading", { name: /Keyboard Shortcuts/i }),
  ).toBeVisible();
  await pause(2500);

  // 14. Close help
  await page.keyboard.press("Escape");
  await pause(800);

  // 15. Navigate to settings
  await page.goto("/settings");
  await expect(
    page.getByRole("heading", { name: /Settings/i, level: 1 }),
  ).toBeVisible();
  await pause(2500);

  // 16. Navigate back to board
  await page.goto("/");
  await expect(page.getByText("Implement multiply and divide functions").first()).toBeVisible();
  await pause(2000);
});
