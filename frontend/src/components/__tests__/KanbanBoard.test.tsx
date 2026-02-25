import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { KanbanBoard } from "@/components/KanbanBoard";
import { COLUMN_ORDER, STATE_DISPLAY_NAMES } from "@/types/api";

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
    boards: [
      {
        id: "board-1",
        name: "Test",
        repo_root: "/tmp",
        description: null,
        default_branch: "main",
        created_at: "",
        updated_at: "",
      },
    ],
    isLoading: false,
    error: null,
    setCurrentBoard: vi.fn(),
    refreshBoards: vi.fn(),
  }),
}));

// Mock DnD
vi.mock("@hello-pangea/dnd", () => ({
  DragDropContext: ({ children }: { children: React.ReactNode }) => children,
  Droppable: ({ children }: { children: (...args: unknown[]) => React.ReactNode }) =>
    children(
      { innerRef: vi.fn(), droppableProps: {}, placeholder: null },
      { isDraggingOver: false }
    ),
  Draggable: ({ children }: { children: (...args: unknown[]) => React.ReactNode }) =>
    children(
      { innerRef: vi.fn(), draggableProps: {}, dragHandleProps: {} },
      { isDragging: false }
    ),
}));

// Mock queries hook to return empty board data
vi.mock("@/hooks/useQueries", () => ({
  useBoardViewQuery: () => ({
    data: {
      columns: [
        { state: "proposed", tickets: [] },
        { state: "planned", tickets: [] },
        { state: "executing", tickets: [] },
        { state: "verifying", tickets: [] },
        { state: "needs_human", tickets: [] },
        { state: "blocked", tickets: [] },
        { state: "done", tickets: [] },
        { state: "abandoned", tickets: [] },
      ],
      total_tickets: 0,
    },
    isLoading: false,
    error: null,
    dataUpdatedAt: Date.now(),
    refetch: vi.fn(),
  }),
}));

// Mock mutations
vi.mock("@/hooks/useMutations", () => ({
  useTransitionTicket: () => ({ mutateAsync: vi.fn() }),
  useExecuteTicket: () => ({ mutateAsync: vi.fn() }),
}));

// Mock api calls used inside KanbanBoard
vi.mock("@/services/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/services/api")>();
  return {
    ...original,
    runPlannerStart: vi.fn().mockResolvedValue({ status: "completed", tickets_queued: 0, message: "No tickets" }),
    fetchPlannerStatus: vi.fn().mockResolvedValue({
      model: "test-model",
      llm_configured: true,
      llm_provider: "test",
      features: { auto_execute: false, propose_followups: false, generate_reflections: false },
      max_followups_per_ticket: 2,
      max_followups_per_tick: 3,
    }),
  };
});

// Mock ticketStore
vi.mock("@/stores/ticketStore", () => ({
  useTicketSelectionStore: () => ({
    selectTicket: vi.fn(),
    selectedTicketId: null,
    detailDrawerOpen: false,
    clearSelection: vi.fn(),
    setDetailDrawerOpen: vi.fn(),
  }),
}));

describe("KanbanBoard", () => {
  it("renders column headers for all states", () => {
    render(<KanbanBoard />);

    for (const state of COLUMN_ORDER) {
      const displayName = STATE_DISPLAY_NAMES[state];
      expect(screen.getByText(displayName)).toBeInTheDocument();
    }
  });

  it("renders the Start Autopilot button", () => {
    render(<KanbanBoard />);
    expect(screen.getByText("Start Autopilot")).toBeInTheDocument();
  });

  it("renders the auto-refresh toggle", () => {
    render(<KanbanBoard />);
    expect(screen.getByText("Auto-refresh")).toBeInTheDocument();
  });

  it("renders the Refresh button", () => {
    render(<KanbanBoard />);
    expect(screen.getByText("Refresh")).toBeInTheDocument();
  });

  it("renders the filter input", () => {
    render(<KanbanBoard />);
    expect(
      screen.getByPlaceholderText("Filter tickets...")
    ).toBeInTheDocument();
  });
});
