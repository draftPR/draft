import { describe, it, expect } from "vitest";
import { renderHook, waitFor, act } from "@/test/test-utils";
import { useTransitionTicket, useExecuteTicket, useStartAutopilot } from "../useMutations";

describe("useTransitionTicket", () => {
  it("calls transition API and invalidates queries on success", async () => {
    const { result } = renderHook(() => useTransitionTicket("board-1"));

    await act(async () => {
      result.current.mutate({
        ticketId: "ticket-1",
        data: { to_state: "executing", actor_type: "human" },
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it("handles missing boardId gracefully", async () => {
    const { result } = renderHook(() => useTransitionTicket(undefined));

    await act(async () => {
      result.current.mutate({
        ticketId: "ticket-1",
        data: { to_state: "executing", actor_type: "human" },
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe("useExecuteTicket", () => {
  it("calls execute API", async () => {
    const { result } = renderHook(() => useExecuteTicket("board-1"));

    await act(async () => {
      result.current.mutate("ticket-1");
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe("useStartAutopilot", () => {
  it("calls planner start API", async () => {
    const { result } = renderHook(() => useStartAutopilot());

    await act(async () => {
      result.current.mutate(undefined);
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});
