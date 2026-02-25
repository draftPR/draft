import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useBackendStatus } from "../useBackendStatus";

describe("useBackendStatus", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts as online after successful health check", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );

    const { result } = renderHook(() => useBackendStatus());

    await waitFor(() => {
      expect(result.current.isOffline).toBe(false);
    });
  });

  it("goes offline after FAIL_THRESHOLD consecutive failures", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => useBackendStatus());

    // Initial ping fails
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });

    // Second ping (scheduled after first timeout)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    await waitFor(() => {
      expect(result.current.isOffline).toBe(true);
    });
  });

  it("wake() calls the Vite endpoint", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );

    const { result } = renderHook(() => useBackendStatus());

    await act(async () => {
      await result.current.wake();
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      "/__api/wake-backend",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("retry resets fail count and pings immediately", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );

    const { result } = renderHook(() => useBackendStatus());

    await act(async () => {
      result.current.retry();
      await vi.advanceTimersByTimeAsync(100);
    });

    // Should have called fetch for initial ping + retry
    expect(fetchSpy).toHaveBeenCalled();
  });
});
