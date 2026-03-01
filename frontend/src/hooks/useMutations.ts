/**
 * React Query mutation hooks with optimistic updates.
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
  BoardResponse,
} from '@/types/api';
import { TicketState } from '@/types/api';

/** Transition a ticket to a new state (optimistic) */
export function useTransitionTicket(boardId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ ticketId, data }: { ticketId: string; data: TicketTransition }) =>
      transitionTicket(ticketId, data),

    onMutate: async ({ ticketId, data }) => {
      if (!boardId) return;
      const boardKey = queryKeys.boards.view(boardId);

      await queryClient.cancelQueries({ queryKey: boardKey });
      const snapshot = queryClient.getQueryData<BoardResponse>(boardKey);

      if (snapshot) {
        // Find the ticket in existing columns
        let movedTicket = null;
        for (const col of snapshot.columns) {
          const found = col.tickets.find((t) => t.id === ticketId);
          if (found) {
            movedTicket = found;
            break;
          }
        }

        if (movedTicket) {
          const updatedTicket = { ...movedTicket, state: data.to_state };
          const newColumns = snapshot.columns.map((col) => {
            if (col.state === movedTicket!.state) {
              return { ...col, tickets: col.tickets.filter((t) => t.id !== ticketId) };
            }
            if (col.state === data.to_state) {
              return { ...col, tickets: [updatedTicket, ...col.tickets] };
            }
            return col;
          });
          queryClient.setQueryData(boardKey, { ...snapshot, columns: newColumns });
        }
      }

      return { snapshot };
    },

    onError: (_err, _vars, context) => {
      if (boardId && context?.snapshot) {
        queryClient.setQueryData(queryKeys.boards.view(boardId), context.snapshot);
      }
    },

    onSettled: () => {
      if (boardId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.boards.view(boardId) });
      }
    },
  });
}

/** Execute a ticket (optimistic move to EXECUTING) */
export function useExecuteTicket(boardId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ticketId: string) => executeTicket(ticketId),

    onMutate: async (ticketId) => {
      if (!boardId) return;
      const boardKey = queryKeys.boards.view(boardId);

      await queryClient.cancelQueries({ queryKey: boardKey });
      const snapshot = queryClient.getQueryData<BoardResponse>(boardKey);

      if (snapshot) {
        let movedTicket = null;
        for (const col of snapshot.columns) {
          const found = col.tickets.find((t) => t.id === ticketId);
          if (found) {
            movedTicket = found;
            break;
          }
        }

        if (movedTicket) {
          const updatedTicket = { ...movedTicket, state: TicketState.EXECUTING };
          const newColumns = snapshot.columns.map((col) => {
            if (col.state === movedTicket!.state) {
              return { ...col, tickets: col.tickets.filter((t) => t.id !== ticketId) };
            }
            if (col.state === TicketState.EXECUTING) {
              return { ...col, tickets: [updatedTicket, ...col.tickets] };
            }
            return col;
          });
          queryClient.setQueryData(boardKey, { ...snapshot, columns: newColumns });
        }
      }

      return { snapshot };
    },

    onError: (_err, _vars, context) => {
      if (boardId && context?.snapshot) {
        queryClient.setQueryData(queryKeys.boards.view(boardId), context.snapshot);
      }
    },

    onSettled: () => {
      if (boardId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.boards.view(boardId) });
      }
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
