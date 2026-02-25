import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { BoardSelector } from "@/components/BoardSelector";

// Use a mutable mock that can be overridden per test
const mockBoardContext = {
  currentBoard: null as Record<string, unknown> | null,
  boards: [] as Record<string, unknown>[],
  isLoading: false,
  error: null,
  setCurrentBoard: vi.fn(),
  refreshBoards: vi.fn(),
};

vi.mock("@/contexts/BoardContext", () => ({
  useBoard: () => mockBoardContext,
}));

const mockBoard = {
  id: "board-1",
  name: "My Project",
  repo_root: "/tmp/repo",
  description: "A test project",
  default_branch: "main",
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

describe("BoardSelector", () => {
  beforeEach(() => {
    // Reset to defaults
    mockBoardContext.currentBoard = null;
    mockBoardContext.boards = [];
    mockBoardContext.isLoading = false;
    mockBoardContext.error = null;
  });

  it("renders current board name when boards are available", () => {
    mockBoardContext.currentBoard = mockBoard;
    mockBoardContext.boards = [mockBoard];

    render(<BoardSelector />);
    expect(screen.getByText("My Project")).toBeInTheDocument();
  });

  it("shows 'No projects yet' when no boards exist", () => {
    mockBoardContext.currentBoard = null;
    mockBoardContext.boards = [];

    render(<BoardSelector />);
    expect(screen.getByText("No projects yet")).toBeInTheDocument();
  });

  it("shows skeleton when loading", () => {
    mockBoardContext.isLoading = true;

    render(<BoardSelector />);
    // The Skeleton component renders with animate-pulse class
    const skeleton = document.querySelector(".animate-pulse");
    expect(skeleton).toBeInTheDocument();
  });
});
