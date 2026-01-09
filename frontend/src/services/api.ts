/**
 * API service layer for backend communication
 */

import { config } from "@/config";
import type {
  BoardResponse,
  BulkAcceptRequest,
  BulkAcceptResponse,
  BulkPriorityUpdateRequest,
  BulkPriorityUpdateResponse,
  CleanupRequest,
  CleanupResponse,
  EvidenceListResponse,
  FeedbackBundle,
  GenerateTicketsResponse,
  Goal,
  GoalCreate,
  GoalListResponse,
  Job,
  JobListResponse,
  MergeRequest,
  MergeResponse,
  MergeStatusResponse,
  PlannerStartRequest,
  PlannerStartResponse,
  PlannerStatusResponse,
  PlannerTickResponse,
  QueueStatusResponse,
  ReflectionResult,
  ReviewComment,
  ReviewCommentCreate,
  ReviewCommentListResponse,
  ReviewSubmit,
  ReviewSummary,
  RevisionDetail,
  RevisionDiffResponse,
  RevisionListResponse,
  Ticket,
  TicketCreate,
  TicketEventListResponse,
  TicketTransition,
} from "@/types/api";

const API_BASE = config.backendBaseUrl;

/**
 * Generic fetch wrapper with error handling
 */
async function apiFetch<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const message = errorData.detail || `HTTP error ${response.status}`;
    throw new Error(message);
  }

  return response.json();
}

/**
 * Fetch the board with all tickets grouped by state
 */
export async function fetchBoard(): Promise<BoardResponse> {
  return apiFetch<BoardResponse>("/board");
}

/**
 * Fetch events for a specific ticket
 */
export async function fetchTicketEvents(
  ticketId: string
): Promise<TicketEventListResponse> {
  return apiFetch<TicketEventListResponse>(`/tickets/${ticketId}/events`);
}

/**
 * Create a new goal
 */
