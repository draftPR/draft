import type {
  Board,
  Goal,
  Ticket,
  BoardResponse,
  TicketsByState,
  Evidence,
  Revision,
  Job,
  TicketEvent,
  ReviewComment,
  ReviewSummary,
  PlannerStatusResponse,
} from "@/types/api";
import {
  TicketState,
  JobStatus,
  JobKind,
  RevisionStatus,
  ActorType,
  EventType,
  EvidenceKind,
  AuthorType,
  ReviewDecision,
} from "@/types/api";

let counter = 0;
function uid(): string {
  counter += 1;
  return `test-${counter.toString().padStart(4, "0")}`;
}

export function resetIdCounter() {
  counter = 0;
}

// --- Board ---
export function createMockBoard(overrides: Partial<Board> = {}): Board {
  const id = uid();
  return {
    id,
    name: `Test Board ${id}`,
    description: "A test board",
    repo_root: "/tmp/test-repo",
    default_branch: "main",
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    ...overrides,
  };
}

// --- Goal ---
export function createMockGoal(overrides: Partial<Goal> = {}): Goal {
  const id = uid();
  return {
    id,
    title: `Test Goal ${id}`,
    description: "A test goal description",
    board_id: "board-1",
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    ticket_count: 0,
    done_count: 0,
    cost_budget_cents: null,
    cost_spent_cents: 0,
    max_auto_tickets: 10,
    max_concurrent_tickets: 1,
    autonomy_level: "supervised",
    ...overrides,
  } as Goal;
}

// --- Ticket ---
export function createMockTicket(overrides: Partial<Ticket> = {}): Ticket {
  const id = uid();
  return {
    id,
    title: `Test Ticket ${id}`,
    description: "A test ticket description",
    state: TicketState.PLANNED,
    priority: 50,
    priority_bucket: "P1",
    goal_id: "goal-1",
    board_id: "board-1",
    blocked_by_ticket_id: null,
    is_blocked: false,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    ...overrides,
  } as Ticket;
}

// --- Job ---
export function createMockJob(overrides: Partial<Job> = {}): Job {
  const id = uid();
  return {
    id,
    ticket_id: "ticket-1",
    board_id: "board-1",
    kind: JobKind.EXECUTE,
    status: JobStatus.SUCCEEDED,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    started_at: "2025-01-01T00:00:01Z",
    finished_at: "2025-01-01T00:00:30Z",
    error_message: null,
    ...overrides,
  } as Job;
}

// --- Evidence ---
export function createMockEvidence(
  overrides: Partial<Evidence> = {},
): Evidence {
  const id = uid();
  return {
    id,
    job_id: "job-1",
    ticket_id: "ticket-1",
    kind: EvidenceKind.COMMAND_LOG,
    label: "test output",
    body: "All tests passed",
    created_at: "2025-01-01T00:00:00Z",
    ...overrides,
  } as Evidence;
}

// --- Revision ---
export function createMockRevision(
  overrides: Partial<Revision> = {},
): Revision {
  const id = uid();
  return {
    id,
    ticket_id: "ticket-1",
    job_id: "job-1",
    revision_number: 1,
    status: RevisionStatus.OPEN,
    diff_stat: "+10 -2",
    diff_patch: "diff --git a/file.py ...",
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    ...overrides,
  } as Revision;
}

// --- Ticket Event ---
export function createMockTicketEvent(
  overrides: Partial<TicketEvent> = {},
): TicketEvent {
  const id = uid();
  return {
    id,
    ticket_id: "ticket-1",
    event_type: EventType.CREATED,
    actor_type: ActorType.HUMAN,
    actor_id: null,
    old_state: null,
    new_state: TicketState.PROPOSED,
    detail: null,
    created_at: "2025-01-01T00:00:00Z",
    ...overrides,
  } as TicketEvent;
}

// --- Review Comment ---
export function createMockReviewComment(
  overrides: Partial<ReviewComment> = {},
): ReviewComment {
  const id = uid();
  return {
    id,
    revision_id: "rev-1",
    file_path: "src/main.py",
    line_number: 10,
    body: "Looks good",
    author_type: AuthorType.HUMAN,
    created_at: "2025-01-01T00:00:00Z",
    ...overrides,
  } as ReviewComment;
}

// --- Review Summary ---
export function createMockReviewSummary(
  overrides: Partial<ReviewSummary> = {},
): ReviewSummary {
  return {
    id: uid(),
    revision_id: "rev-1",
    decision: ReviewDecision.APPROVED,
    body: "LGTM",
    author_type: AuthorType.HUMAN,
    created_at: "2025-01-01T00:00:00Z",
    ...overrides,
  } as ReviewSummary;
}

// --- Board Response (full board view) ---
export function createMockBoardResponse(
  tickets: Ticket[] = [],
): BoardResponse {
  const columnMap = new Map<string, Ticket[]>();
  for (const state of Object.values(TicketState)) {
    columnMap.set(state, []);
  }
  for (const t of tickets) {
    const list = columnMap.get(t.state);
    if (list) list.push(t);
  }
  const columns: TicketsByState[] = [];
  for (const [state, tix] of columnMap) {
    columns.push({ state: state as TicketState, tickets: tix });
  }
  return { columns, total_tickets: tickets.length };
}

// --- Planner Status ---
export function createMockPlannerStatus(
  overrides: Partial<PlannerStatusResponse> = {},
): PlannerStatusResponse {
  return {
    running: false,
    tick_count: 0,
    actions: [],
    ...overrides,
  } as PlannerStatusResponse;
}
