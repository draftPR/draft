/**
 * Board store -- replaces BoardContext.tsx
 *
 * Manages current board selection and board list.
 * Server state (board list) still comes from React Query via useQueries.
 * This store only holds the "which board is selected" client state.
 */

import { create } from "zustand";
import type { Board } from "@/types/api";

interface BoardState {
  currentBoardId: string | null;
  setCurrentBoardId: (id: string) => void;
  clearCurrentBoard: () => void;
}

export const useBoardStore = create<BoardState>((set) => ({
  currentBoardId: localStorage.getItem("currentBoardId"),

  setCurrentBoardId: (id: string) => {
    localStorage.setItem("currentBoardId", id);
    set({ currentBoardId: id });
  },

  clearCurrentBoard: () => {
    localStorage.removeItem("currentBoardId");
    set({ currentBoardId: null });
  },
}));

/**
 * Derive the current board from the board list and store selection.
 * Use this in components that need the full Board object.
 */
export function selectCurrentBoard(
  boards: Board[],
  currentBoardId: string | null,
): Board | null {
  if (currentBoardId) {
    const board = boards.find((b) => b.id === currentBoardId);
    if (board) return board;
  }
  return boards.length > 0 ? boards[0] : null;
}
