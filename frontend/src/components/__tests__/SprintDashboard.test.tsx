import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { SprintDashboard } from "@/components/SprintDashboard";

const mockDashboardData = {
  budget: {
    daily_budget: 10,
    daily_spent: 3.5,
    daily_remaining: 6.5,
    weekly_budget: 50,
    weekly_spent: 12,
    weekly_remaining: 38,
    monthly_budget: 150,
    monthly_spent: 45,
    monthly_remaining: 105,
    is_over_budget: false,
    warning_threshold_reached: false,
  },
  sprint: {
    total_tickets: 20,
    completed_tickets: 8,
    in_progress_tickets: 3,
    blocked_tickets: 2,
    completion_rate: 40,
    avg_cycle_time_hours: 2.5,
    velocity: 1.5,
  },
  agent: {
    total_sessions: 15,
    successful_sessions: 12,
    success_rate: 80,
    avg_turns_per_session: 5.2,
    most_used_agent: "claude",
    total_cost_usd: 45,
  },
  cost_trend: [
    { date: "Mon", cost: 5 },
    { date: "Tue", cost: 3 },
    { date: "Wed", cost: 7 },
  ],
};

const mockFetchDashboard = vi.fn().mockResolvedValue(mockDashboardData);

vi.mock("@/services/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/services/api")>();
  return {
    ...original,
    fetchDashboard: (...args: unknown[]) => mockFetchDashboard(...args),
  };
});

describe("SprintDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchDashboard.mockResolvedValue(mockDashboardData);
  });

  it("renders the Sprint Dashboard heading", () => {
    render(<SprintDashboard />);
    expect(screen.getByText("Sprint Dashboard")).toBeInTheDocument();
  });

  it("renders Budget Status card", async () => {
    render(<SprintDashboard />);

    await waitFor(() => {
      expect(screen.getByText("Budget Status")).toBeInTheDocument();
    });
  });

  it("renders Sprint Progress card", async () => {
    render(<SprintDashboard />);

    await waitFor(() => {
      expect(screen.getByText("Sprint Progress")).toBeInTheDocument();
    });
  });

  it("renders Velocity & Efficiency card", async () => {
    render(<SprintDashboard />);

    await waitFor(() => {
      expect(
        screen.getByText("Velocity & Efficiency")
      ).toBeInTheDocument();
    });
  });

  it("renders Cost Trend chart", async () => {
    render(<SprintDashboard />);

    await waitFor(() => {
      expect(screen.getByText("Cost Trend (7 days)")).toBeInTheDocument();
    });
  });

  it("displays budget amounts", async () => {
    render(<SprintDashboard />);

    await waitFor(() => {
      expect(screen.getByText("$3.50 / $10")).toBeInTheDocument();
    });
  });

  it("displays sprint completion rate", async () => {
    render(<SprintDashboard />);

    await waitFor(() => {
      expect(screen.getByText("40%")).toBeInTheDocument();
    });
  });

  it("displays ticket counts", async () => {
    render(<SprintDashboard />);

    await waitFor(() => {
      expect(screen.getByText("8/20")).toBeInTheDocument();
      expect(screen.getByText("tickets completed")).toBeInTheDocument();
    });
  });

  it("displays velocity", async () => {
    render(<SprintDashboard />);

    await waitFor(() => {
      expect(screen.getByText("1.5")).toBeInTheDocument();
      expect(screen.getByText("tickets/day")).toBeInTheDocument();
    });
  });

  it("displays agent success rate", async () => {
    render(<SprintDashboard />);

    await waitFor(() => {
      expect(screen.getByText("80%")).toBeInTheDocument();
      expect(screen.getByText("agent success")).toBeInTheDocument();
    });
  });

  it("shows error state when API fails", async () => {
    mockFetchDashboard.mockRejectedValueOnce(new Error("Server error"));

    render(<SprintDashboard />);

    await waitFor(() => {
      expect(screen.getByText("Server error")).toBeInTheDocument();
    });
  });
});
