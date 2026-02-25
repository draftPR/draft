import { http, HttpResponse } from "msw";
import {
  createMockBoard,
  createMockGoal,
  createMockTicket,
  createMockBoardResponse,
  createMockPlannerStatus,
  createMockJob,
  createMockEvidence,
  createMockRevision,
} from "./data";
import { TicketState } from "@/types/api";

const BASE = "http://localhost:8000";

const defaultBoard = createMockBoard({ id: "board-1", name: "My Board" });
const defaultGoal = createMockGoal({
  id: "goal-1",
  board_id: "board-1",
  title: "Default Goal",
});
const defaultTickets = [
  createMockTicket({
    id: "ticket-1",
    title: "Planned Ticket",
    state: TicketState.PLANNED,
    goal_id: "goal-1",
  }),
  createMockTicket({
    id: "ticket-2",
    title: "Executing Ticket",
    state: TicketState.EXECUTING,
    goal_id: "goal-1",
  }),
  createMockTicket({
    id: "ticket-3",
    title: "Done Ticket",
    state: TicketState.DONE,
    goal_id: "goal-1",
  }),
];

export const handlers = [
  // Health
  http.get(`${BASE}/health`, () => HttpResponse.json({ status: "ok" })),

  // Boards
  http.get(`${BASE}/boards`, () =>
    HttpResponse.json({ boards: [defaultBoard] }),
  ),
  http.get(`${BASE}/boards/:boardId`, () =>
    HttpResponse.json(defaultBoard),
  ),
  http.get(`${BASE}/boards/:boardId/board`, () =>
    HttpResponse.json(createMockBoardResponse(defaultTickets)),
  ),
  http.post(`${BASE}/boards`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json(
      createMockBoard({ name: body.name as string }),
      { status: 201 },
    );
  }),

  // Goals
  http.get(`${BASE}/goals`, () =>
    HttpResponse.json({ goals: [defaultGoal] }),
  ),
  http.post(`${BASE}/goals`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json(
      createMockGoal({ title: body.title as string }),
      { status: 201 },
    );
  }),
  http.patch(`${BASE}/goals/:goalId`, () =>
    HttpResponse.json(defaultGoal),
  ),

  // Tickets
  http.get(`${BASE}/tickets/:ticketId`, ({ params }) => {
    const ticket = defaultTickets.find((t) => t.id === params.ticketId);
    if (ticket) return HttpResponse.json(ticket);
    return HttpResponse.json(defaultTickets[0]);
  }),
  http.post(`${BASE}/tickets`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json(
      createMockTicket({ title: body.title as string }),
      { status: 201 },
    );
  }),
  http.post(`${BASE}/tickets/:ticketId/transition`, ({ params }) =>
    HttpResponse.json(
      createMockTicket({
        id: params.ticketId as string,
        state: TicketState.EXECUTING,
      }),
    ),
  ),
  http.post(`${BASE}/tickets/:ticketId/execute`, ({ params }) =>
    HttpResponse.json(
      createMockJob({ ticket_id: params.ticketId as string }),
    ),
  ),
  http.delete(`${BASE}/tickets/:ticketId`, () =>
    new HttpResponse(null, { status: 204 }),
  ),
  http.get(`${BASE}/tickets/:ticketId/events`, () =>
    HttpResponse.json({ events: [] }),
  ),

  // Jobs
  http.get(`${BASE}/jobs`, () =>
    HttpResponse.json({ jobs: [createMockJob()] }),
  ),
  http.get(`${BASE}/jobs/:jobId`, () =>
    HttpResponse.json(createMockJob()),
  ),

  // Queue status
  http.get(`${BASE}/queue/status`, () =>
    HttpResponse.json({ queued: [], running: [], total_queued: 0, total_running: 0 }),
  ),

  // Evidence
  http.get(`${BASE}/tickets/:ticketId/evidence`, () =>
    HttpResponse.json({ evidence: [createMockEvidence()] }),
  ),
  http.get(`${BASE}/jobs/:jobId/evidence`, () =>
    HttpResponse.json({ evidence: [createMockEvidence()] }),
  ),

  // Revisions
  http.get(`${BASE}/tickets/:ticketId/revisions`, () =>
    HttpResponse.json({ revisions: [createMockRevision()] }),
  ),
  http.get(`${BASE}/revisions/:revisionId`, () =>
    HttpResponse.json(createMockRevision()),
  ),
  http.get(`${BASE}/revisions/:revisionId/diff`, () =>
    HttpResponse.json({
      revision_id: "rev-1",
      diff_stat: "+10 -2",
      diff_patch: "",
      files: [],
    }),
  ),
  http.get(`${BASE}/revisions/:revisionId/comments`, () =>
    HttpResponse.json({ comments: [] }),
  ),
  http.post(`${BASE}/revisions/:revisionId/comments`, () =>
    HttpResponse.json({ id: "comment-1" }, { status: 201 }),
  ),
  http.post(`${BASE}/revisions/:revisionId/review`, () =>
    HttpResponse.json({ id: "review-1" }),
  ),

  // Executors
  http.get(`${BASE}/executors/available`, () =>
    HttpResponse.json([
      { name: "claude", display_name: "Claude Code", available: true },
      { name: "cursor_agent", display_name: "Cursor Agent", available: false },
    ]),
  ),
  http.get(`${BASE}/executors/profiles`, () =>
    HttpResponse.json([]),
  ),

  // Planner
  http.get(`${BASE}/planner/status`, () =>
    HttpResponse.json(createMockPlannerStatus()),
  ),
  http.post(`${BASE}/planner/start`, () =>
    HttpResponse.json({ message: "Planner started" }),
  ),

  // Settings
  http.get(`${BASE}/settings`, () =>
    HttpResponse.json({}),
  ),
  http.put(`${BASE}/settings`, () =>
    HttpResponse.json({}),
  ),
  http.get(`${BASE}/settings/planner`, () =>
    HttpResponse.json({}),
  ),
  http.put(`${BASE}/settings/planner`, () =>
    HttpResponse.json({}),
  ),
  http.get(`${BASE}/settings/planner/check`, () =>
    HttpResponse.json({ healthy: true }),
  ),

  // Board config
  http.get(`${BASE}/boards/:boardId/config`, () =>
    HttpResponse.json({}),
  ),
  http.put(`${BASE}/boards/:boardId/config`, () =>
    HttpResponse.json({}),
  ),

  // Repos
  http.post(`${BASE}/repos/discover`, () =>
    HttpResponse.json({ repos: [] }),
  ),

  // Conflict & merge
  http.get(`${BASE}/tickets/:ticketId/conflict-status`, () =>
    HttpResponse.json({ has_conflict: false }),
  ),
  http.get(`${BASE}/tickets/:ticketId/merge-status`, () =>
    HttpResponse.json({ merged: false }),
  ),

  // Vite dev server wake endpoint
  http.get("/__api/wake-backend", () =>
    HttpResponse.json({ ok: true }),
  ),
];
