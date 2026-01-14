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
  // Core lifecycle events
  CREATED: "created",
  TRANSITIONED: "transitioned",
  UPDATED: "updated",
  COMMENT: "comment",
  // Merge lifecycle events
  MERGE_REQUESTED: "merge_requested",
  MERGE_SUCCEEDED: "merge_succeeded",
  MERGE_FAILED: "merge_failed",
  // Cleanup events
  WORKTREE_CLEANED: "worktree_cleaned",
  WORKTREE_CLEANUP_FAILED: "worktree_cleanup_failed",
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
  // GitHub PR fields
  pr_number?: number | null;
  pr_url?: string | null;
  pr_state?: string | null;
  pr_created_at?: string | null;
  pr_merged_at?: string | null;
  pr_head_branch?: string | null;
  pr_base_branch?: string | null;
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
  error_type?: string;
}

// Priority bucket types
export const PriorityBucket = {
  P0: "P0",
  P1: "P1",
  P2: "P2",
  P3: "P3",
} as const;

export type PriorityBucket = (typeof PriorityBucket)[keyof typeof PriorityBucket];

export const PRIORITY_BUCKET_VALUES: Record<PriorityBucket, number> = {
  [PriorityBucket.P0]: 90,
  [PriorityBucket.P1]: 70,
  [PriorityBucket.P2]: 50,
  [PriorityBucket.P3]: 30,
};

export const PRIORITY_BUCKET_LABELS: Record<PriorityBucket, string> = {
  [PriorityBucket.P0]: "P0 - Critical",
  [PriorityBucket.P1]: "P1 - High",
  [PriorityBucket.P2]: "P2 - Medium",
  [PriorityBucket.P3]: "P3 - Low",
};

export const PRIORITY_BUCKET_COLORS: Record<PriorityBucket, string> = {
  [PriorityBucket.P0]: "bg-red-500",
  [PriorityBucket.P1]: "bg-orange-500",
  [PriorityBucket.P2]: "bg-blue-500",
  [PriorityBucket.P3]: "bg-slate-500",
};

// Planner types (AI ticket generation)
export interface ProposedTicket {
  id: string;  // ID of the created ticket
  title: string;
  description: string;
  priority_bucket?: PriorityBucket | null;
  priority?: number | null;
  priority_rationale?: string | null;
  verification: string[];
  notes?: string | null;
}

export interface GenerateTicketsRequest {
  workspace_path?: string;
  include_readme?: boolean;
}

export interface GenerateTicketsResponse {
  tickets: ProposedTicket[];
  goal_id: string;
}

// Reflection types
export interface SuggestedPriorityChange {
  ticket_id: string;
  ticket_title: string;
  current_bucket: PriorityBucket;
  current_priority: number;
  suggested_bucket: PriorityBucket;
  suggested_priority: number;
  reason: string;
}

export type ReflectionQuality = "good" | "needs_work" | "insufficient";

export interface ReflectionResult {
  overall_quality: ReflectionQuality;
  quality_notes: string;
  coverage_gaps: string[];
  suggested_changes: SuggestedPriorityChange[];
}

// Bulk priority update types
export interface PriorityUpdate {
  ticket_id: string;
  priority_bucket: PriorityBucket;
}

export interface BulkPriorityUpdateRequest {
  goal_id: string;
  updates: PriorityUpdate[];
  allow_p0?: boolean;  // Required when assigning P0 priority
}

export interface BulkPriorityUpdateResult {
  ticket_id: string;
  success: boolean;
  new_priority?: number | null;
  new_bucket?: PriorityBucket | null;
  error?: string | null;
}

export interface BulkPriorityUpdateResponse {
  updated: BulkPriorityUpdateResult[];
  updated_count: number;
  failed_count: number;
}

// Bulk accept types
export interface BulkAcceptRequest {
  ticket_ids: string[];
  goal_id?: string | null;
  actor_type?: ActorType;
  actor_id?: string | null;
  reason?: string | null;
  queue_first?: boolean;  // If true, queue first ticket for execution
}

export interface BulkAcceptResult {
  ticket_id: string;
  success: boolean;
  error?: string | null;
}

export interface BulkAcceptResponse {
  accepted_ids: string[];
  rejected: BulkAcceptResult[];
  accepted_count: number;
  failed_count: number;
  queued_job_id?: string | null;  // Job ID if queue_first was true
  queued_ticket_id?: string | null;  // Ticket ID that was queued (first in request order)
}

