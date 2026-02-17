/**
 * BoardContext - Manages current board (project) state using React Query
 */

import { createContext, useContext, useState, useMemo, useCallback, ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { Board } from '@/types/api';
import { useBoardsQuery } from '@/hooks/useQueries';
import { queryKeys } from '@/hooks/queryKeys';

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
  const [currentBoardId, setCurrentBoardId] = useState<string | null>(() => {
    return localStorage.getItem('currentBoardId');
  });

  const { data, isLoading, error } = useBoardsQuery();
  const boards = useMemo(() => data?.boards ?? [], [data?.boards]);

  // Derive the effective board ID: auto-select first board or clear stale selection
  const effectiveBoardId = useMemo(() => {
    if (currentBoardId && boards.some(b => b.id === currentBoardId)) {
      return currentBoardId;
    }
    return boards.length > 0 ? boards[0].id : null;
  }, [boards, currentBoardId]);

  // Sync effectiveBoardId back to state + localStorage when it diverges
  if (effectiveBoardId !== currentBoardId) {
    setCurrentBoardId(effectiveBoardId);
    if (effectiveBoardId) {
      localStorage.setItem('currentBoardId', effectiveBoardId);
    } else {
      localStorage.removeItem('currentBoardId');
    }
  }

  const currentBoard = boards.find(b => b.id === effectiveBoardId) || null;

  async function refreshBoards() {
    await queryClient.invalidateQueries({ queryKey: queryKeys.boards.all });
  }

  const setCurrentBoard = useCallback((boardId: string) => {
    setCurrentBoardId(boardId);
    localStorage.setItem('currentBoardId', boardId);
  }, []);

  const value: BoardContextValue = {
    currentBoard,
    setCurrentBoard,
    boards,
    isLoading,
    error: error as Error | null,
    refreshBoards,
  };

  return (
    <BoardContext.Provider value={value}>
      {children}
    </BoardContext.Provider>
  );
}

/**
 * Hook to access board context
 */
export function useBoard() {
  const context = useContext(BoardContext);
  if (!context) {
    throw new Error('useBoard must be used within BoardProvider');
  }
  return context;
}