export async function createGoal(data: GoalCreate): Promise<Goal> {
  return apiFetch<Goal>("/goals", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Fetch all goals
 */
export async function fetchGoals(): Promise<GoalListResponse> {
  return apiFetch<GoalListResponse>("/goals");
}

/**
 * Create a new ticket
 */
export async function createTicket(data: TicketCreate): Promise<Ticket> {
  return apiFetch<Ticket>("/tickets", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Transition a ticket to a new state
 */
export async function transitionTicket(
  ticketId: string,
  data: TicketTransition
): Promise<Ticket> {
  return apiFetch<Ticket>(`/tickets/${ticketId}/transition`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Fetch a single ticket by ID
 */
export async function fetchTicket(ticketId: string): Promise<Ticket> {
  return apiFetch<Ticket>(`/tickets/${ticketId}`);
}

/**
 * Execute a single ticket immediately
 * 
 * This creates an execute job for the ticket and queues it for processing.
 * Valid for tickets in PLANNED, NEEDS_HUMAN, or DONE state.
 * 
 * @returns The created job
 */
export async function executeTicket(ticketId: string): Promise<Job> {
  return apiFetch<Job>(`/tickets/${ticketId}/execute`, {
    method: "POST",
  });
}

/**
 * Fetch all verification evidence for a ticket
 */
export async function fetchTicketEvidence(
  ticketId: string
): Promise<EvidenceListResponse> {
  return apiFetch<EvidenceListResponse>(`/tickets/${ticketId}/evidence`);
}

/**
 * Fetch stdout content for an evidence record
 */
export async function fetchEvidenceStdout(evidenceId: string): Promise<string> {
  const url = `${API_BASE}/evidence/${evidenceId}/stdout`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP error ${response.status}`);
  }
  return response.text();
}

/**
 * Fetch stderr content for an evidence record
 */
export async function fetchEvidenceStderr(evidenceId: string): Promise<string> {
  const url = `${API_BASE}/evidence/${evidenceId}/stderr`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP error ${response.status}`);
  }
  return response.text();
}

/**
 * Fetch a single goal by ID
 */
export async function fetchGoal(goalId: string): Promise<Goal> {
  return apiFetch<Goal>(`/goals/${goalId}`);
}

/**
 * Generate proposed tickets for a goal using AI planner
 */
export async function generateTicketsForGoal(
  goalId: string,
  workspacePath?: string
): Promise<GenerateTicketsResponse> {
  return apiFetch<GenerateTicketsResponse>(`/goals/${goalId}/generate-tickets`, {
    method: "POST",
    body: JSON.stringify({ workspace_path: workspacePath || "." }),
  });
}

/**
 * Bulk accept proposed tickets (transition from proposed to planned)
 */
export async function bulkAcceptTickets(
  data: BulkAcceptRequest
): Promise<BulkAcceptResponse> {
  return apiFetch<BulkAcceptResponse>("/tickets/accept", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Reflect on proposed tickets for a goal (AI evaluation)
 *
 * Returns suggestions for priority changes and coverage gaps.
 * Use bulkUpdatePriorities() to apply the suggested changes.
 */
export async function reflectOnTickets(
  goalId: string
): Promise<ReflectionResult> {
  return apiFetch<ReflectionResult>(`/goals/${goalId}/reflect-on-tickets`, {
    method: "POST",
  });
}

/**
 * Bulk update ticket priorities
 *
 * Used to apply priority suggestions from reflection.
 */
export async function bulkUpdatePriorities(
  data: BulkPriorityUpdateRequest
): Promise<BulkPriorityUpdateResponse> {
  return apiFetch<BulkPriorityUpdateResponse>("/tickets/bulk-update-priority", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Run one planner decision cycle (Autopilot tick)
 * 
 * NOTE: For normal operation, use runPlannerStart() instead.
 * This is mainly for debugging/manual control.
 */
export async function runPlannerTick(): Promise<PlannerTickResponse> {
  return apiFetch<PlannerTickResponse>("/planner/tick", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

/**
 * Start the autopilot and run until all planned tickets are processed.
 *
 * This is the main entry point for automated ticket processing:
 * - Queues all planned tickets ordered by priority
 * - Polls for completion - waits for each ticket to finish
 * - Continues until queue is empty or max duration reached
 * - Returns summary of all actions taken
 *
 * @param options - Optional configuration for poll interval and max duration
 */
export async function runPlannerStart(
  options?: PlannerStartRequest
): Promise<PlannerStartResponse> {
  return apiFetch<PlannerStartResponse>("/planner/start", {
    method: "POST",
    body: JSON.stringify(options || {}),
  });
}

/**
 * Get planner configuration status
 *
 * Returns info about which features are enabled, the LLM model,
 * and whether an API key is configured.
 *
 * @param healthCheck - If true, performs a live health check on the LLM (makes a minimal API call)
 */
export async function fetchPlannerStatus(
  healthCheck: boolean = false
): Promise<PlannerStatusResponse> {
  const params = healthCheck ? "?health_check=true" : "";
  return apiFetch<PlannerStatusResponse>(`/planner/status${params}`);
}

// ==================== Revision API ====================

/**
 * Fetch all revisions for a ticket
 */
export async function fetchTicketRevisions(
  ticketId: string
): Promise<RevisionListResponse> {
  return apiFetch<RevisionListResponse>(`/tickets/${ticketId}/revisions`);
}

/**
 * Fetch a single revision with diff content
 */
export async function fetchRevision(revisionId: string): Promise<RevisionDetail> {
  return apiFetch<RevisionDetail>(`/revisions/${revisionId}`);
}

/**
 * Fetch the diff content for a revision with parsed file information
 */
export async function fetchRevisionDiff(
  revisionId: string
): Promise<RevisionDiffResponse> {
  return apiFetch<RevisionDiffResponse>(`/revisions/${revisionId}/diff`);
}

// ==================== Review Comments API ====================

/**
 * Add an inline comment to a revision
 */
export async function addReviewComment(
  revisionId: string,
  data: ReviewCommentCreate
): Promise<ReviewComment> {
  return apiFetch<ReviewComment>(`/revisions/${revisionId}/comments`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Fetch all comments for a revision
 */
export async function fetchRevisionComments(
  revisionId: string,
  includeResolved: boolean = true
): Promise<ReviewCommentListResponse> {
  const params = new URLSearchParams();
  params.set("include_resolved", String(includeResolved));
  return apiFetch<ReviewCommentListResponse>(
    `/revisions/${revisionId}/comments?${params.toString()}`
  );
}

/**
 * Resolve a comment
 */
export async function resolveComment(commentId: string): Promise<ReviewComment> {
  return apiFetch<ReviewComment>(`/comments/${commentId}/resolve`, {
    method: "POST",
  });
}

/**
 * Unresolve a comment
 */
export async function unresolveComment(commentId: string): Promise<ReviewComment> {
  return apiFetch<ReviewComment>(`/comments/${commentId}/unresolve`, {
    method: "POST",
  });
}

// ==================== Review Decision API ====================

/**
 * Submit a review decision for a revision (approve or request changes)
 */
export async function submitReview(
  revisionId: string,
  data: ReviewSubmit
): Promise<ReviewSummary> {
  return apiFetch<ReviewSummary>(`/revisions/${revisionId}/review`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Fetch the feedback bundle for a revision
 */
export async function fetchFeedbackBundle(
  revisionId: string
): Promise<FeedbackBundle> {
  return apiFetch<FeedbackBundle>(`/revisions/${revisionId}/feedback-bundle`);
}

// ==================== Merge API ====================

/**
 * Merge a ticket's worktree branch into the default branch
 */
export async function mergeTicket(
  ticketId: string,
  data: MergeRequest
): Promise<MergeResponse> {
  return apiFetch<MergeResponse>(`/tickets/${ticketId}/merge`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Get merge status for a ticket
 */
export async function fetchMergeStatus(
  ticketId: string
): Promise<MergeStatusResponse> {
  return apiFetch<MergeStatusResponse>(`/tickets/${ticketId}/merge-status`);
}

// ==================== Job API ====================

/**
 * Fetch all jobs for a ticket
 */
export async function fetchTicketJobs(
  ticketId: string
): Promise<JobListResponse> {
  return apiFetch<JobListResponse>(`/tickets/${ticketId}/jobs`);
}

/**
 * Retry a failed job
 */
export async function retryJob(jobId: string): Promise<Job> {
  return apiFetch<Job>(`/jobs/${jobId}/retry`, {
    method: "POST",
  });
}

/**
 * Cancel a job
 */
export async function cancelJob(jobId: string): Promise<{ id: string; status: string; message: string }> {
  return apiFetch<{ id: string; status: string; message: string }>(`/jobs/${jobId}/cancel`, {
    method: "POST",
  });
}

/**
 * Fetch logs for a job (plain text)
 */
export async function fetchJobLogs(jobId: string): Promise<string> {
  const url = `${API_BASE}/jobs/${jobId}/logs`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP error ${response.status}`);
  }
  return response.text();
}

/**
 * Get queue status (running and queued jobs with ticket info)
 */
export async function fetchQueueStatus(): Promise<QueueStatusResponse> {
  return apiFetch<QueueStatusResponse>("/jobs/queue");
}

// ==================== Maintenance API ====================

/**
 * Run cleanup of stale worktrees and old evidence
 */
export async function runCleanup(data: CleanupRequest): Promise<CleanupResponse> {
  return apiFetch<CleanupResponse>("/maintenance/cleanup", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ==================== Debug API ====================

export interface OrchestratorLogEntry {
  timestamp: string;
  level: string;
  message: string;
  data: Record<string, unknown>;
}

export interface OrchestratorLogsResponse {
  logs: OrchestratorLogEntry[];
  total: number;
}

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

export interface RunningJobInfo {
  job_id: string;
  ticket_id: string;
  ticket_title: string;
  kind: string;
  started_at: string | null;
  log_preview: string | null;
}

export interface SystemStatusResponse {
  timestamp: string;
  running_jobs: RunningJobInfo[];
  queued_count: number;
  tickets_by_state: Record<string, number>;
  recent_events_count: number;
}

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

/**
 * Fetch orchestrator logs from in-memory buffer
 */
export async function fetchOrchestratorLogs(
  limit: number = 100,
  since?: string
): Promise<OrchestratorLogsResponse> {
  const params = new URLSearchParams({ limit: limit.toString() });
  if (since) params.append("since", since);
  return apiFetch<OrchestratorLogsResponse>(`/debug/orchestrator/logs?${params}`);
}

/**
 * Fetch agent logs for a specific job
 */
export async function fetchAgentLogs(jobId: string): Promise<AgentLogsResponse> {
  return apiFetch<AgentLogsResponse>(`/debug/agent/logs/${jobId}`);
}

/**
 * Fetch live system status for debug panel
 */
export async function fetchSystemStatus(): Promise<SystemStatusResponse> {
  return apiFetch<SystemStatusResponse>("/debug/status");
}

/**
 * Fetch recent ticket events for activity feed
 */
export async function fetchRecentEvents(limit: number = 50): Promise<RecentEvent[]> {
  return apiFetch<RecentEvent[]>(`/debug/events/recent?limit=${limit}`);
}

/**
 * Create EventSource for streaming orchestrator logs (SSE)
 */
export function streamOrchestratorLogs(
  onMessage: (log: OrchestratorLogEntry) => void,
  onError?: (error: Event) => void
): EventSource {
  const eventSource = new EventSource(`${API_BASE}/debug/orchestrator/stream`);
  
  eventSource.onmessage = (event) => {
    try {
      const log = JSON.parse(event.data) as OrchestratorLogEntry;
      onMessage(log);
    } catch (e) {
      console.error("Failed to parse orchestrator log:", e);
    }
  };
  
  if (onError) {
    eventSource.onerror = onError;
  }
  
  return eventSource;
}

/**
 * Create EventSource for streaming agent logs for a running job (SSE)
 */
export function streamAgentLogs(
  jobId: string,
  onMessage: (data: { content?: string; error?: string; status?: string }) => void,
  onError?: (error: Event) => void
): EventSource {
  const eventSource = new EventSource(`${API_BASE}/debug/agent/stream/${jobId}`);
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.error("Failed to parse agent log:", e);
    }
  };
  
  if (onError) {
    eventSource.onerror = onError;
  }
  
  return eventSource;
}
