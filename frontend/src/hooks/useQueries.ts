/**
 * React Query hooks for data fetching with automatic caching and refetching.
 */

import { useQuery } from '@tanstack/react-query';
import { queryKeys } from './queryKeys';
import {
  fetchBoards,
  fetchBoard,
  fetchTicket,
  fetchPlannerStatus,
} from '@/services/api';
import type {
  BoardListResponse,
  BoardResponse,
  Ticket,
  PlannerStatusResponse,
} from '@/types/api';

/** Fetch all boards */
export function useBoardsQuery() {
  return useQuery<BoardListResponse>({
    queryKey: queryKeys.boards.all,
    queryFn: fetchBoards,
    staleTime: 2000,
  });
}

/** Fetch board view (columns + tickets) with optional auto-refetch */
export function useBoardViewQuery(boardId: string | null | undefined, autoRefresh = true) {
  return useQuery<BoardResponse>({
    queryKey: queryKeys.boards.view(boardId ?? ''),
    queryFn: () => fetchBoard(boardId!),
    enabled: !!boardId,
    staleTime: 2000,
    refetchInterval: autoRefresh ? 3000 : false,
  });
}

/** Fetch a single ticket */
export function useTicketQuery(ticketId: string | null | undefined) {
  return useQuery<Ticket>({
    queryKey: queryKeys.tickets.detail(ticketId ?? ''),
    queryFn: () => fetchTicket(ticketId!),
    enabled: !!ticketId,
    staleTime: 5000,
  });
}

/** Fetch planner status */
export function usePlannerStatusQuery(healthCheck = false) {
  return useQuery<PlannerStatusResponse>({
    queryKey: [...queryKeys.planner.status, healthCheck],
    queryFn: () => fetchPlannerStatus(healthCheck),
    staleTime: 10000,
  });
}
