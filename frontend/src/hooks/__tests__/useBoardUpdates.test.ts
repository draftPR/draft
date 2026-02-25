import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@/test/test-utils";
import { useBoardUpdates } from "../useBoardUpdates";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  readyState = 1;
  send = vi.fn();
  close = vi.fn();

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
    setTimeout(() => this.onopen?.(), 0);
  }

  simulateMessage(data: object | string) {
    const payload = typeof data === "string" ? data : JSON.stringify(data);
    this.onmessage?.({ data: payload });
  }
}

describe("useBoardUpdates", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  it("returns disconnected when boardId is null", () => {
    const { result } = renderHook(() => useBoardUpdates(null));
    expect(result.current.status).toBe("disconnected");
    expect(result.current.isConnected).toBe(false);
  });

  it("connects when boardId is provided", async () => {
    const { result } = renderHook(() => useBoardUpdates("board-1"));

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    expect(MockWebSocket.instances[0].url).toContain("/ws/board/board-1");
  });

  it("subscribe receives messages", async () => {
    const listener = vi.fn();
    const { result } = renderHook(() => useBoardUpdates("board-1"));

    await waitFor(() => expect(result.current.isConnected).toBe(true));

    act(() => {
      result.current.subscribe(listener);
    });

    act(() => {
      MockWebSocket.instances[0].simulateMessage({
        type: "ticket_update",
        ticket_id: "t1",
      });
    });

    expect(listener).toHaveBeenCalledWith(
      expect.objectContaining({ type: "ticket_update", ticket_id: "t1" }),
    );
  });

  it("tracks lastUpdate", async () => {
    const { result } = renderHook(() => useBoardUpdates("board-1"));

    await waitFor(() => expect(result.current.isConnected).toBe(true));

    act(() => {
      MockWebSocket.instances[0].simulateMessage({
        type: "job_completed",
        job_id: "j1",
      });
    });

    expect(result.current.lastUpdate?.type).toBe("job_completed");
  });

  it("unsubscribe removes listener", async () => {
    const listener = vi.fn();
    const { result } = renderHook(() => useBoardUpdates("board-1"));

    await waitFor(() => expect(result.current.isConnected).toBe(true));

    let unsub: () => void;
    act(() => {
      unsub = result.current.subscribe(listener);
    });

    act(() => unsub());

    act(() => {
      MockWebSocket.instances[0].simulateMessage({
        type: "ticket_update",
        ticket_id: "t2",
      });
    });

    expect(listener).not.toHaveBeenCalled();
  });
});
