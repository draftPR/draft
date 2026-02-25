import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { KeyboardShortcutsHelp, KeyboardShortcutBadge } from "../KeyboardShortcutsHelp";
import type { KeyboardShortcut } from "../../hooks/useKeyboardNavigation";

describe("KeyboardShortcutsHelp", () => {
  const sampleShortcuts: KeyboardShortcut[] = [
    { key: "j", handler: vi.fn(), description: "Move down", category: "Navigation" },
    { key: "k", handler: vi.fn(), description: "Move up", category: "Navigation" },
    { key: "enter", handler: vi.fn(), description: "Open ticket", category: "Actions" },
    { key: "ctrl+k", handler: vi.fn(), description: "Command palette", category: "Global" },
  ];

  it("renders the dialog when open=true", () => {
    render(
      <KeyboardShortcutsHelp
        shortcuts={sampleShortcuts}
        open={true}
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Keyboard Shortcuts")).toBeInTheDocument();
  });

  it("does not render the dialog content when open=false", () => {
    render(
      <KeyboardShortcutsHelp
        shortcuts={sampleShortcuts}
        open={false}
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.queryByText("Keyboard Shortcuts")).not.toBeInTheDocument();
  });

  it("displays shortcut descriptions grouped by category", () => {
    render(
      <KeyboardShortcutsHelp
        shortcuts={sampleShortcuts}
        open={true}
        onOpenChange={vi.fn()}
      />,
    );

    // Categories
    expect(screen.getByText("Navigation")).toBeInTheDocument();
    expect(screen.getByText("Actions")).toBeInTheDocument();
    expect(screen.getByText("Global")).toBeInTheDocument();

    // Descriptions
    expect(screen.getByText("Move down")).toBeInTheDocument();
    expect(screen.getByText("Move up")).toBeInTheDocument();
    expect(screen.getByText("Open ticket")).toBeInTheDocument();
    expect(screen.getByText("Command palette")).toBeInTheDocument();
  });

  it("formats key combinations correctly", () => {
    render(
      <KeyboardShortcutsHelp
        shortcuts={sampleShortcuts}
        open={true}
        onOpenChange={vi.fn()}
      />,
    );

    // Single keys are uppercased
    expect(screen.getByText("J")).toBeInTheDocument();
    expect(screen.getByText("K")).toBeInTheDocument();
    expect(screen.getByText("ENTER")).toBeInTheDocument();
    // Modifier combos
    expect(screen.getByText("Ctrl+K")).toBeInTheDocument();
  });

  it("shows Global category first", () => {
    render(
      <KeyboardShortcutsHelp
        shortcuts={sampleShortcuts}
        open={true}
        onOpenChange={vi.fn()}
      />,
    );

    // Dialog renders into a portal, so query the full document
    const headings = document.querySelectorAll("h3");
    expect(headings.length).toBeGreaterThan(0);
    expect(headings[0].textContent).toBe("Global");
  });

  it("renders empty when no shortcuts are provided", () => {
    render(
      <KeyboardShortcutsHelp
        shortcuts={[]}
        open={true}
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Keyboard Shortcuts")).toBeInTheDocument();
    // No category headings
    expect(screen.queryByRole("heading", { level: 3 })).not.toBeInTheDocument();
  });

  it("shows the help tip text", () => {
    render(
      <KeyboardShortcutsHelp
        shortcuts={sampleShortcuts}
        open={true}
        onOpenChange={vi.fn()}
      />,
    );

    expect(
      screen.getByText(/Keyboard shortcuts are disabled when typing in text fields/),
    ).toBeInTheDocument();
  });
});

describe("KeyboardShortcutBadge", () => {
  it("renders the shortcut key formatted", () => {
    render(<KeyboardShortcutBadge shortcut="ctrl+s" />);

    expect(screen.getByText("Ctrl+S")).toBeInTheDocument();
  });

  it("renders meta key as command symbol", () => {
    render(<KeyboardShortcutBadge shortcut="cmd+k" />);

    // cmd maps to the command symbol
    expect(screen.getByText(/\u2318\+K/)).toBeInTheDocument();
  });
});
