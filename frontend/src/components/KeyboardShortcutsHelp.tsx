import React, { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { useKeyboardNavigation, type KeyboardShortcut } from '../hooks/useKeyboardNavigation';

interface KeyboardShortcutsHelpProps {
  /** List of shortcuts to display */
  shortcuts: KeyboardShortcut[];
}

/**
 * Keyboard shortcuts help dialog.
 *
 * Shows all available keyboard shortcuts grouped by category.
 * Opens with `?` key.
 *
 * @example
 * ```tsx
 * const shortcuts = [
 *   { key: 'j', handler: moveDown, description: 'Move down', category: 'Navigation' },
 *   { key: 'k', handler: moveUp, description: 'Move up', category: 'Navigation' },
 *   { key: 'enter', handler: open, description: 'Open ticket', category: 'Actions' },
 * ];
 *
 * <KeyboardShortcutsHelp shortcuts={shortcuts} />
 * ```
 */
export function KeyboardShortcutsHelp({ shortcuts }: KeyboardShortcutsHelpProps) {
  const [open, setOpen] = useState(false);

  // Register `?` to open help
  useKeyboardNavigation({
    shortcuts: [
      {
        key: '?',
        handler: () => setOpen(true),
        description: 'Show keyboard shortcuts',
        category: 'Help',
      },
    ],
    enabled: !open, // Disable when dialog is open
  });

  // Group shortcuts by category
  const groupedShortcuts = shortcuts.reduce((acc, shortcut) => {
    const category = shortcut.category || 'Other';
    if (!acc[category]) {
      acc[category] = [];
    }
    acc[category].push(shortcut);
    return acc;
  }, {} as Record<string, KeyboardShortcut[]>);

  // Format key for display (e.g., "ctrl+k" → "Ctrl+K")
  const formatKey = (key: string): string => {
    return key
      .split(' ')
      .map((part) =>
        part
          .split('+')
          .map((k) => {
            if (k === 'ctrl') return 'Ctrl';
            if (k === 'cmd' || k === 'meta') return '⌘';
            if (k === 'alt') return 'Alt';
            if (k === 'shift') return 'Shift';
            return k.toUpperCase();
          })
          .join('+')
      )
      .join(' ');
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Keyboard Shortcuts</DialogTitle>
          <DialogDescription>
            Navigate faster with keyboard shortcuts. Press <kbd>?</kbd> anytime to see this help.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 mt-4">
          {Object.entries(groupedShortcuts)
            .sort(([a], [b]) => {
              // Sort categories: Global first, then alphabetical
              if (a === 'Global') return -1;
              if (b === 'Global') return 1;
              return a.localeCompare(b);
            })
            .map(([category, categoryShortcuts]) => (
              <div key={category}>
                <h3 className="text-sm font-semibold text-foreground mb-2">{category}</h3>
                <div className="space-y-1">
                  {categoryShortcuts.map((shortcut, index) => (
                    <div
                      key={`${shortcut.key}-${index}`}
                      className="flex items-center justify-between py-2 px-3 rounded hover:bg-accent"
                    >
                      <span className="text-sm text-muted-foreground">
                        {shortcut.description || shortcut.key}
                      </span>
                      <kbd className="px-2 py-1 text-xs font-mono bg-secondary border border-border rounded">
                        {formatKey(shortcut.key)}
                      </kbd>
                    </div>
                  ))}
                </div>
              </div>
            ))}
        </div>

        <div className="mt-6 pt-4 border-t text-xs text-muted-foreground">
          <p>
            Tip: Keyboard shortcuts are disabled when typing in text fields. Press <kbd>Esc</kbd>{' '}
            to close dialogs and return focus to the main view.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Render a keyboard shortcut indicator inline.
 *
 * @example
 * ```tsx
 * <Button>
 *   Save <KeyboardShortcutBadge shortcut="ctrl+s" />
 * </Button>
 * ```
 */
export function KeyboardShortcutBadge({ shortcut }: { shortcut: string }) {
  const formatKey = (key: string): string => {
    return key
      .split('+')
      .map((k) => {
        if (k === 'ctrl') return 'Ctrl';
        if (k === 'cmd' || k === 'meta') return '⌘';
        if (k === 'alt') return 'Alt';
        if (k === 'shift') return 'Shift';
        return k.toUpperCase();
      })
      .join('+');
  };

  return (
    <kbd className="ml-2 px-1.5 py-0.5 text-[10px] font-mono bg-secondary border border-border rounded">
      {formatKey(shortcut)}
    </kbd>
  );
}
