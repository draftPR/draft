import { describe, it, expect, beforeEach } from "vitest";
import { useBoardStore, selectCurrentBoard } from "../boardStore";
import type { Board } from "@/types/api";

const mockBoards: Board[] = [
  {
    id: "board-1",
    name: "Board One",
    description: null,
    repo_root: "/tmp/repo1",
    default_branch: "main",
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
  {
    id: "board-2",
    name: "Board Two",
    description: "second",
    repo_root: "/tmp/repo2",
    default_branch: "main",
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
];

describe("boardStore", () => {
  beforeEach(() => {
    useBoardStore.setState({ currentBoardId: null });
  });

  it("initializes with null when localStorage is empty", () => {
    const state = useBoardStore.getState();
    expect(state.currentBoardId).toBeNull();
  });

  it("setCurrentBoardId updates state and writes to localStorage", () => {
    useBoardStore.getState().setCurrentBoardId("board-1");
    expect(useBoardStore.getState().currentBoardId).toBe("board-1");
    expect(localStorage.setItem).toHaveBeenCalledWith(
      "currentBoardId",
      "board-1",
    );
  });

  it("clearCurrentBoard resets state and removes from localStorage", () => {
    useBoardStore.getState().setCurrentBoardId("board-1");
    useBoardStore.getState().clearCurrentBoard();
    expect(useBoardStore.getState().currentBoardId).toBeNull();
    expect(localStorage.removeItem).toHaveBeenCalledWith("currentBoardId");
  });
});

describe("selectCurrentBoard", () => {
  it("returns board matching currentBoardId", () => {
    const result = selectCurrentBoard(mockBoards, "board-2");
    expect(result?.id).toBe("board-2");
  });

  it("returns first board when id is null", () => {
    const result = selectCurrentBoard(mockBoards, null);
    expect(result?.id).toBe("board-1");
  });

  it("returns first board when id does not match", () => {
    const result = selectCurrentBoard(mockBoards, "nonexistent");
    expect(result?.id).toBe("board-1");
  });

  it("returns null when board list is empty", () => {
    const result = selectCurrentBoard([], "board-1");
    expect(result).toBeNull();
  });
});
