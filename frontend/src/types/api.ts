/**
 * TypeScript types matching backend API schemas
 */

// State values matching backend state_machine.py (using const objects for erasableSyntaxOnly)
export const TicketState = {
  PROPOSED: "proposed",
  PLANNED: "planned",
  EXECUTING: "executing",
  VERIFYING: "verifying",
  NEEDS_HUMAN: "needs_human",
  BLOCKED: "blocked",
  DONE: "done",
  ABANDONED: "abandoned",
} as const;

export type TicketState = (typeof TicketState)[keyof typeof TicketState];

export const ActorType = {
  HUMAN: "human",
  PLANNER: "planner",
  SYSTEM: "system",
  EXECUTOR: "executor",
} as const;

export type ActorType = (typeof ActorType)[keyof typeof ActorType];

export const EventType = {
  CREATED: "created",
  TRANSITIONED: "transitioned",
  UPDATED: "updated",
  COMMENT: "comment",
} as const;

export type EventType = (typeof EventType)[keyof typeof EventType];

// Goal types
export interface Goal {
  id: string;
  title: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface GoalCreate {
  title: string;
  description?: string | null;
}

export interface GoalListResponse {
  goals: Goal[];
  total: number;
}

// Ticket types
export interface Ticket {
  id: string;
  goal_id: string;
  title: string;
  description: string | null;
  state: TicketState;
  priority: number | null;
  created_at: string;
  updated_at: string;
}

export interface TicketCreate {
  goal_id: string;
  title: string;
  description?: string | null;
  priority?: number | null;
  actor_type?: ActorType;
  actor_id?: string | null;
}

export interface TicketTransition {
  to_state: TicketState;
  actor_type: ActorType;
  actor_id?: string | null;
  reason?: string | null;
}

// Ticket Event types
export interface TicketEvent {
  id: string;
  ticket_id: string;
  event_type: EventType;
  from_state: TicketState | null;
  to_state: TicketState | null;
  actor_type: ActorType;
  actor_id: string | null;
  reason: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface TicketEventListResponse {
  events: TicketEvent[];
  total: number;
}

// Evidence types (verification command results)
export const EvidenceKind = {
  COMMAND_LOG: "command_log",
  TEST_REPORT: "test_report",
} as const;

export type EvidenceKind = (typeof EvidenceKind)[keyof typeof EvidenceKind];

export interface Evidence {
  id: string;
  ticket_id: string;
  job_id: string;
  kind: EvidenceKind;
  command: string;
  exit_code: number;
  stdout_path: string | null;
  stderr_path: string | null;
  created_at: string;
  succeeded: boolean;
}

export interface EvidenceListResponse {
  evidence: Evidence[];
  total: number;
}

// Board types
export interface TicketsByState {
  state: TicketState;
  tickets: Ticket[];
}

export interface BoardResponse {
  columns: TicketsByState[];
  total_tickets: number;
}

// API Error type
export interface ApiError {
  detail: string;
}

// Column order for display
export const COLUMN_ORDER: TicketState[] = [
  TicketState.PROPOSED,
  TicketState.PLANNED,
  TicketState.EXECUTING,
  TicketState.VERIFYING,
  TicketState.NEEDS_HUMAN,
  TicketState.BLOCKED,
  TicketState.DONE,
  TicketState.ABANDONED,
];

// State display names
export const STATE_DISPLAY_NAMES: Record<TicketState, string> = {
  [TicketState.PROPOSED]: "Proposed",
  [TicketState.PLANNED]: "Planned",
  [TicketState.EXECUTING]: "Executing",
  [TicketState.VERIFYING]: "Verifying",
  [TicketState.NEEDS_HUMAN]: "Needs Human",
  [TicketState.BLOCKED]: "Blocked",
  [TicketState.DONE]: "Done",
  [TicketState.ABANDONED]: "Abandoned",
};

// State colors for badges
export const STATE_COLORS: Record<TicketState, string> = {
  [TicketState.PROPOSED]: "bg-slate-500",
  [TicketState.PLANNED]: "bg-blue-500",
  [TicketState.EXECUTING]: "bg-amber-500",
  [TicketState.VERIFYING]: "bg-purple-500",
  [TicketState.NEEDS_HUMAN]: "bg-orange-500",
  [TicketState.BLOCKED]: "bg-red-500",
  [TicketState.DONE]: "bg-emerald-500",
  [TicketState.ABANDONED]: "bg-gray-400",
};
