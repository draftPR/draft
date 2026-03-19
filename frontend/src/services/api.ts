/**
 * API service layer for backend communication
 */

import { config } from "@/config";
import type {
  AgentInfo,
  AgentListResponse,
  AgentLogsResponse,
  Board,
  BoardCreate,
  BoardListResponse,
  BoardResponse,
  BulkAcceptRequest,
  BulkAcceptResponse,
  BulkPriorityUpdateRequest,
  BulkPriorityUpdateResponse,
  CleanupRequest,
  CleanupResponse,
  CreatePRRequest,
  DashboardResponse,
  DiscoverReposRequest,
  DiscoverReposResponse,
  EvidenceListResponse,
  FeedbackBundle,
  GenerateTicketsResponse,
  Goal,
  GoalCreate,
  GoalListResponse,
  GoalUpdate,
  Job,
  JobListResponse,
  MergeRequest,
  MergeResponse,
  MergeStatusResponse,
  OrchestratorLogEntry,
  OrchestratorLogsResponse,
  PlannerConfigResponse,
  PlannerConfigUpdate,
  PlannerHealthResponse,
  PlannerStartRequest,
  PlannerStartResponse,
  PlannerStatusResponse,
  PlannerTickResponse,
  PRStatus,
  QueuedMessageStatus,
  QueueStatusResponse,
  RecentEvent,
  ReflectionResult,
  ReviewComment,
  ReviewCommentCreate,
  ReviewCommentListResponse,
  ReviewSubmit,
  ReviewSummary,
  RevisionDetail,
  RevisionDiffResponse,
  RevisionListResponse,
  SessionInfo,
  StreamCallbackData,
  StreamNormalizedEntry,
  SystemStatusResponse,
  Ticket,
  TicketAgentLogsResponse,
  TicketCreate,
  TicketEventListResponse,
  TicketTransition,
  TicketUpdate,
} from "@/types/api";

// Re-export types that were previously defined here, so existing imports don't break
export type {
  AgentInfo,
  AgentListResponse,
  AgentLogsResponse,
  CreatePRRequest,
  DashboardResponse,
  JobExecutionSummary,
  OrchestratorLogEntry,
  OrchestratorLogsResponse,
  PRStatus,
  QueueStatusResponse,
  RecentEvent,
  SessionInfo,
  StreamCallbackData,
  StreamNormalizedEntry,
  SystemStatusResponse,
  TicketAgentLogsResponse,
  BudgetStatus,
  SprintMetrics,
  AgentMetrics,
} from "@/types/api";

// ==================== Board Config API ====================

export interface ExecutorModel {
  id: string;
  name: string;
  description: string;
}

export async function getBoardConfig(boardId: string): Promise<{ has_overrides: boolean; config: any }> {
  return apiFetch<{ has_overrides: boolean; config: any }>(`/boards/${boardId}/config`);
}