// Planner Tick types (autopilot)
export const PlannerActionType = {
  ENQUEUED_EXECUTE: "enqueued_execute",
  PROPOSED_FOLLOWUP: "proposed_followup",
  GENERATED_REFLECTION: "generated_reflection",
  SKIPPED: "skipped",
} as const;

export type PlannerActionType = (typeof PlannerActionType)[keyof typeof PlannerActionType];

export interface PlannerAction {
  action_type: PlannerActionType;
  ticket_id: string;
  ticket_title: string | null;
  details: Record<string, unknown> | null;
}

export interface PlannerTickResponse {
  actions: PlannerAction[];
  summary: string;
}

export interface PlannerStartRequest {
  poll_interval_seconds?: number;
  max_duration_seconds?: number;
}

export interface PlannerStartResponse {
  status: "running" | "completed" | "timeout" | "error";
  message: string;
  tickets_queued: number;
  tickets_completed: number;
  tickets_failed: number;
  total_actions: PlannerAction[];
}

export interface PlannerFeaturesStatus {
  auto_execute: boolean;
  propose_followups: boolean;
  generate_reflections: boolean;
}

export interface LastTickStats {
  executed: number;
  followups_created: number;
  reflections_added: number;
  last_tick_at: string | null;
}

export interface LLMHealthCheck {
  healthy: boolean;
  latency_ms: number | null;
  error: string | null;
}

