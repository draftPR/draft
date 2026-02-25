import type { Page } from "@playwright/test";

export const mockBoard = {
  id: "board-1",
  name: "Test Board",
  description: "A test board",
  repo_root: "/tmp/test-repo",
  default_branch: "main",
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

export const mockGoal = {
  id: "goal-1",
  title: "Test Goal",
  description: "A test goal",
  board_id: "board-1",
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
  ticket_count: 3,
  done_count: 1,
  cost_budget_cents: null,
  cost_spent_cents: 0,
  max_auto_tickets: 10,
  max_concurrent_tickets: 1,
  autonomy_level: "supervised",
};

export const mockTickets = [
  {
    id: "ticket-1",
    title: "Setup database schema",
    description: "Create initial DB schema",
    state: "planned",
    priority: 90,
    priority_bucket: "P0",
    goal_id: "goal-1",
    board_id: "board-1",
    blocked_by_ticket_id: null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
  {
    id: "ticket-2",
    title: "Implement API endpoints",
    description: "Build REST API",
    state: "executing",
    priority: 70,
    priority_bucket: "P1",
    goal_id: "goal-1",
    board_id: "board-1",
    blocked_by_ticket_id: null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
  {
    id: "ticket-3",
    title: "Write tests",
    description: "Add test coverage",
    state: "done",
    priority: 50,
    priority_bucket: "P2",
    goal_id: "goal-1",
    board_id: "board-1",
    blocked_by_ticket_id: null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
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
  const columns = states.map((state) => ({
    state,
    tickets: mockTickets.filter((t) => t.state === state),
  }));
  return { columns, total_tickets: mockTickets.length };
}

/** Backend API base URL used by the frontend */
const API = "http://localhost:8000";

/**
 * Set up all API route interceptions for E2E tests.
 * No real backend needed.
 *
 * IMPORTANT: Route patterns are scoped to localhost:8000 to avoid
 * intercepting Vite dev-server page navigations (e.g. /settings).
 */
export async function mockAllApiRoutes(page: Page) {
  // Health
  await page.route(`${API}/health`, (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );

  // Boards
  await page.route(`${API}/boards`, (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({ json: mockBoard, status: 201 });
    }
    return route.fulfill({ json: { boards: [mockBoard] } });
  });
  await page.route(`${API}/boards/board-1`, (route) =>
    route.fulfill({ json: mockBoard }),
  );
  await page.route(`${API}/boards/board-1/board`, (route) =>
    route.fulfill({ json: buildBoardResponse() }),
  );
  await page.route(`${API}/boards/board-1/config`, (route) =>
    route.fulfill({ json: {} }),
  );

  // Goals
  await page.route(`${API}/goals`, (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({ json: mockGoal, status: 201 });
    }
    return route.fulfill({ json: { goals: [mockGoal] } });
  });
  await page.route(`${API}/goals/goal-1`, (route) =>
    route.fulfill({ json: mockGoal }),
  );

  // Tickets
  await page.route(`${API}/tickets`, (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({ json: mockTickets[0], status: 201 });
    }
    return route.fulfill({ json: { tickets: mockTickets } });
  });
  await page.route(`${API}/tickets/ticket-**`, (route) => {
    const url = route.request().url();
    if (url.includes("/transition")) {
      return route.fulfill({ json: { ...mockTickets[0], state: "executing" } });
    }
    if (url.includes("/execute")) {
      return route.fulfill({
        json: { id: "job-1", ticket_id: "ticket-1", status: "queued" },
      });
    }
    if (url.includes("/events")) {
      return route.fulfill({ json: { events: [] } });
    }
    if (url.includes("/evidence")) {
      return route.fulfill({ json: { evidence: [] } });
    }
    if (url.includes("/revisions")) {
      return route.fulfill({ json: { revisions: [] } });
    }
    if (url.includes("/jobs")) {
      return route.fulfill({ json: { jobs: [] } });
    }
    if (url.includes("/dependents")) {
      return route.fulfill({ json: [] });
    }
    if (url.includes("/merge-status")) {
      return route.fulfill({ json: { status: "not_applicable" } });
    }
    if (url.includes("/conflict-status")) {
      return route.fulfill({ json: { has_conflicts: false } });
    }
    if (url.includes("/agent-logs")) {
      return route.fulfill({
        json: { executions: [], total_jobs: 0, total_entries: 0 },
      });
    }
    if (url.includes("/queue")) {
      return route.fulfill({ json: { status: "not_queued" } });
    }
    if (url.includes("/push-status")) {
      return route.fulfill({ json: { pushed: false } });
    }
    if (route.request().method() === "DELETE") {
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ json: mockTickets[0] });
  });

  // Queue
  await page.route(`${API}/jobs/queue`, (route) =>
    route.fulfill({
      json: { queued: [], running: [], total_queued: 0, total_running: 0 },
    }),
  );

  // Executors
  await page.route(`${API}/executors/available`, (route) =>
    route.fulfill({
      json: [
        { name: "claude", display_name: "Claude Code", available: true },
      ],
    }),
  );
  await page.route(`${API}/executors/profiles`, (route) =>
    route.fulfill({ json: [] }),
  );

  // Planner
  await page.route(`${API}/planner/status`, (route) =>
    route.fulfill({ json: { running: false, tick_count: 0, actions: [] } }),
  );
  await page.route(`${API}/planner/start`, (route) =>
    route.fulfill({ json: { message: "started" } }),
  );

  // Settings
  await page.route(`${API}/settings`, (route) =>
    route.fulfill({ json: {} }),
  );
  await page.route(`${API}/settings/planner`, (route) =>
    route.fulfill({ json: {} }),
  );
  await page.route(`${API}/settings/planner/check`, (route) =>
    route.fulfill({ json: { healthy: true } }),
  );

  // Vite wake endpoint (this one stays as glob since it's on the Vite server)
  await page.route("**/__api/wake-backend", (route) =>
    route.fulfill({ json: { ok: true } }),
  );

  // Dismiss the welcome walkthrough by setting localStorage
  await page.addInitScript(() => {
    localStorage.setItem("smart-kanban-walkthrough-completed", "1.0");
  });
}
