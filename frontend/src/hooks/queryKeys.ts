/**
 * React Query key factory for consistent cache management.
 *
 * Usage:
 *   queryClient.invalidateQueries({ queryKey: queryKeys.boards.all })
 *   queryClient.invalidateQueries({ queryKey: queryKeys.tickets.detail(id) })
 */

export const queryKeys = {
  boards: {
    all: ['boards'] as const,
    detail: (boardId: string) => ['boards', boardId] as const,
    view: (boardId: string) => ['boards', boardId, 'view'] as const,
  },
  tickets: {
    all: ['tickets'] as const,
    detail: (ticketId: string) => ['tickets', ticketId] as const,
  },
  goals: {
    all: ['goals'] as const,
    detail: (goalId: string) => ['goals', goalId] as const,
    byBoard: (boardId: string) => ['goals', 'board', boardId] as const,
  },
  jobs: {
    all: ['jobs'] as const,
    detail: (jobId: string) => ['jobs', jobId] as const,
    byTicket: (ticketId: string) => ['jobs', 'ticket', ticketId] as const,
  },
  revisions: {
    all: ['revisions'] as const,
    detail: (revisionId: string) => ['revisions', revisionId] as const,
    byTicket: (ticketId: string) => ['revisions', 'ticket', ticketId] as const,
  },
  evidence: {
    byTicket: (ticketId: string) => ['evidence', 'ticket', ticketId] as const,
    byJob: (jobId: string) => ['evidence', 'job', jobId] as const,
  },
  executors: {
    available: ['executors', 'available'] as const,
    profiles: ['executors', 'profiles'] as const,
  },
  planner: {
    status: ['planner', 'status'] as const,
  },
} as const;
