import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { GoalDetailDialog } from "../GoalDetailDialog";

const BASE = "http://localhost:8000";

// Mock child dialog components to keep tests focused
vi.mock("../ReflectionDialog", () => ({
  ReflectionDialog: () => null,
}));

vi.mock("../TicketGenerationProgress", () => ({
  TicketGenerationProgress: () => null,
}));

vi.mock("../ProposedTicketsReview", () => ({
  ProposedTicketsReview: () => null,
}));

// Add GET /goals/:goalId handler since it's not in default handlers
beforeEach(() => {
  server.use(
    http.get(`${BASE}/goals/:goalId`, () =>
      HttpResponse.json({
        id: "goal-1",
        board_id: "board-1",
        title: "Test Goal Title",
        description: "A detailed goal description",
        created_at: "2025-06-15T10:30:00Z",
        updated_at: "2025-06-15T10:30:00Z",
        autonomy_enabled: false,
        auto_approve_tickets: false,
        auto_approve_revisions: false,
        auto_merge: false,
        auto_approve_followups: false,
        max_auto_approvals: null,
        auto_approval_count: 0,
        ticket_count: 0,
        done_count: 0,
        cost_budget_cents: null,
        cost_spent_cents: 0,
        max_auto_tickets: 10,
        max_concurrent_tickets: 1,
        autonomy_level: "supervised",
      }),
    ),
  );
});

describe("GoalDetailDialog", () => {
  const defaultProps = {
    goalId: "goal-1",
    open: true,
    onOpenChange: vi.fn(),
    onTicketsAccepted: vi.fn(),
  };

  it("renders dialog and loads goal details", async () => {
    render(<GoalDetailDialog {...defaultProps} />);

    // Initially shows loading
    expect(screen.getByText("Loading...")).toBeInTheDocument();

    // After fetch completes, show goal title
    await waitFor(() => {
      expect(screen.getByText("Test Goal Title")).toBeInTheDocument();
    });
  });

  it("does not render when goalId is null", () => {
    render(
      <GoalDetailDialog {...defaultProps} goalId={null} />,
    );

    // Component returns null when goalId is null
    expect(screen.queryByText("Goal Details")).not.toBeInTheDocument();
    expect(screen.queryByText("Loading...")).not.toBeInTheDocument();
  });

  it("does not render dialog content when closed", () => {
    render(<GoalDetailDialog {...defaultProps} open={false} />);

    expect(screen.queryByText("Loading...")).not.toBeInTheDocument();
  });

  it("shows goal description after loading", async () => {
    render(<GoalDetailDialog {...defaultProps} />);

    await waitFor(() => {
      expect(
        screen.getByText("A detailed goal description"),
      ).toBeInTheDocument();
    });

    expect(screen.getByText("Description")).toBeInTheDocument();
  });

  it("shows creation date after loading", async () => {
    render(<GoalDetailDialog {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText(/Created Jun 15, 2025/)).toBeInTheDocument();
    });
  });

  it("shows Generate Tickets and Reflect buttons", async () => {
    render(<GoalDetailDialog {...defaultProps} />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Generate Tickets/ }),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByRole("button", { name: /Reflect/ }),
    ).toBeInTheDocument();
  });

  it("shows AI Ticket Generation section", async () => {
    render(<GoalDetailDialog {...defaultProps} />);

    await waitFor(() => {
      expect(
        screen.getByText("AI Ticket Generation"),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText(/Use AI to analyze this goal/),
    ).toBeInTheDocument();
  });

  it("shows error state when fetch fails", async () => {
    server.use(
      http.get(`${BASE}/goals/:goalId`, () =>
        HttpResponse.json(
          { detail: "Goal not found" },
          { status: 404 },
        ),
      ),
    );

    render(<GoalDetailDialog {...defaultProps} />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Try Again" }),
      ).toBeInTheDocument();
    });
  });

  it("shows autonomy section when goal has autonomy enabled", async () => {
    server.use(
      http.get(`${BASE}/goals/:goalId`, () =>
        HttpResponse.json({
          id: "goal-1",
          board_id: "board-1",
          title: "Autonomous Goal",
          description: null,
          created_at: "2025-06-15T10:30:00Z",
          updated_at: "2025-06-15T10:30:00Z",
          autonomy_enabled: true,
          auto_approve_tickets: true,
          auto_approve_revisions: true,
          auto_merge: true,
          auto_approve_followups: false,
          max_auto_approvals: 10,
          auto_approval_count: 3,
          ticket_count: 5,
          done_count: 2,
          cost_budget_cents: null,
          cost_spent_cents: 0,
          max_auto_tickets: 10,
          max_concurrent_tickets: 1,
          autonomy_level: "supervised",
        }),
      ),
    );

    render(<GoalDetailDialog {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Autonomy Active")).toBeInTheDocument();
    });

    expect(screen.getByText(/3 auto-actions/)).toBeInTheDocument();
  });
});