export interface PlannerStatusResponse {
  model: string;
  llm_configured: boolean;
  llm_provider: string | null;
  llm_health: LLMHealthCheck | null;
  features: PlannerFeaturesStatus;
  max_followups_per_ticket: number;
  max_followups_per_tick: number;
  last_tick: LastTickStats | null;
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
// Note: "Done" means human approved and code was merged to main branch
export const STATE_DISPLAY_NAMES: Record<TicketState, string> = {
  [TicketState.PROPOSED]: "Proposed",
  [TicketState.PLANNED]: "Planned",
  [TicketState.EXECUTING]: "Executing",
  [TicketState.VERIFYING]: "Verifying",
  [TicketState.NEEDS_HUMAN]: "Needs Review",
  [TicketState.BLOCKED]: "Blocked",
  [TicketState.DONE]: "Done",  // Approved and merged to main branch
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

// ==================== Revision Types ====================

export const RevisionStatus = {
  OPEN: "open",
  CHANGES_REQUESTED: "changes_requested",
  APPROVED: "approved",
  SUPERSEDED: "superseded",
} as const;

export type RevisionStatus = (typeof RevisionStatus)[keyof typeof RevisionStatus];

export const AuthorType = {
  HUMAN: "human",
  AGENT: "agent",
  SYSTEM: "system",
} as const;

export type AuthorType = (typeof AuthorType)[keyof typeof AuthorType];

export const ReviewDecision = {
  APPROVED: "approved",
  CHANGES_REQUESTED: "changes_requested",
} as const;

export type ReviewDecision = (typeof ReviewDecision)[keyof typeof ReviewDecision];

export interface Revision {
  id: string;
  ticket_id: string;
  job_id: string;
  number: number;
  status: RevisionStatus;
  diff_stat_evidence_id: string | null;
  diff_patch_evidence_id: string | null;
  created_at: string;
  unresolved_comment_count: number;
}

export interface RevisionDetail extends Revision {
  diff_stat: string | null;
  diff_patch: string | null;
}

export interface RevisionListResponse {
  revisions: Revision[];
  total: number;
}

export interface DiffFile {
  path: string;
  old_path?: string | null;
  additions: number;
  deletions: number;
  status: "added" | "deleted" | "modified" | "renamed";
}

export interface RevisionDiffResponse {
  revision_id: string;
  diff_stat: string | null;
  diff_patch: string | null;
  files: DiffFile[];
}

// ==================== Review Comment Types ====================

export interface ReviewComment {
  id: string;
  revision_id: string;
  file_path: string;
  line_number: number;
  anchor: string;
  body: string;
  author_type: AuthorType;
  resolved: boolean;
  created_at: string;
  line_content?: string;
}

export interface ReviewCommentCreate {
  file_path: string;
  line_number: number;
  body: string;
  author_type?: AuthorType;
  hunk_header?: string | null;
  line_content?: string | null;
}

export interface ReviewCommentListResponse {
  comments: ReviewComment[];
  total: number;
  unresolved_count: number;
}

// ==================== Review Summary Types ====================

export interface ReviewSummary {
  id: string;
  revision_id: string;
  decision: ReviewDecision;
  body: string;
  created_at: string;
}

export interface ReviewSubmit {
  decision: ReviewDecision;
  summary: string;
  auto_run_fix?: boolean;
  create_pr?: boolean;
}

// ==================== Feedback Bundle Types ====================

export interface FeedbackComment {
  file_path: string;
  line_number: number;
  anchor: string;
  body: string;
}

export interface FeedbackBundle {
  ticket_id: string;
  revision_id: string;
  revision_number: number;
  decision: string;
  summary: string;
  comments: FeedbackComment[];
}

// Revision status display names
export const REVISION_STATUS_DISPLAY: Record<RevisionStatus, string> = {
  [RevisionStatus.OPEN]: "Open",
  [RevisionStatus.CHANGES_REQUESTED]: "Changes Requested",
  [RevisionStatus.APPROVED]: "Approved",
  [RevisionStatus.SUPERSEDED]: "Superseded",
};

// Revision status colors
export const REVISION_STATUS_COLORS: Record<RevisionStatus, string> = {
  [RevisionStatus.OPEN]: "bg-blue-500",
  [RevisionStatus.CHANGES_REQUESTED]: "bg-orange-500",
  [RevisionStatus.APPROVED]: "bg-emerald-500",
  [RevisionStatus.SUPERSEDED]: "bg-gray-400",
};

// ==================== Merge Types ====================

export const MergeStrategy = {
  MERGE: "merge",
  REBASE: "rebase",
} as const;

export type MergeStrategy = (typeof MergeStrategy)[keyof typeof MergeStrategy];

export interface MergeRequest {
  strategy: MergeStrategy;
  delete_worktree: boolean;
  cleanup_artifacts: boolean;
}

export interface MergeResponse {
  success: boolean;
  message: string;
  exit_code: number;
  evidence_id: string | null;
  pull_warning: string | null;
}

export interface WorkspaceInfo {
  worktree_path: string;
  branch_name: string;
}

export interface LastMergeAttempt {
  event_type: string;
  reason: string;
  created_at: string;
  payload?: {
    pull_warning?: string;
    [key: string]: unknown;
  } | null;
}

export interface MergeStatusResponse {
  ticket_id: string;
  can_merge: boolean;
  is_merged: boolean;
  has_approved_revision: boolean;
  workspace: WorkspaceInfo | null;
  last_merge_attempt: LastMergeAttempt | null;
}

// ==================== Job Types ====================

export const JobKind = {
  EXECUTE: "execute",
  VERIFY: "verify",
  RESUME: "resume",
} as const;

export type JobKind = (typeof JobKind)[keyof typeof JobKind];

export const JobStatus = {
  QUEUED: "queued",
  RUNNING: "running",
  SUCCEEDED: "succeeded",
  FAILED: "failed",
  CANCELED: "canceled",
} as const;

export type JobStatus = (typeof JobStatus)[keyof typeof JobStatus];

export interface Job {
  id: string;
  ticket_id: string;
  kind: JobKind;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  log_path: string | null;
  celery_task_id?: string | null;
}

export interface JobListResponse {
  jobs: Job[];
  total: number;
}

export interface QueuedJob {
  id: string;
  ticket_id: string;
  ticket_title: string;
  kind: JobKind;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  queue_position: number | null;
}

export interface QueueStatusResponse {
  running: QueuedJob[];
  queued: QueuedJob[];
  total_running: number;
  total_queued: number;
}

// ==================== Cleanup Types ====================

export interface CleanupRequest {
  dry_run: boolean;
  delete_worktrees: boolean;
  delete_evidence: boolean;
}

export interface CleanupResponse {
  dry_run: boolean;
  worktrees_deleted: number;
  worktrees_failed: number;
  evidence_files_deleted: number;
  evidence_files_failed: number;
  bytes_freed: number;
  details: string[];
}

// ==================== Queued Message Types ====================

export interface QueuedMessageStatus {
  status: "empty" | "queued";
  message: string | null;
  queued_at: string | null;
}
