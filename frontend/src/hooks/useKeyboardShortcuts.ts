import { useEffect, useCallback, useMemo } from "react";

export interface KeyboardShortcut {
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
  meta?: boolean; // Cmd on Mac
  description: string;
  action: () => void;
  disabled?: boolean;
}

interface UseKeyboardShortcutsOptions {
  enabled?: boolean;
  scope?: string; // For scoped shortcuts (e.g., "board", "ticket-detail")
}

function getShortcutKey(shortcut: Omit<KeyboardShortcut, "description" | "action">): string {
  const parts: string[] = [];
  if (shortcut.ctrl) parts.push("ctrl");
  if (shortcut.alt) parts.push("alt");
  if (shortcut.shift) parts.push("shift");
  if (shortcut.meta) parts.push("meta");
  parts.push(shortcut.key.toLowerCase());
  return parts.join("+");
}

function matchesShortcut(
  event: KeyboardEvent,
  shortcut: KeyboardShortcut
): boolean {
  // Check modifiers
  if (shortcut.ctrl && !event.ctrlKey) return false;
  if (shortcut.alt && !event.altKey) return false;
  if (shortcut.shift && !event.shiftKey) return false;
  if (shortcut.meta && !event.metaKey) return false;
  
  // Check that no extra modifiers are pressed
  if (!shortcut.ctrl && event.ctrlKey) return false;
  if (!shortcut.alt && event.altKey) return false;
  if (!shortcut.shift && event.shiftKey) return false;
  if (!shortcut.meta && event.metaKey) return false;
  
  // Check key
  return event.key.toLowerCase() === shortcut.key.toLowerCase();
}

export function useKeyboardShortcuts(
  shortcuts: KeyboardShortcut[],
  options: UseKeyboardShortcutsOptions = {}
) {
  const { enabled = true } = options;
  
  // Build shortcut lookup
  const shortcutMap = useMemo(() => {
    const map = new Map<string, KeyboardShortcut>();
    shortcuts.forEach(s => {
      if (!s.disabled) {
        map.set(getShortcutKey(s), s);
      }
    });
    return map;
  }, [shortcuts]);
  
  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    // Ignore if in input/textarea
    const target = event.target as HTMLElement;
    if (
      target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.isContentEditable
    ) {
      return;
    }
    
    // Try to find matching shortcut
    for (const shortcut of shortcutMap.values()) {
      if (matchesShortcut(event, shortcut)) {
        event.preventDefault();
        event.stopPropagation();
        shortcut.action();
        return;
      }
    }
  }, [shortcutMap]);
  
  useEffect(() => {
    if (!enabled) return;
    
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [enabled, handleKeyDown]);
  
  return { shortcuts: Array.from(shortcutMap.values()) };
}

// Pre-defined application shortcuts
export function useAppShortcuts(callbacks: {
  onNewTicket?: () => void;
  onExecute?: () => void;
  onRefresh?: () => void;
  onSearch?: () => void;
  onGoToBoard?: () => void;
  onHelp?: () => void;
  onToggleSidebar?: () => void;
  onNavigateUp?: () => void;
  onNavigateDown?: () => void;
  onSelect?: () => void;
}) {
  const shortcuts: KeyboardShortcut[] = [
    // Navigation
    {
      key: "g",
      description: "Go to board",
      action: callbacks.onGoToBoard || (() => {}),
      disabled: !callbacks.onGoToBoard,
    },
    {
      key: "j",
      description: "Navigate down",
      action: callbacks.onNavigateDown || (() => {}),
      disabled: !callbacks.onNavigateDown,
    },
    {
      key: "k",
      description: "Navigate up",
      action: callbacks.onNavigateUp || (() => {}),
      disabled: !callbacks.onNavigateUp,
    },
    {
      key: "Enter",
      description: "Select/Open",
      action: callbacks.onSelect || (() => {}),
      disabled: !callbacks.onSelect,
    },
    
    // Actions
    {
      key: "n",
      description: "New ticket",
      action: callbacks.onNewTicket || (() => {}),
      disabled: !callbacks.onNewTicket,
    },
    {
      key: "e",
      description: "Execute ticket",
      action: callbacks.onExecute || (() => {}),
      disabled: !callbacks.onExecute,
    },
    {
      key: "r",
      description: "Refresh",
      action: callbacks.onRefresh || (() => {}),
      disabled: !callbacks.onRefresh,
    },
    
    // Search
    {
      key: "/",
      description: "Search",
      action: callbacks.onSearch || (() => {}),
      disabled: !callbacks.onSearch,
    },
    {
      key: "k",
      ctrl: true,
      description: "Command palette",
      action: callbacks.onSearch || (() => {}),
      disabled: !callbacks.onSearch,
    },
    
    // UI
    {
      key: "b",
      description: "Toggle sidebar",
      action: callbacks.onToggleSidebar || (() => {}),
      disabled: !callbacks.onToggleSidebar,
    },
    {
      key: "?",
      description: "Show shortcuts help",
      action: callbacks.onHelp || (() => {}),
      disabled: !callbacks.onHelp,
    },
  ].filter(s => !s.disabled);
  
  return useKeyboardShortcuts(shortcuts);
}

// Helper to format shortcut for display
export function formatShortcut(shortcut: KeyboardShortcut): string {
  const parts: string[] = [];
  
  // Use Mac-style on Mac
  const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
  
  if (shortcut.ctrl) parts.push(isMac ? "⌃" : "Ctrl");
  if (shortcut.alt) parts.push(isMac ? "⌥" : "Alt");
  if (shortcut.shift) parts.push(isMac ? "⇧" : "Shift");
  if (shortcut.meta) parts.push(isMac ? "⌘" : "Win");
  
  // Format special keys
  let key = shortcut.key;
  if (key === " ") key = "Space";
  if (key === "Enter") key = isMac ? "↵" : "Enter";
  if (key === "Escape") key = "Esc";
  if (key === "ArrowUp") key = "↑";
  if (key === "ArrowDown") key = "↓";
  if (key === "ArrowLeft") key = "←";
  if (key === "ArrowRight") key = "→";
  
  parts.push(key.toUpperCase());
  
  return parts.join(isMac ? "" : "+");
}
