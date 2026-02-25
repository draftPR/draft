import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { TicketEvidence } from "@/components/TicketEvidence";
import type { TicketEvidence as TicketEvidenceData } from "@/hooks/useTicketEvidence";

// Mock the useTicketEvidence hook
vi.mock("@/hooks/useTicketEvidence", () => ({
  useTicketEvidence: vi.fn(),
}));

// Mock all child evidence components
vi.mock("@/components/evidence/PlanView", () => ({
  PlanView: () => <div data-testid="plan-view">PlanView</div>,
}));
vi.mock("@/components/evidence/ActionTimeline", () => ({
  ActionTimeline: () => <div data-testid="action-timeline">ActionTimeline</div>,
}));
vi.mock("@/components/evidence/DiffViewer", () => ({
  DiffViewer: () => <div data-testid="evidence-diff-viewer">DiffViewer</div>,
}));
vi.mock("@/components/evidence/TestResults", () => ({
  TestResults: () => <div data-testid="test-results">TestResults</div>,
}));
vi.mock("@/components/evidence/CostBreakdown", () => ({
  CostBreakdown: () => <div data-testid="cost-breakdown">CostBreakdown</div>,
}));
vi.mock("@/components/evidence/RollbackPlan", () => ({
  RollbackPlan: () => <div data-testid="rollback-plan">RollbackPlan</div>,
}));

import { useTicketEvidence } from "@/hooks/useTicketEvidence";

const mockEvidence = {
  plan: {
    description: "Fix the bug",
    approach: "Direct fix",
    files_to_modify: ["src/app.ts"],
    estimated_complexity: "low" as const,
  },
  actions: [],
  diffs: [],
  diff_stat: { total_files: 2, total_additions: 10, total_deletions: 5 },
  test_results: [{ name: "test1", status: "passed", duration_ms: 100 }],
  cost: {
    total_usd: 0.0025,
    input_tokens: 1000,
    output_tokens: 500,
    model: "claude-sonnet",
    provider: "anthropic",
  },
  rollback_steps: [],
};

describe("TicketEvidence", () => {
  it("renders loading state", () => {
    vi.mocked(useTicketEvidence).mockReturnValue({
      evidence: null,
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(<TicketEvidence ticketId="ticket-1" />);
    expect(screen.getByText("Loading evidence...")).toBeInTheDocument();
  });

  it("renders error state", () => {
    vi.mocked(useTicketEvidence).mockReturnValue({
      evidence: null,
      loading: false,
      error: "Network error",
      refetch: vi.fn(),
    });

    render(<TicketEvidence ticketId="ticket-1" />);
    expect(
      screen.getByText("Failed to load evidence: Network error"),
    ).toBeInTheDocument();
  });

  it("renders no evidence state", () => {
    vi.mocked(useTicketEvidence).mockReturnValue({
      evidence: null,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<TicketEvidence ticketId="ticket-1" />);
    expect(
      screen.getByText(/No evidence available for this ticket/),
    ).toBeInTheDocument();
  });

  it("renders evidence card with title and description", () => {
    vi.mocked(useTicketEvidence).mockReturnValue({
      evidence: mockEvidence as unknown as TicketEvidenceData,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<TicketEvidence ticketId="ticket-1" />);
    expect(screen.getByText("Ticket Evidence")).toBeInTheDocument();
    expect(
      screen.getByText(/Full transparency/),
    ).toBeInTheDocument();
  });

  it("renders badges for diff stats and test status", () => {
    vi.mocked(useTicketEvidence).mockReturnValue({
      evidence: mockEvidence as unknown as TicketEvidenceData,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<TicketEvidence ticketId="ticket-1" />);
    expect(screen.getByText("2 files changed")).toBeInTheDocument();
    expect(screen.getByText("Tests Passed")).toBeInTheDocument();
  });

  it("renders Tests Failed badge when tests fail", () => {
    const failingEvidence = {
      ...mockEvidence,
      test_results: [
        { name: "test1", status: "failed", duration_ms: 100 },
      ],
    };
    vi.mocked(useTicketEvidence).mockReturnValue({
      evidence: failingEvidence as unknown as TicketEvidenceData,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<TicketEvidence ticketId="ticket-1" />);
    expect(screen.getByText("Tests Failed")).toBeInTheDocument();
  });

  it("renders tab triggers", () => {
    vi.mocked(useTicketEvidence).mockReturnValue({
      evidence: mockEvidence as unknown as TicketEvidenceData,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<TicketEvidence ticketId="ticket-1" />);
    // Tab triggers include the icon + text
    expect(screen.getByText("Plan")).toBeInTheDocument();
    expect(screen.getByText("Actions")).toBeInTheDocument();
    expect(screen.getByText("Changes")).toBeInTheDocument();
    expect(screen.getByText("Tests")).toBeInTheDocument();
    expect(screen.getByText("Cost")).toBeInTheDocument();
    expect(screen.getByText("Rollback")).toBeInTheDocument();
  });
});
