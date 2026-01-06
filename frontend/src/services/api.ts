/**
 * API service layer for backend communication
 */

import { config } from "@/config";
import type {
  BoardResponse,
  EvidenceListResponse,
  Goal,
  GoalCreate,
  GoalListResponse,
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

