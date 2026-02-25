import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@/test/test-utils";
import { useBoardsQuery, useBoardViewQuery, useTicketQuery, usePlannerStatusQuery } from "../useQueries";

describe("useBoardsQuery", () => {
  it("fetches boards list", async () => {
    const { result } = renderHook(() => useBoardsQuery());
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.boards).toHaveLength(1);
    expect(result.current.data?.boards[0].name).toBe("My Board");
  });
});

describe("useBoardViewQuery", () => {
  it("fetches board view when boardId is provided", async () => {
    const { result } = renderHook(() => useBoardViewQuery("board-1"));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.columns).toBeDefined();
    expect(result.current.data?.total_tickets).toBe(3);
  });

  it("is disabled when boardId is null", () => {
    const { result } = renderHook(() => useBoardViewQuery(null));
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useTicketQuery", () => {
  it("fetches ticket when id is provided", async () => {
    const { result } = renderHook(() => useTicketQuery("ticket-1"));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe("ticket-1");
  });

  it("is disabled when ticketId is null", () => {
    const { result } = renderHook(() => useTicketQuery(null));
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("usePlannerStatusQuery", () => {
  it("fetches planner status", async () => {
    const { result } = renderHook(() => usePlannerStatusQuery());
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeDefined();
  });
});
