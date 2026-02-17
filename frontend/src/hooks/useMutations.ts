/**
 * React Query mutation hooks for state-changing operations.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from './queryKeys';
import {
  transitionTicket,
  executeTicket,
  runPlannerStart,
} from '@/services/api';
import type {
  TicketTransition,
} from '@/types/api';

/** Transition a ticket to a new state */
export function useTransitionTicket() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ ticketId, data }: { ticketId: string; data: TicketTransition }) =>
      transitionTicket(ticketId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.boards.all });
    },
  });
}

/** Execute a ticket (start a job) */
export function useExecuteTicket() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ticketId: string) => executeTicket(ticketId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.boards.all });
    },
  });
}

/** Start the autopilot planner */
export function useStartAutopilot() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: runPlannerStart,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.boards.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.planner.status });
    },
  });
}
