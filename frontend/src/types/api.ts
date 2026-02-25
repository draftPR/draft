/**
 * TypeScript types matching backend API schemas.
 *
 * Backend-sourced types are re-exported from the auto-generated file (generated.ts).
 * Run `make generate-types` to regenerate from the FastAPI OpenAPI spec.
 *
 * Frontend-only constants (display names, colors, column order) are defined here.
 */

import type { components } from "./generated";
import type { NormalizedLogEntry } from "@/types/logs";

// ==================== Re-exported Backend Types ====================
// These are derived from the OpenAPI spec via `make generate-types`.
// Use `components["schemas"]["TypeName"]` to reference generated types.

// --- Enums (const objects + type aliases for erasableSyntaxOnly) ---

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

export type TicketState = components["schemas"]["TicketState"];

export const ActorType = {
  HUMAN: "human",
  PLANNER: "planner",
  SYSTEM: "system",
  EXECUTOR: "executor",
} as const;

export type ActorType = components["schemas"]["ActorType"];

export const EventType = {
  CREATED: "created",
  TRANSITIONED: "transitioned",
  UPDATED: "updated",
  COMMENT: "comment",
  MERGE_REQUESTED: "merge_requested",
  MERGE_SUCCEEDED: "merge_succeeded",
  MERGE_FAILED: "merge_failed",
  WORKTREE_CLEANED: "worktree_cleaned",
  WORKTREE_CLEANUP_FAILED: "worktree_cleanup_failed",
} as const;

export type EventType = components["schemas"]["EventType"];

export const EvidenceKind = {
  COMMAND_LOG: "command_log",
  TEST_REPORT: "test_report",
} as const;

export type EvidenceKind = components["schemas"]["EvidenceKind"];

export const RevisionStatus = {
  OPEN: "open",
  CHANGES_REQUESTED: "changes_requested",
  APPROVED: "approved",
  SUPERSEDED: "superseded",
} as const;

export type RevisionStatus = components["schemas"]["RevisionStatus"];

export const AuthorType = {
  HUMAN: "human",
  AGENT: "agent",
  SYSTEM: "system",
} as const;

export type AuthorType = components["schemas"]["AuthorType"];

export const ReviewDecision = {
  APPROVED: "approved",
  CHANGES_REQUESTED: "changes_requested",
} as const;

export type ReviewDecision = components["schemas"]["ReviewDecision"];

export const MergeStrategy = {
  MERGE: "merge",
  REBASE: "rebase",
} as const;

export type MergeStrategy = components["schemas"]["MergeStrategy"];

export const JobKind = {
  EXECUTE: "execute",
  VERIFY: "verify",
  RESUME: "resume",
} as const;

export type JobKind = components["schemas"]["JobKind"];

export const JobStatus = {
  QUEUED: "queued",
  RUNNING: "running",
  SUCCEEDED: "succeeded",
  FAILED: "failed",
  CANCELED: "canceled",
} as const;

export type JobStatus = components["schemas"]["JobStatus"];

export const PriorityBucket = {
  P0: "P0",
  P1: "P1",
  P2: "P2",
  P3: "P3",
} as const;

export type PriorityBucket = components["schemas"]["PriorityBucket"];

export const PlannerActionType = {
  ENQUEUED_EXECUTE: "enqueued_execute",
  PROPOSED_FOLLOWUP: "proposed_followup",
  GENERATED_REFLECTION: "generated_reflection",
  SKIPPED: "skipped",
} as const;

export type PlannerActionType =
  (typeof PlannerActionType)[keyof typeof PlannerActionType];

// --- Goal types ---
export type Goal = components["schemas"]["GoalResponse"];
// GoalCreate: autonomy fields have server defaults, so we make them optional for the frontend
export type GoalCreate = Pick<components["schemas"]["GoalCreate"], "title"> &
  Partial<Omit<components["schemas"]["GoalCreate"], "title">>;
export type GoalUpdate = components["schemas"]["GoalUpdate"];
export type GoalListResponse = components["schemas"]["GoalListResponse"];

// --- Ticket types ---
// Ticket extends TicketResponse with optional PR fields and is_blocked flag
export type Ticket = components["schemas"]["TicketResponse"] & {
  is_blocked?: boolean;
  pr_number?: number | null;
  pr_url?: string | null;
  pr_state?: string | null;
  pr_created_at?: string | null;
  pr_merged_at?: string | null;
  pr_head_branch?: string | null;
  pr_base_branch?: string | null;
};
// TicketCreate: actor_type has server default, so we make it optional for the frontend
export type TicketCreate = Pick<
  components["schemas"]["TicketCreate"],
  "goal_id" | "title"
> &
  Partial<
    Omit<components["schemas"]["TicketCreate"], "goal_id" | "title">
  >;
export type TicketTransition = components["schemas"]["TicketTransition"];

// --- Ticket Event types ---
export type TicketEvent = components["schemas"]["TicketEventResponse"];
export type TicketEventListResponse =
  components["schemas"]["TicketEventListResponse"];

