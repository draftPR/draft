import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { TicketDetailPanel } from "@/components/TicketDetailPanel";
import { TicketState, STATE_DISPLAY_NAMES } from "@/types/api";

// Mock ticketStore
vi.mock("@/stores/ticketStore", () => ({
  useTicketSelectionStore: () => ({
    selectedTicketId: "ticket-1",
    detailDrawerOpen: true,
    selectTicket: vi.fn(),
    clearSelection: vi.fn(),
    setDetailDrawerOpen: vi.fn(),
  }),
}));

// Mock BoardContext
vi.mock("@/contexts/BoardContext", () => ({
  useBoard: () => ({
    currentBoard: {
      id: "board-1",
      name: "Test",
      repo_root: "/tmp",
      description: null,
      default_branch: "main",
      created_at: "",
      updated_at: "",
    },
    boards: [],
    isLoading: false,
    error: null,
    setCurrentBoard: vi.fn(),
    refreshBoards: vi.fn(),
  }),
}));

// Mock useQueries
vi.mock("@/hooks/useQueries", () => ({
  useBoardViewQuery: () => ({
    data: null,
    dataUpdatedAt: 0,
  }),
}));

// Mock API calls -- all mock return values must be inline (no external variable references)
vi.mock("@/services/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/services/api")>();
  return {
    ...original,
    fetchTicket: vi.fn().mockResolvedValue({
      id: "ticket-1",
      goal_id: "goal-1",
      title: "Implement user authentication",
      description: "Add JWT-based authentication to the API",
      state: "planned",
      priority: 80,
      blocked_by_ticket_id: null,
      blocked_by_ticket_title: null,
      created_at: "2025-01-01T00:00:00Z",
      updated_at: "2025-01-01T00:00:00Z",
    }),
    fetchTicketEvents: vi.fn().mockResolvedValue({ events: [] }),
    fetchTicketEvidence: vi.fn().mockResolvedValue({ evidence: [] }),
    fetchTicketRevisions: vi.fn().mockResolvedValue({ revisions: [] }),
    fetchMergeStatus: vi.fn().mockResolvedValue(null),
    fetchTicketJobs: vi.fn().mockResolvedValue({ jobs: [] }),
    fetchTicketDependents: vi.fn().mockResolvedValue([]),
    fetchConflictStatus: vi.fn().mockResolvedValue(null),
    fetchExecutorProfiles: vi.fn().mockResolvedValue([]),
    transitionTicket: vi.fn(),
    executeTicket: vi.fn(),
    queueFollowupMessage: vi.fn(),
    getQueuedMessage: vi.fn().mockResolvedValue(null),
    cancelQueuedMessage: vi.fn(),
    fetchTicketAgentLogs: vi.fn().mockResolvedValue({
      ticket_id: "ticket-1",
      total_jobs: 0,
      total_entries: 0,
      executions: [],
    }),
    streamAgentLogs: vi.fn().mockReturnValue({ close: vi.fn() }),
  };
});

describe("TicketDetailPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders ticket title after loading", async () => {
    render(<TicketDetailPanel />);

    await waitFor(() => {
      expect(
        screen.getByText("Implement user authentication")
      ).toBeInTheDocument();
    });
  });

  it("renders ticket description", async () => {
    render(<TicketDetailPanel />);

    await waitFor(() => {
      expect(
        screen.getByText("Add JWT-based authentication to the API")
      ).toBeInTheDocument();
    });
  });

  it("renders ticket state", async () => {
    render(<TicketDetailPanel />);

    await waitFor(() => {
      expect(
        screen.getByText(STATE_DISPLAY_NAMES[TicketState.PLANNED])
      ).toBeInTheDocument();
    });
  });

  it("renders priority display", async () => {
    render(<TicketDetailPanel />);

    await waitFor(() => {
      expect(screen.getByText("80 (High)")).toBeInTheDocument();
    });
  });

  it("renders Description section heading", async () => {
    render(<TicketDetailPanel />);

    await waitFor(() => {
      expect(screen.getByText("Description")).toBeInTheDocument();
    });
  });

  it("renders Agent Activity section", async () => {
    render(<TicketDetailPanel />);

    await waitFor(() => {
      expect(screen.getByText("Agent Activity")).toBeInTheDocument();
    });
  });

  it("renders keyboard navigation hint", async () => {
    render(<TicketDetailPanel />);

    await waitFor(() => {
      expect(screen.getByText("navigate tickets")).toBeInTheDocument();
    });
  });
});
