import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@/test/test-utils";
import { useNotificationBridge } from "../useNotificationBridge";
import { useNotificationStore } from "@/stores/notificationStore";

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

  simulateMessage(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

describe("useNotificationBridge", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
    useNotificationStore.setState({ notifications: [] });
  });

  it("creates notification on job_completed", async () => {
    renderHook(() => useNotificationBridge("board-1"));

    await waitFor(() => MockWebSocket.instances.length > 0);
    await waitFor(() => MockWebSocket.instances[0].onopen !== null);

    // Wait for WebSocket connection
    await waitFor(() => {
      return MockWebSocket.instances[0].send.mock.calls.length > 0;
    });

    act(() => {
      MockWebSocket.instances[0].simulateMessage({
        type: "job_completed",
        ticket_id: "ticket-1",
        data: { status: "SUCCEEDED" },
      });
    });

    const notifs = useNotificationStore.getState().notifications;
    expect(notifs).toHaveLength(1);
    expect(notifs[0].type).toBe("success");
    expect(notifs[0].title).toBe("Job completed");
  });

  it("creates notification for NEEDS_HUMAN ticket", async () => {
    renderHook(() => useNotificationBridge("board-1"));

    await waitFor(() => MockWebSocket.instances.length > 0);

    await waitFor(() => {
      return MockWebSocket.instances[0].send.mock.calls.length > 0;
    });

    act(() => {
      MockWebSocket.instances[0].simulateMessage({
        type: "ticket_update",
        ticket_id: "ticket-1",
        data: { state: "NEEDS_HUMAN", title: "Fix bug" },
      });
    });

    const notifs = useNotificationStore.getState().notifications;
    expect(notifs).toHaveLength(1);
    expect(notifs[0].type).toBe("warning");
    expect(notifs[0].title).toBe("Ticket needs review");
  });

  it("does not bridge when boardId is null", () => {
    renderHook(() => useNotificationBridge(null));
    expect(MockWebSocket.instances).toHaveLength(0);
  });
});