// --- Evidence types ---
export type Evidence = components["schemas"]["EvidenceResponse"];
export type EvidenceListResponse =
  components["schemas"]["EvidenceListResponse"];

// --- Board types ---
export interface Board {
  id: string;
  name: string;
  description: string | null;
  repo_root: string;
  default_branch: string | null;
  created_at: string;
  updated_at: string;
}
export interface BoardCreate {
  name: string;
  description?: string | null;
  repo_root: string;
  default_branch?: string | null;
}
export type BoardListResponse = components["schemas"]["BoardListResponse"];
export type BoardRepo = components["schemas"]["BoardRepoResponse"];

// --- Repo discovery types ---
export type DiscoveredRepo = components["schemas"]["DiscoveredRepoResponse"];
export type DiscoverReposRequest =
  components["schemas"]["DiscoverReposRequest"];
export type DiscoverReposResponse =
  components["schemas"]["DiscoverReposResponse"];

export interface TicketsByState {
  state: TicketState;
  tickets: Ticket[];
}

export interface BoardResponse {
  columns: TicketsByState[];
  total_tickets: number;
}

// --- API Error type ---
export interface ApiError {
  detail: string;
  error_type?: string;
}

// --- Planner types ---
export interface ProposedTicket {
  id: string;
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

// --- Reflection types ---
export type SuggestedPriorityChange =
  components["schemas"]["SuggestedPriorityChange"];
export type ReflectionQuality = "good" | "needs_work" | "insufficient";
export interface ReflectionResult {
  overall_quality: ReflectionQuality;
  quality_notes: string;
  coverage_gaps: string[];
  suggested_changes: SuggestedPriorityChange[];
}

// --- Bulk priority update types ---
export type PriorityUpdate = components["schemas"]["PriorityUpdate"];
export interface BulkPriorityUpdateRequest {
  goal_id: string;
  updates: PriorityUpdate[];
  allow_p0?: boolean;
}
export type BulkPriorityUpdateResult =
  components["schemas"]["BulkPriorityUpdateResult"];
export type BulkPriorityUpdateResponse =
  components["schemas"]["BulkPriorityUpdateResponse"];

// --- Bulk accept types ---
export interface BulkAcceptRequest {
  ticket_ids: string[];
  goal_id?: string | null;
  actor_type?: ActorType;
  actor_id?: string | null;
  reason?: string | null;
  queue_first?: boolean;
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
  queued_job_id?: string | null;
  queued_ticket_id?: string | null;
}

// --- Planner tick types ---
export type PlannerAction = components["schemas"]["PlannerAction"];
export type PlannerTickResponse =
  components["schemas"]["PlannerTickResponse"];
export type PlannerStartRequest =
  components["schemas"]["PlannerStartRequest"];
export type PlannerStartResponse =
  components["schemas"]["PlannerStartResponse"];
export type PlannerFeaturesStatus =
  components["schemas"]["PlannerFeaturesStatus"];
export type LastTickStats = components["schemas"]["LastTickStats"];
export type LLMHealthCheck = components["schemas"]["LLMHealthCheck"];
export type PlannerStatusResponse =
  components["schemas"]["PlannerStatusResponse"];

// --- Revision types ---
export type Revision = components["schemas"]["RevisionResponse"];
export type RevisionDetail = components["schemas"]["RevisionDetailResponse"];
export type RevisionListResponse =
  components["schemas"]["RevisionListResponse"];
export type DiffFile = components["schemas"]["DiffFile"];
export interface RevisionDiffResponse {
  revision_id: string;
  diff_stat: string | null;
  diff_patch: string | null;
  files: DiffFile[];
}

// --- Review comment types ---
export type ReviewComment = components["schemas"]["ReviewCommentResponse"];
export interface ReviewCommentCreate {
  file_path: string;
  line_number: number;
  body: string;
  author_type?: AuthorType;
  hunk_header?: string | null;
  line_content?: string | null;
}
export type ReviewCommentListResponse =
  components["schemas"]["ReviewCommentListResponse"];

// --- Review summary types ---
export type ReviewSummary = components["schemas"]["ReviewSummaryResponse"];
export type ReviewSubmit = components["schemas"]["ReviewSubmit"];

// --- Feedback bundle types ---
export type FeedbackBundle = components["schemas"]["FeedbackBundle"];
export type FeedbackComment = components["schemas"]["FeedbackComment"];

// --- Merge types ---
export type MergeRequest = components["schemas"]["MergeRequest"];
export type MergeResponse = components["schemas"]["MergeResponse"];
export type MergeStatusResponse =
  components["schemas"]["MergeStatusResponse"];

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

// --- Job types ---
export type Job = components["schemas"]["JobResponse"];
export type JobListResponse = components["schemas"]["JobListResponse"];
export type QueuedJob = components["schemas"]["QueuedJobResponse"];

export interface QueueStatusResponse {
  running: QueuedJob[];
  queued: QueuedJob[];
  total_running: number;
  total_queued: number;
}

// --- Cleanup types ---
export type CleanupRequest = components["schemas"]["CleanupRequest"];
export type CleanupResponse = components["schemas"]["CleanupResponse"];

// --- Queued message types ---
export interface QueuedMessageStatus {
  status: "empty" | "queued";
  message: string | null;
  queued_at: string | null;
}

// --- Conflict resolution types ---
export type ConflictOp = "rebase" | "merge" | "cherry_pick" | "revert" | "unknown";

export interface ConflictStatusResponse {
  has_conflict: boolean;
  operation: ConflictOp | null;
  conflicted_files: string[];
  can_continue: boolean;
  can_abort: boolean;
  divergence: {
    ahead: number;
    behind: number;
    diverged: boolean;
    up_to_date: boolean;
  } | null;
}

export interface RebaseResponse {
  success: boolean;
  message: string;
  has_conflicts: boolean;
  conflicted_files: string[];
}

export interface AbortResponse {
  success: boolean;
  message: string;
}

// --- Push types ---
export interface PushResponse {
  success: boolean;
  message: string;
}

export interface PushStatusResponse {
  ahead: number;
  behind: number;
  remote_exists: boolean;
  needs_push: boolean;
}

// --- PR comment/merge types ---
export interface PRComment {
  author: string;
  body: string;
  created_at: string;
}

export interface AddPRCommentRequest {
  body: string;
}

export type PRMergeStrategy = "squash" | "merge" | "rebase";

export interface MergePRRequest {
  strategy: PRMergeStrategy;
}

// --- Debug types ---
export type OrchestratorLogEntry =
  components["schemas"]["OrchestratorLogEntry"];
export type OrchestratorLogsResponse =
  components["schemas"]["OrchestratorLogsResponse"];

export interface AgentLogEntry {
  timestamp: string;
  job_id: string;
  ticket_id: string;
  ticket_title: string;
  kind: string;
  content: string;
}

export interface AgentLogsResponse {
  logs: AgentLogEntry[];
  job_id: string | null;
  ticket_title: string | null;
}

export type RunningJobInfo = components["schemas"]["RunningJobInfo"];
export type SystemStatusResponse =
  components["schemas"]["SystemStatusResponse"];

export interface RecentEvent {
  id: string;
  ticket_id: string;
  ticket_title: string | null;
  event_type: string;
  actor_type: string;
  actor_id: string;
  payload: Record<string, unknown> | null;
  created_at: string;
}

// --- Streaming types ---
export interface StreamLogMessage {
  level:
    | "stdout"
    | "stderr"
    | "info"
    | "error"
    | "progress"
    | "normalized"
    | "finished";
  content: string;
  timestamp: string;
  progress_pct?: number;
  stage?: string;
}

export interface StreamNormalizedEntry {
  entry_type:
    | "system_message"
    | "assistant_message"
    | "thinking"
    | "tool_use"
    | "error_message";
  content: string;
  sequence: number;
  tool_name?: string | null;
  action_type?: string | null;
  tool_status?: string | null;
  metadata?: Record<string, any>;
  timestamp?: string;
}

export interface StreamCallbackData {
  content?: string;
  error?: string;
  status?: string;
  progress?: number;
  stage?: string;
  normalized?: StreamNormalizedEntry;
}

// --- Dashboard types ---
export type BudgetStatus = components["schemas"]["BudgetStatus"];
export type SprintMetrics = components["schemas"]["SprintMetrics"];
export type AgentMetrics = components["schemas"]["AgentMetrics"];
export type CostTrendItem = components["schemas"]["CostTrendItem"];
export interface DashboardResponse {
  budget: BudgetStatus;
  sprint: SprintMetrics;
  agent: AgentMetrics;
  cost_trend: CostTrendItem[];
}

// --- Agent types ---
export type AgentInfo = components["schemas"]["AgentInfo"];
export type AgentListResponse = components["schemas"]["AgentListResponse"];
export type SessionInfo = components["schemas"]["SessionInfo"];

// --- Agent log types ---
export interface JobExecutionSummary {
  job_id: string;
  job_kind: string;
  job_status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  entry_count: number;
  entries: NormalizedLogEntry[];
}

export interface TicketAgentLogsResponse {
  ticket_id: string;
  ticket_title: string;
  total_entries: number;
  total_jobs: number;
  executions: JobExecutionSummary[];
}

// --- Pull request types ---
export type PRStatus = components["schemas"]["PRStatusResponse"];
export type CreatePRRequest = components["schemas"]["CreatePRRequest"];

// --- Planner config types ---
export interface PlannerConfigResponse {
  model: string;
  agent_path: string;
  timeout: number;
}

export interface PlannerConfigUpdate {
  model?: string;
  agent_path?: string;
}

export interface PlannerHealthResponse {
  status: "online" | "offline";
  model: string;
  error?: string;
}

// ==================== Frontend-Only Constants ====================

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
