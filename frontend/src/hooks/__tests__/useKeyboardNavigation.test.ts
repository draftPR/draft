import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useKeyboardNavigation } from "../useKeyboardNavigation";

function fireKeyDown(key: string, opts: Partial<KeyboardEventInit> = {}) {
  document.dispatchEvent(
    new KeyboardEvent("keydown", {
      key,
      code: `Key${key.toUpperCase()}`,
      bubbles: true,
      ...opts,
    }),
  );
}

describe("useKeyboardNavigation", () => {
  it("calls handler on matching single key", () => {
    const handler = vi.fn();
    renderHook(() =>
      useKeyboardNavigation({
        shortcuts: [{ key: "j", handler, description: "Down" }],
      }),
    );
    fireKeyDown("j");
    expect(handler).toHaveBeenCalledOnce();
  });

  it("calls handler with ctrl modifier", () => {
    const handler = vi.fn();
    renderHook(() =>
      useKeyboardNavigation({
        shortcuts: [{ key: "ctrl+k", handler, description: "Search" }],
      }),
    );

    // Without modifier
    fireKeyDown("k");
    expect(handler).not.toHaveBeenCalled();

    // With modifier
    fireKeyDown("k", { ctrlKey: true });
    expect(handler).toHaveBeenCalledOnce();
  });

  it("does not fire when disabled", () => {
    const handler = vi.fn();
    renderHook(() =>
      useKeyboardNavigation({
        shortcuts: [{ key: "j", handler }],
        enabled: false,
      }),
    );
    fireKeyDown("j");
    expect(handler).not.toHaveBeenCalled();
  });

  it("ignores key events from input elements", () => {
    const handler = vi.fn();
    renderHook(() =>
      useKeyboardNavigation({
        shortcuts: [{ key: "j", handler }],
      }),
    );

    const input = document.createElement("input");
    document.body.appendChild(input);
    input.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "j",
        code: "KeyJ",
        bubbles: true,
      }),
    );
    document.body.removeChild(input);

    expect(handler).not.toHaveBeenCalled();
  });

  it("handles key sequences like 'g g'", async () => {
    vi.useFakeTimers();
    const handler = vi.fn();
    renderHook(() =>
      useKeyboardNavigation({
        shortcuts: [{ key: "g g", handler, description: "Go to top" }],
      }),
    );

    fireKeyDown("g");
    expect(handler).not.toHaveBeenCalled();

    fireKeyDown("g");
    expect(handler).toHaveBeenCalledOnce();

    vi.useRealTimers();
  });
});
