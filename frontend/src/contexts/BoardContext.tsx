/**
 * BoardContext - Compatibility wrapper around Zustand boardStore.
 *
 * Delegates to useBoardStore for board selection state.
 * Server state (board list) still comes from React Query via useQueries.
 *
 * Components can use either:
 *   - useBoard() (this context, for backwards compatibility)
 *   - useBoardStore() + useBoardsQuery() (direct, preferred for new code)
 */

import {
  createContext,
  useContext,
  useMemo,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Board } from "@/types/api";
import { useBoardsQuery } from "@/hooks/useQueries";
import { queryKeys } from "@/hooks/queryKeys";
import { useBoardStore, selectCurrentBoard } from "@/stores/boardStore";

interface BoardContextValue {
  currentBoard: Board | null;
  setCurrentBoard: (boardId: string) => void;
  boards: Board[];
  isLoading: boolean;
  error: Error | null;
  refreshBoards: () => Promise<void>;
}

const BoardContext = createContext<BoardContextValue | null>(null);

interface BoardProviderProps {
  children: ReactNode;
}

export function BoardProvider({ children }: BoardProviderProps) {
  const queryClient = useQueryClient();
  const { currentBoardId, setCurrentBoardId } = useBoardStore();

  const { data, isLoading, error } = useBoardsQuery();
  const boards = useMemo(() => data?.boards ?? [], [data?.boards]);

  const currentBoard = useMemo(
    () => selectCurrentBoard(boards, currentBoardId),
    [boards, currentBoardId],
  );

  // Auto-select first board if none selected or selection is stale
  if (!currentBoard && boards.length > 0) {
    setCurrentBoardId(boards[0].id);
  }

  async function refreshBoards() {
    await queryClient.invalidateQueries({ queryKey: queryKeys.boards.all });
  }

  const value: BoardContextValue = {
    currentBoard,
    setCurrentBoard: setCurrentBoardId,
    boards,
    isLoading,
    error: error as Error | null,
    refreshBoards,
  };

  return (
    <BoardContext.Provider value={value}>{children}</BoardContext.Provider>
  );
}

/**
 * Hook to access board context (backwards compatible).
 * Prefer using useBoardStore() + useBoardsQuery() directly in new code.
 */
export function useBoard() {
  const context = useContext(BoardContext);
  if (!context) {
    throw new Error("useBoard must be used within BoardProvider");
  }
  return context;
}
