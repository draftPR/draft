import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { BoardLayout } from "@/components/BoardLayout";
import { COLUMN_ORDER, STATE_DISPLAY_NAMES } from "@/types/api";

// Mock BoardContext
vi.mock("@/contexts/BoardContext", () => ({
  useBoard: () => ({
    currentBoard: {
      id: "board-1",
      name: "Test Board",
      repo_root: "/tmp",
      description: null,
      default_branch: "main",
      created_at: "",
      updated_at: "",
    },
    boards: [
      {
        id: "board-1",
        name: "Test Board",
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

// Mock queries
vi.mock("@/hooks/useQueries", () => ({
  useBoardViewQuery: () => ({
    data: {
      columns: COLUMN_ORDER.map((state) => ({
        state,
        tickets: [],
      })),
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

// Mock API
vi.mock("@/services/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/services/api")>();
  return {
    ...original,
    runPlannerStart: vi.fn().mockResolvedValue({ status: "completed", tickets_queued: 0, message: "" }),
    fetchPlannerStatus: vi.fn().mockResolvedValue({
      model: "test",
      llm_configured: true,
      llm_provider: "test",
      features: { auto_execute: false, propose_followups: false, generate_reflections: false },
      max_followups_per_ticket: 2,
      max_followups_per_tick: 3,
    }),
  };
});

// Mock ticketStore -- no ticket selected
vi.mock("@/stores/ticketStore", () => ({
  useTicketSelectionStore: () => ({
    selectedTicketId: null,
    detailDrawerOpen: false,
    selectTicket: vi.fn(),
    clearSelection: vi.fn(),
    setDetailDrawerOpen: vi.fn(),
  }),
}));

describe("BoardLayout", () => {
  it("renders the KanbanBoard when no ticket is selected", () => {
    render(<BoardLayout />);

    // Should render the kanban board column headers
    expect(screen.getByText(STATE_DISPLAY_NAMES.proposed)).toBeInTheDocument();
    expect(screen.getByText(STATE_DISPLAY_NAMES.planned)).toBeInTheDocument();
    expect(screen.getByText(STATE_DISPLAY_NAMES.done)).toBeInTheDocument();
  });

  it("renders Autopilot button from KanbanBoard", () => {
    render(<BoardLayout />);
    expect(screen.getByText("Start Autopilot")).toBeInTheDocument();
  });
});
