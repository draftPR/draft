import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useJobStream } from "../useJobStream";

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  readyState = 1; // OPEN
  send = vi.fn();
  close = vi.fn();

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
    // Simulate async open
    setTimeout(() => this.onopen?.(), 0);
  }

  simulateMessage(data: object | string) {
    const payload = typeof data === "string" ? data : JSON.stringify(data);
    this.onmessage?.({ data: payload });
  }

  simulateClose(code = 1000) {
    this.onclose?.({ code });
  }
}

describe("useJobStream", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  it("returns disconnected when jobId is null", () => {
    const { result } = renderHook(() => useJobStream(null));
    expect(result.current.status).toBe("disconnected");
    expect(result.current.isStreaming).toBe(false);
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  it("connects to WebSocket when jobId is provided", async () => {
    const { result } = renderHook(() => useJobStream("job-1"));

    await waitFor(() => {
      expect(result.current.status).toBe("connected");
    });

    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toContain("/ws/jobs/job-1");
  });

  it("accumulates output messages", async () => {
    const { result } = renderHook(() => useJobStream("job-1"));

    await waitFor(() => expect(result.current.status).toBe("connected"));

    const ws = MockWebSocket.instances[0];

    act(() => {
      ws.simulateMessage({ type: "output", content: "line 1" });
    });
    act(() => {
      ws.simulateMessage({ type: "output", content: "line 2" });
    });

    expect(result.current.lines).toEqual(["line 1", "line 2"]);
    expect(result.current.output).toBe("line 1\nline 2");
  });

  it("updates jobStatus on status message", async () => {
    const { result } = renderHook(() => useJobStream("job-1"));

    await waitFor(() => expect(result.current.status).toBe("connected"));

    act(() => {
      MockWebSocket.instances[0].simulateMessage({
        type: "status",
        status: "running",
      });
    });

    expect(result.current.jobStatus).toBe("running");
  });

  it("handles error message", async () => {
    const { result } = renderHook(() => useJobStream("job-1"));

    await waitFor(() => expect(result.current.status).toBe("connected"));

    act(() => {
      MockWebSocket.instances[0].simulateMessage({
        type: "error",
        content: "Something failed",
      });
    });

    expect(result.current.error).toBe("Something failed");
  });

  it("cleans up on unmount", async () => {
    const { result, unmount } = renderHook(() => useJobStream("job-1"));

    await waitFor(() => expect(result.current.status).toBe("connected"));

    const ws = MockWebSocket.instances[0];
    unmount();
    expect(ws.close).toHaveBeenCalled();
  });
});
