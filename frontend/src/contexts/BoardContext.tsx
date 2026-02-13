/**
 * BoardContext - Manages current board (project) state
 */

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import type { Board } from '@/types/api';
import { fetchBoards } from '@/services/api';

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
  const [currentBoardId, setCurrentBoardId] = useState<string | null>(() => {
    // Load from localStorage on mount
    return localStorage.getItem('currentBoardId');
  });
  const [boards, setBoards] = useState<Board[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  // Fetch boards on mount
  useEffect(() => {
    loadBoards();
  }, []);

  async function loadBoards() {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetchBoards();
      setBoards(response.boards);

      // Auto-select first board if none selected
      if (!currentBoardId && response.boards.length > 0) {
        setCurrentBoardId(response.boards[0].id);
      }

      // If selected board was deleted, clear selection
      if (currentBoardId && !response.boards.find(b => b.id === currentBoardId)) {
        setCurrentBoardId(response.boards[0]?.id || null);
      }
    } catch (err) {
      console.error('Failed to load boards:', err);
      setError(err instanceof Error ? err : new Error('Failed to load boards'));
    } finally {
      setIsLoading(false);
    }
  }

  // Persist current board to localStorage
  useEffect(() => {
    if (currentBoardId) {
      localStorage.setItem('currentBoardId', currentBoardId);
    } else {
      localStorage.removeItem('currentBoardId');
    }
  }, [currentBoardId]);

  const currentBoard = boards.find(b => b.id === currentBoardId) || null;

  const value: BoardContextValue = {
    currentBoard,
    setCurrentBoard: setCurrentBoardId,
    boards,
    isLoading,
    error,
    refreshBoards: loadBoards,
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