export async function updateBoardConfig(boardId: string, config: Record<string, any>): Promise<void> {
  return apiFetch<void>(`/boards/${boardId}/config`, {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

export async function clearBoardConfig(boardId: string): Promise<void> {
  return apiFetch<void>(`/boards/${boardId}/config`, {
    method: "DELETE",
  });
}

export async function getExecutorModels(executor: string): Promise<ExecutorModel[]> {
  return apiFetch<ExecutorModel[]>(`/executors/${executor}/models`);
}

export interface ExecutorProfile {
  name: string;
  executor_type: string;
  timeout: number;
  extra_flags: string[];
  model: string | null;
  env: Record<string, string>;
}

export async function fetchExecutorProfiles(boardId?: string): Promise<ExecutorProfile[]> {
  const params = boardId ? `?board_id=${boardId}` : "";
  return apiFetch<ExecutorProfile[]>(`/executors/profiles${params}`);
}

export async function saveExecutorProfiles(
  profiles: ExecutorProfile[],
  boardId?: string,
): Promise<ExecutorProfile[]> {
  const params = boardId ? `?board_id=${boardId}` : "";
  return apiFetch<ExecutorProfile[]>(`/executors/profiles${params}`, {
    method: "PUT",
    body: JSON.stringify(profiles),
  });
}

export async function deleteBoard(boardId: string): Promise<void> {
  return apiFetch<void>(`/boards/${boardId}`, {
    method: "DELETE",
  });
}

export async function deleteAllTickets(boardId: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/boards/${boardId}/tickets`, {
    method: "DELETE",
  });
}

// ==================== Global Settings API ====================

export async function getGlobalSettings(boardId?: string): Promise<{ board_id: string; config_path: string; execute_config: any }> {
  const params = boardId ? `?board_id=${boardId}` : "";
  return apiFetch<{ board_id: string; config_path: string; execute_config: any }>(`/settings${params}`);
}

export async function updateGlobalSettings(settings: Record<string, any>, boardId?: string): Promise<void> {
  const params = boardId ? `?board_id=${boardId}` : "";
  return apiFetch<void>(`/settings${params}`, {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}

// ==================== Planner Config API ====================

export async function fetchPlannerConfig(boardId?: string): Promise<PlannerConfigResponse> {
  const params = boardId ? `?board_id=${boardId}` : "";
  return apiFetch<PlannerConfigResponse>(`/settings/planner${params}`);
}

export async function updatePlannerConfig(data: PlannerConfigUpdate, boardId?: string): Promise<PlannerConfigResponse> {
  const params = boardId ? `?board_id=${boardId}` : "";
  return apiFetch<PlannerConfigResponse>(`/settings/planner${params}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function checkPlannerHealth(boardId?: string): Promise<PlannerHealthResponse> {
  const params = boardId ? `?board_id=${boardId}` : "";
  return apiFetch<PlannerHealthResponse>(`/settings/planner/check${params}`);
}

export interface AgentTestResponse {
  status: "ok" | "error";
  executor: string;
  response: string | null;
  error: string | null;
  duration_ms: number;
}

export async function testExecutor(boardId?: string): Promise<AgentTestResponse> {
  const params = boardId ? `?board_id=${boardId}` : "";
  return apiFetch<AgentTestResponse>(`/executors/test${params}`, {
    method: "POST",
  });
}

const API_BASE = config.backendBaseUrl;

/**
 * Typed API error that preserves the HTTP status code.
 */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

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
    const errorData = await response.json().catch((parseErr) => {
      console.error(`Failed to parse error response JSON from ${endpoint}:`, parseErr);
      return {};
    });
    const message = errorData.detail || `HTTP error ${response.status}`;
    throw new ApiError(message, response.status);
  }

  // Handle 204 No Content (no body to parse)
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// ==================== Board API ====================

/**
 * Fetch all boards
 */
export async function fetchBoards(): Promise<BoardListResponse> {
  return apiFetch<BoardListResponse>("/boards");
}

/**
 * Fetch a single board by ID
 */
export async function fetchBoardById(boardId: string): Promise<Board> {
  return apiFetch<Board>(`/boards/${boardId}`);
}

/**
 * Fetch the board with all tickets grouped by state
 *
 * @param boardId - Optional board ID. If not provided, uses legacy /board endpoint
 */
export async function fetchBoard(boardId?: string): Promise<BoardResponse> {
  if (boardId) {
    return apiFetch<BoardResponse>(`/boards/${boardId}/board`);
  }
  return apiFetch<BoardResponse>("/board");
}

/**
 * Create a new board
 */
export async function createBoard(board: BoardCreate): Promise<Board> {
  return apiFetch<Board>("/boards", {
    method: "POST",
    body: JSON.stringify(board),
  });
}

/**
 * Discover git repositories in specified paths
 */
export async function discoverRepos(request: DiscoverReposRequest): Promise<DiscoverReposResponse> {
  return apiFetch<DiscoverReposResponse>("/repos/discover", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

/**
 * Delete a single ticket
 */
export async function deleteTicket(ticketId: string): Promise<void> {
  return apiFetch<void>(`/tickets/${ticketId}`, {
    method: "DELETE",
  });
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
export async function fetchGoals(boardId?: string): Promise<GoalListResponse> {
  const query = boardId ? `?board_id=${encodeURIComponent(boardId)}` : "";
  return apiFetch<GoalListResponse>(`/goals${query}`);
}

/**
 * Update a goal (supports partial updates including autonomy settings)
 */
export async function updateGoal(goalId: string, data: GoalUpdate): Promise<Goal> {
  return apiFetch<Goal>(`/goals/${goalId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

/**
 * Delete a goal and all its associated tickets, jobs, and data (cascade delete)
 */
export async function deleteGoal(goalId: string): Promise<void> {
  return apiFetch<void>(`/goals/${goalId}`, {
    method: "DELETE",
  });
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
 * Update a ticket's title, description, or priority (partial update)
 */
export async function updateTicket(
  ticketId: string,
  data: TicketUpdate
): Promise<Ticket> {
  return apiFetch<Ticket>(`/tickets/${ticketId}`, {
    method: "PATCH",
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
export async function executeTicket(ticketId: string, executorProfile?: string): Promise<Job> {
  const url = executorProfile
    ? `/tickets/${ticketId}/execute?executor_profile=${encodeURIComponent(executorProfile)}`
    : `/tickets/${ticketId}/execute`;
  return apiFetch<Job>(url, {
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
 * Fetch tickets that are blocked by this ticket (downstream dependencies)
 */
export async function fetchTicketDependents(
  ticketId: string
): Promise<Ticket[]> {
  return apiFetch<Ticket[]>(`/tickets/${ticketId}/dependents`);
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
 * Create EventSource for streaming job logs via the optimized SSE endpoint.
 * 
 * This uses the hybrid in-memory + Redis streaming for ultra-low latency (<10ms).
 * Each event type corresponds to a log level (stdout, stderr, info, error, progress, normalized, finished).
 */
export function streamAgentLogs(
  jobId: string,
  onMessage: (data: StreamCallbackData) => void,
  onError?: (error: Event) => void
): EventSource {
  const eventSource = new EventSource(`${API_BASE}/jobs/${jobId}/logs/stream`);
  
  // Handle different event types
  const handleEvent = (event: MessageEvent, level: string) => {
    try {
      const content = event.data;
      
      if (level === "finished") {
        onMessage({ status: "completed" });
        eventSource.close();
        return;
      }
      
      if (level === "error") {
        onMessage({ error: content });
        return;
      }
      
      if (level === "progress") {
        // Progress events may contain JSON with percentage
        try {
          const data = JSON.parse(content);
          onMessage({ progress: data.progress_pct, stage: data.stage });
        } catch {
          onMessage({ content });
        }
        return;
      }
      
      if (level === "normalized") {
        // Normalized log entry from cursor-agent JSON parsing
        try {
          const entry = JSON.parse(content) as StreamNormalizedEntry;
          entry.timestamp = entry.timestamp || new Date().toISOString();
          onMessage({ normalized: entry });
        } catch (e) {
          console.error("Failed to parse normalized entry:", e);
          onMessage({ content: content + "\n" });
        }
        return;
      }
      
      // stdout, stderr, info
      onMessage({ content: content + "\n" });
    } catch (e) {
      console.error("Failed to parse agent log:", e);
    }
  };
  
  // Listen to all event types
  eventSource.addEventListener("stdout", (e) => handleEvent(e as MessageEvent, "stdout"));
  eventSource.addEventListener("stderr", (e) => handleEvent(e as MessageEvent, "stderr"));
  eventSource.addEventListener("info", (e) => handleEvent(e as MessageEvent, "info"));
  eventSource.addEventListener("error", (e) => handleEvent(e as MessageEvent, "error"));
  eventSource.addEventListener("progress", (e) => handleEvent(e as MessageEvent, "progress"));
  eventSource.addEventListener("normalized", (e) => handleEvent(e as MessageEvent, "normalized"));
  eventSource.addEventListener("finished", (e) => handleEvent(e as MessageEvent, "finished"));
  
  // Fallback for untyped messages
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch {
      onMessage({ content: event.data + "\n" });
    }
  };
  
  if (onError) {
    eventSource.onerror = onError;
  }
  
  return eventSource;
}

// ==================== Queued Message API ====================

/**
 * Queue a follow-up message for a ticket.
 * 
 * This enables instant follow-up UX: while the agent is working,
 * you can type the next instruction. When execution completes,
 * the queued message auto-executes.
 */
export async function queueFollowupMessage(
  ticketId: string,
  message: string
): Promise<QueuedMessageStatus> {
  return apiFetch<QueuedMessageStatus>(`/tickets/${ticketId}/queue`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

/**
 * Get the queued message status for a ticket
 */
export async function getQueuedMessage(
  ticketId: string
): Promise<QueuedMessageStatus> {
  return apiFetch<QueuedMessageStatus>(`/tickets/${ticketId}/queue`);
}

/**
 * Cancel a queued message for a ticket
 */
export async function cancelQueuedMessage(
  ticketId: string
): Promise<QueuedMessageStatus> {
  return apiFetch<QueuedMessageStatus>(`/tickets/${ticketId}/queue`, {
    method: "DELETE",
  });
}

// ==================== Conflict Resolution API ====================

import type {
  ConflictStatusResponse,
  RebaseResponse,
  AbortResponse,
  PushResponse,
  PushStatusResponse,
  PRComment,
  AddPRCommentRequest,
  MergePRRequest,
} from "@/types/api";

export async function fetchConflictStatus(
  ticketId: string
): Promise<ConflictStatusResponse> {
  return apiFetch<ConflictStatusResponse>(`/tickets/${ticketId}/conflict-status`);
}

export async function rebaseTicket(
  ticketId: string,
  ontoBranch: string = "main"
): Promise<RebaseResponse> {
  return apiFetch<RebaseResponse>(
    `/tickets/${ticketId}/rebase?onto_branch=${encodeURIComponent(ontoBranch)}`,
    { method: "POST" }
  );
}

export async function continueRebase(
  ticketId: string
): Promise<RebaseResponse> {
  return apiFetch<RebaseResponse>(`/tickets/${ticketId}/continue-rebase`, {
    method: "POST",
  });
}

export async function abortConflict(
  ticketId: string
): Promise<AbortResponse> {
  return apiFetch<AbortResponse>(`/tickets/${ticketId}/abort-conflict`, {
    method: "POST",
  });
}

// ==================== Push API ====================

/**
 * Check if a ticket's branch needs to be pushed to remote
 */
export async function fetchPushStatus(
  ticketId: string
): Promise<PushStatusResponse> {
  return apiFetch<PushStatusResponse>(`/tickets/${ticketId}/push-status`);
}

/**
 * Push a ticket's branch to remote
 */
export async function pushTicketBranch(
  ticketId: string
): Promise<PushResponse> {
  return apiFetch<PushResponse>(`/tickets/${ticketId}/push`, {
    method: "POST",
  });
}

/**
 * Force-push a ticket's branch to remote (uses --force-with-lease)
 */
export async function forcePushTicketBranch(
  ticketId: string
): Promise<PushResponse> {
  return apiFetch<PushResponse>(`/tickets/${ticketId}/force-push`, {
    method: "POST",
  });
}

// ==================== PR Comments & Merge API ====================

/**
 * Add a comment to a ticket's PR
 */
export async function addPRComment(
  ticketId: string,
  body: string
): Promise<{ success: boolean; message: string }> {
  return apiFetch<{ success: boolean; message: string }>(
    `/pull-requests/${ticketId}/comments`,
    {
      method: "POST",
      body: JSON.stringify({ body } satisfies AddPRCommentRequest),
    }
  );
}

/**
 * List all comments on a ticket's PR
 */
export async function listPRComments(
  ticketId: string
): Promise<PRComment[]> {
  return apiFetch<PRComment[]>(`/pull-requests/${ticketId}/comments`);
}

/**
 * Merge a ticket's PR on GitHub
 */
export async function mergePR(
  ticketId: string,
  strategy: MergePRRequest["strategy"] = "squash"
): Promise<{ success: boolean; message: string }> {
  return apiFetch<{ success: boolean; message: string }>(
    `/pull-requests/${ticketId}/merge`,
    {
      method: "POST",
      body: JSON.stringify({ strategy } satisfies MergePRRequest),
    }
  );
}

// ==================== Dashboard API ====================

/**
 * Fetch dashboard data with metrics and budget status
 */
export async function fetchDashboard(
  goalId?: string,
  dailyBudget: number = 10,
  weeklyBudget: number = 50,
  monthlyBudget: number = 150
): Promise<DashboardResponse> {
  const params = new URLSearchParams();
  if (goalId) params.set("goal_id", goalId);
  params.set("daily_budget", dailyBudget.toString());
  params.set("weekly_budget", weeklyBudget.toString());
  params.set("monthly_budget", monthlyBudget.toString());
  return apiFetch<DashboardResponse>(`/dashboard?${params.toString()}`);
}

// ==================== Agents API ====================

/**
 * Fetch all available AI agents
 */
export async function fetchAgents(): Promise<AgentListResponse> {
  return apiFetch<AgentListResponse>("/agents");
}

/**
 * Fetch only available agents
 */
export async function fetchAvailableAgents(): Promise<string[]> {
  return apiFetch<string[]>("/agents/available");
}

/**
 * Fetch agent info by type
 */
export async function fetchAgentInfo(agentType: string): Promise<AgentInfo> {
  return apiFetch<AgentInfo>(`/agents/${agentType}`);
}

/**
 * Fetch agent sessions for a ticket
 */
export async function fetchTicketSessions(
  ticketId: string,
  includeEnded: boolean = false
): Promise<{ sessions: SessionInfo[]; total: number }> {
  const params = new URLSearchParams({ include_ended: String(includeEnded) });
  return apiFetch<{ sessions: SessionInfo[]; total: number }>(
    `/agents/sessions/ticket/${ticketId}?${params.toString()}`
  );
}

/**
 * Normalized Logs API
 */
import type { NormalizedLogEntry } from "@/types/logs";

/**
 * Fetch normalized logs for a job
 */
export async function getNormalizedLogs(
  jobId: string
): Promise<NormalizedLogEntry[]> {
  return apiFetch<NormalizedLogEntry[]>(`/jobs/${jobId}/normalized-logs`);
}

/**
 * Trigger manual log normalization for a job
 */
export async function normalizeJobLogs(
  jobId: string,
  agentType: string = "claude"
): Promise<{ success: boolean; entries_created: number; message: string }> {
  return apiFetch<{ success: boolean; entries_created: number; message: string }>(
    `/jobs/${jobId}/normalize-logs?agent_type=${agentType}`,
    { method: "POST" }
  );
}

/**
 * Fetch all agent execution logs for a ticket (chain of thought, tool calls, etc.)
 */
export async function fetchTicketAgentLogs(
  ticketId: string,
  includeEntries: boolean = true
): Promise<TicketAgentLogsResponse> {
  const params = new URLSearchParams({ include_entries: String(includeEntries) });
  return apiFetch<TicketAgentLogsResponse>(
    `/tickets/${ticketId}/agent-logs?${params.toString()}`
  );
}

// ============================================================================
// Pull Request API
// ============================================================================

/**
 * Create a GitHub Pull Request for a ticket
 */
export async function createPullRequest(
  request: CreatePRRequest
): Promise<PRStatus> {
  return apiFetch<PRStatus>("/pull-requests", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

/**
 * Get PR status for a ticket
 */
export async function getPRStatus(ticketId: string): Promise<PRStatus> {
  return apiFetch<PRStatus>(`/pull-requests/${ticketId}`);
}

/**
 * Manually refresh PR status from GitHub
 */
export async function refreshPRStatus(ticketId: string): Promise<PRStatus> {
  return apiFetch<PRStatus>(`/pull-requests/${ticketId}/refresh`, {
    method: "POST",
  });
}
