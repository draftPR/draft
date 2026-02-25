import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import {
  useKeyboardShortcuts,
  useAppShortcuts,
  formatShortcut,
  type KeyboardShortcut,
} from "../useKeyboardShortcuts";

function fireKeyDown(key: string, opts: Partial<KeyboardEventInit> = {}) {
  window.dispatchEvent(
    new KeyboardEvent("keydown", { key, bubbles: true, ...opts }),
  );
}

describe("useKeyboardShortcuts", () => {
  it("calls action on matching key press", () => {
    const action = vi.fn();
    const shortcuts: KeyboardShortcut[] = [
      { key: "n", description: "New", action },
    ];

    renderHook(() => useKeyboardShortcuts(shortcuts));
    fireKeyDown("n");
    expect(action).toHaveBeenCalledOnce();
  });

  it("ignores when disabled", () => {
    const action = vi.fn();
    const shortcuts: KeyboardShortcut[] = [
      { key: "n", description: "New", action },
    ];

    renderHook(() => useKeyboardShortcuts(shortcuts, { enabled: false }));
    fireKeyDown("n");
    expect(action).not.toHaveBeenCalled();
  });

  it("ignores shortcuts from disabled shortcuts", () => {
    const action = vi.fn();
    const shortcuts: KeyboardShortcut[] = [
      { key: "n", description: "New", action, disabled: true },
    ];

    renderHook(() => useKeyboardShortcuts(shortcuts));
    fireKeyDown("n");
    expect(action).not.toHaveBeenCalled();
  });

  it("handles modifier keys (ctrl)", () => {
    const action = vi.fn();
    const shortcuts: KeyboardShortcut[] = [
      { key: "k", ctrl: true, description: "Search", action },
    ];

    renderHook(() => useKeyboardShortcuts(shortcuts));

    // Without ctrl - should not fire
    fireKeyDown("k");
    expect(action).not.toHaveBeenCalled();

    // With ctrl - should fire
    fireKeyDown("k", { ctrlKey: true });
    expect(action).toHaveBeenCalledOnce();
  });

  it("ignores keypress in input elements", () => {
    const action = vi.fn();
    const shortcuts: KeyboardShortcut[] = [
      { key: "n", description: "New", action },
    ];

    renderHook(() => useKeyboardShortcuts(shortcuts));

    const input = document.createElement("input");
    document.body.appendChild(input);
    input.dispatchEvent(
      new KeyboardEvent("keydown", { key: "n", bubbles: true }),
    );
    document.body.removeChild(input);

    expect(action).not.toHaveBeenCalled();
  });
});

describe("useAppShortcuts", () => {
  it("registers provided callbacks as shortcuts", () => {
    const onNewTicket = vi.fn();
    const { result } = renderHook(() =>
      useAppShortcuts({ onNewTicket }),
    );
    expect(result.current.shortcuts.length).toBeGreaterThan(0);
  });

  it("fires onNewTicket on n key", () => {
    const onNewTicket = vi.fn();
    renderHook(() => useAppShortcuts({ onNewTicket }));
    fireKeyDown("n");
    expect(onNewTicket).toHaveBeenCalledOnce();
  });
});

describe("formatShortcut", () => {
  it("formats simple key", () => {
    const result = formatShortcut({
      key: "n",
      description: "New",
      action: () => {},
    });
    expect(result).toContain("N");
  });

  it("formats shortcut with ctrl modifier", () => {
    const result = formatShortcut({
      key: "k",
      ctrl: true,
      description: "Search",
      action: () => {},
    });
    // Should contain either Ctrl or ⌃ depending on platform
    expect(result.length).toBeGreaterThan(1);
  });
});
