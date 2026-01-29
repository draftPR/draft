import { useEffect, useCallback, useRef } from 'react';

export interface KeyboardShortcut {
  /** Key combination (e.g., 'j', 'k', 'ctrl+k', 'cmd+k', 'g g') */
  key: string;
  /** Function to execute when shortcut is triggered */
  handler: () => void;
  /** Optional description for help menu */
  description?: string;
  /** Optional category for organization */
  category?: string;
}

export interface KeyboardNavigationOptions {
  /** List of keyboard shortcuts to register */
  shortcuts: KeyboardShortcut[];
  /** Whether keyboard navigation is enabled (default: true) */
  enabled?: boolean;
  /** Element to attach listeners to (default: document) */
  target?: HTMLElement | Document;
}

/**
 * Hook for implementing vim-style keyboard navigation.
 *
 * Supports single keys (j, k), modifier keys (ctrl+k, cmd+k),
 * and key sequences (g g, shift+g).
 *
 * @param options - Keyboard navigation configuration
 *
 * @example
 * ```tsx
 * function TicketList({ tickets, selectedIndex, setSelectedIndex }) {
 *   useKeyboardNavigation({
 *     shortcuts: [
 *       { key: 'j', handler: () => moveDown(), description: 'Move down' },
 *       { key: 'k', handler: () => moveUp(), description: 'Move up' },
 *       { key: 'g g', handler: () => goToTop(), description: 'Go to top' },
 *       { key: 'enter', handler: () => openSelected(), description: 'Open ticket' },
 *     ],
 *     enabled: !isModalOpen
 *   });
 *
 *   return <div>...</div>;
 * }
 * ```
 */
