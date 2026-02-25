import { describe, it, expect } from "vitest";
import { queryKeys } from "../queryKeys";

describe("queryKeys", () => {
  it("boards.all is a stable key", () => {
    expect(queryKeys.boards.all).toEqual(["boards"]);
  });

  it("boards.detail produces unique keys", () => {
    const key1 = queryKeys.boards.detail("a");
    const key2 = queryKeys.boards.detail("b");
    expect(key1).toEqual(["boards", "a"]);
    expect(key2).toEqual(["boards", "b"]);
    expect(key1).not.toEqual(key2);
  });

  it("boards.view includes view suffix", () => {
    expect(queryKeys.boards.view("x")).toEqual(["boards", "x", "view"]);
  });

  it("tickets keys work correctly", () => {
    expect(queryKeys.tickets.all).toEqual(["tickets"]);
    expect(queryKeys.tickets.detail("t1")).toEqual(["tickets", "t1"]);
  });

  it("goals keys include board scoping", () => {
    expect(queryKeys.goals.byBoard("b1")).toEqual(["goals", "board", "b1"]);
  });

  it("jobs keys include ticket scoping", () => {
    expect(queryKeys.jobs.byTicket("t1")).toEqual(["jobs", "ticket", "t1"]);
  });

  it("evidence keys include job and ticket scoping", () => {
    expect(queryKeys.evidence.byTicket("t1")).toEqual([
      "evidence",
      "ticket",
      "t1",
    ]);
    expect(queryKeys.evidence.byJob("j1")).toEqual(["evidence", "job", "j1"]);
  });

  it("executors keys are stable", () => {
    expect(queryKeys.executors.available).toEqual([
      "executors",
      "available",
    ]);
  });

  it("planner keys are stable", () => {
    expect(queryKeys.planner.status).toEqual(["planner", "status"]);
  });
});