export function useKeyboardNavigation(options: KeyboardNavigationOptions) {
  const { shortcuts, enabled = true, target = document } = options;
  const sequenceRef = useRef<string[]>([]);
  const sequenceTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Parse key combinations
  const parseKey = useCallback((key: string): { keys: string[]; modifiers: Set<string> } => {
    const parts = key.toLowerCase().split('+');
    const modifiers = new Set<string>();
    const keys: string[] = [];

    for (const part of parts) {
      const trimmed = part.trim();
      if (['ctrl', 'control', 'cmd', 'meta', 'alt', 'shift'].includes(trimmed)) {
        modifiers.add(trimmed === 'control' ? 'ctrl' : trimmed === 'cmd' ? 'meta' : trimmed);
      } else {
        keys.push(trimmed);
      }
    }

    return { keys, modifiers };
  }, []);

  // Check if event matches shortcut
  const matchesShortcut = useCallback(
    (event: KeyboardEvent, shortcut: KeyboardShortcut): boolean => {
      const { keys, modifiers } = parseKey(shortcut.key);

      // Handle key sequences (e.g., "g g")
      if (keys.length > 1) {
        // This is a sequence, not a combination
        return false; // Handled separately in sequence logic
      }

      const key = keys[0];

      // Check modifiers
      const hasCtrl = event.ctrlKey || event.metaKey; // Treat Cmd and Ctrl as equivalent
      const hasAlt = event.altKey;
      const hasShift = event.shiftKey;

      const needsCtrl = modifiers.has('ctrl') || modifiers.has('meta');
      const needsAlt = modifiers.has('alt');
      const needsShift = modifiers.has('shift');

      // Exact modifier match required
      if (hasCtrl !== needsCtrl || hasAlt !== needsAlt || hasShift !== needsShift) {
        return false;
      }

      // Check key match
      const eventKey = event.key.toLowerCase();
      return eventKey === key || event.code.toLowerCase() === key.toLowerCase();
    },
    [parseKey]
  );

  // Handle key sequences (e.g., "g g", "shift+g")
  const checkSequence = useCallback(
    (key: string) => {
      // Check if any shortcut starts with this sequence
      const matchingShortcuts = shortcuts.filter((s) => {
        const parts = s.key.split(' ');
        if (parts.length <= 1) return false; // Not a sequence

        const currentSequence = [...sequenceRef.current, key];
        const sequenceStr = currentSequence.join(' ');

        // Exact match
        if (s.key === sequenceStr) {
          return true;
        }

        // Partial match (sequence in progress)
        return s.key.startsWith(sequenceStr + ' ');
      });

      if (matchingShortcuts.length === 0) {
        // No matching sequences, reset
        sequenceRef.current = [];
        return null;
      }

      // Add to sequence
      sequenceRef.current.push(key);

      // Check for exact match
      const exactMatch = matchingShortcuts.find(
        (s) => s.key === sequenceRef.current.join(' ')
      );

      if (exactMatch) {
        // Sequence complete!
        sequenceRef.current = [];
        if (sequenceTimeoutRef.current) {
          clearTimeout(sequenceTimeoutRef.current);
        }
        return exactMatch;
      }

      // Sequence in progress, set timeout to reset
      if (sequenceTimeoutRef.current) {
        clearTimeout(sequenceTimeoutRef.current);
      }
      sequenceTimeoutRef.current = setTimeout(() => {
        sequenceRef.current = [];
      }, 1000); // 1 second timeout for sequences

      return null; // Still waiting for more keys
    },
    [shortcuts]
  );

  useEffect(() => {
    if (!enabled) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      // Ignore if typing in input/textarea
      const targetElement = event.target as HTMLElement;
      if (
        targetElement.tagName === 'INPUT' ||
        targetElement.tagName === 'TEXTAREA' ||
        targetElement.isContentEditable
      ) {
        return;
      }

      // First check for key sequences
      const key = event.key.toLowerCase();
      const sequenceShortcut = checkSequence(key);

      if (sequenceShortcut) {
        event.preventDefault();
        sequenceShortcut.handler();
        return;
      }

      // If sequence in progress, wait for next key
      if (sequenceRef.current.length > 0) {
        return;
      }

      // Check for single key shortcuts or modifier combinations
      for (const shortcut of shortcuts) {
        if (matchesShortcut(event, shortcut)) {
          event.preventDefault();
          shortcut.handler();
          break;
        }
      }
    };

    target.addEventListener('keydown', handleKeyDown as EventListener);

    return () => {
      target.removeEventListener('keydown', handleKeyDown as EventListener);
      if (sequenceTimeoutRef.current) {
        clearTimeout(sequenceTimeoutRef.current);
      }
    };
  }, [enabled, shortcuts, target, matchesShortcut, checkSequence]);
}

/**
 * Hook for getting all registered keyboard shortcuts.
 * Useful for displaying a help menu.
 */
export function useKeyboardShortcuts() {
  // This would be populated by a global registry if we want to show all shortcuts
  // For now, it's a placeholder for future implementation
  return {
    shortcuts: [] as KeyboardShortcut[],
    categories: [] as string[],
  };
}

/**
 * Example keyboard shortcuts for common actions.
 */
export const commonShortcuts = {
  navigation: {
    moveDown: { key: 'j', description: 'Move down', category: 'Navigation' },
    moveUp: { key: 'k', description: 'Move up', category: 'Navigation' },
    goToTop: { key: 'g g', description: 'Go to top', category: 'Navigation' },
    goToBottom: { key: 'shift+g', description: 'Go to bottom', category: 'Navigation' },
    nextPage: { key: 'ctrl+f', description: 'Next page', category: 'Navigation' },
    prevPage: { key: 'ctrl+b', description: 'Previous page', category: 'Navigation' },
  },
  actions: {
    open: { key: 'enter', description: 'Open/Select', category: 'Actions' },
    close: { key: 'escape', description: 'Close/Cancel', category: 'Actions' },
    edit: { key: 'e', description: 'Edit', category: 'Actions' },
    delete: { key: 'shift+d', description: 'Delete', category: 'Actions' },
  },
  global: {
    commandPalette: { key: 'ctrl+k', description: 'Command palette', category: 'Global' },
    search: { key: '/', description: 'Search', category: 'Global' },
    help: { key: '?', description: 'Show help', category: 'Global' },
  },
};
