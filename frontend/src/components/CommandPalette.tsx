import React, { useState, useMemo, useEffect, useRef } from 'react';
import { Dialog, DialogContent } from './ui/dialog';
import { Input } from './ui/input';
import { useKeyboardNavigation } from '../hooks/useKeyboardNavigation';
import {
  Search,
  Play,
  CheckSquare,
  Target,
  List,
  Settings,
  FileText,
} from 'lucide-react';

export interface Command {
  /** Unique ID for the command */
  id: string;
  /** Display label */
  label: string;
  /** Optional description */
  description?: string;
  /** Icon component */
  icon?: React.ComponentType<{ className?: string }>;
  /** Keyboard shortcut hint */
  shortcut?: string;
  /** Category for grouping */
  category?: string;
  /** Action to execute when command is selected */
  onSelect: () => void;
  /** Optional keywords for search */
  keywords?: string[];
}

interface CommandPaletteProps {
  /** List of available commands */
  commands: Command[];
  /** Whether palette is initially open */
  initiallyOpen?: boolean;
  /** Placeholder text for search input */
  placeholder?: string;
}

/**
 * Command palette component.
 *
 * A searchable command menu accessible via Ctrl+K / Cmd+K.
 * Supports fuzzy search, keyboard navigation (arrow keys, enter, escape),
 * and grouped commands by category.
 *
 * @example
 * ```tsx
 * const commands = [
 *   {
 *     id: 'new-goal',
 *     label: 'Create New Goal',
 *     icon: Target,
 *     shortcut: 'n g',
 *     category: 'Goals',
 *     onSelect: () => navigate('/goals/new')
 *   },
 *   {
 *     id: 'execute-all',
 *     label: 'Execute All Ready Tickets',
 *     icon: Play,
 *     shortcut: 'e a',
 *     category: 'Tickets',
 *     onSelect: () => executeAllTickets()
 *   }
 * ];
 *
 * <CommandPalette commands={commands} />
 * ```
 */
export function CommandPalette({
  commands,
  initiallyOpen = false,
  placeholder = 'Type a command or search...',
}: CommandPaletteProps) {
  const [open, setOpen] = useState(initiallyOpen);
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Register Ctrl+K / Cmd+K to open palette
  useKeyboardNavigation({
    shortcuts: [
      {
        key: 'ctrl+k',
        handler: () => {
          setOpen(!open);
          setQuery('');
          setSelectedIndex(0);
        },
        description: 'Open command palette',
        category: 'Global',
      },
      {
        key: 'cmd+k',
        handler: () => {
          setOpen(!open);
          setQuery('');
          setSelectedIndex(0);
        },
        description: 'Open command palette',
        category: 'Global',
      },
    ],
    enabled: true,
  });

  // Fuzzy search function
  const fuzzyMatch = (text: string, query: string): boolean => {
    const lowerText = text.toLowerCase();
    const lowerQuery = query.toLowerCase();

    // Empty query matches everything
    if (!lowerQuery) return true;

    // Try exact substring match first
    if (lowerText.includes(lowerQuery)) return true;

    // Try fuzzy match (characters in order)
    let queryIndex = 0;
    for (let i = 0; i < lowerText.length && queryIndex < lowerQuery.length; i++) {
      if (lowerText[i] === lowerQuery[queryIndex]) {
        queryIndex++;
      }
    }
    return queryIndex === lowerQuery.length;
  };

  // Filter and sort commands based on query
  const filteredCommands = useMemo(() => {
    if (!query.trim()) {
      return commands;
    }

    return commands.filter((cmd) => {
      // Search in label, description, and keywords
      const searchableText = [
        cmd.label,
        cmd.description || '',
        ...(cmd.keywords || []),
      ].join(' ');

      return fuzzyMatch(searchableText, query);
    });
  }, [commands, query]);

  // Group filtered commands by category
  const groupedCommands = useMemo(() => {
    const groups: Record<string, Command[]> = {};

    filteredCommands.forEach((cmd) => {
      const category = cmd.category || 'Other';
      if (!groups[category]) {
        groups[category] = [];
      }
      groups[category].push(cmd);
    });

    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [filteredCommands]);

  // Calculate total number of commands for index bounds
  const totalCommands = filteredCommands.length;

  // Handle arrow key navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % totalCommands);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + totalCommands) % totalCommands);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filteredCommands[selectedIndex]) {
        filteredCommands[selectedIndex].onSelect();
        setOpen(false);
        setQuery('');
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setOpen(false);
      setQuery('');
    }
  };

  // Focus input when dialog opens
  useEffect(() => {
    if (open && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  // Reset selection when query changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Scroll selected item into view
  useEffect(() => {
    if (listRef.current) {
      const selectedElement = listRef.current.querySelector(`[data-index="${selectedIndex}"]`);
      selectedElement?.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-2xl p-0 gap-0">
        {/* Search input */}
        <div className="border-b p-4">
          <div className="flex items-center gap-2">
            <Search className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            <Input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              className="border-0 focus-visible:ring-0 focus-visible:ring-offset-0"
            />
          </div>
        </div>

        {/* Command list */}
        <div ref={listRef} className="max-h-[400px] overflow-y-auto p-2">
          {totalCommands === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No commands found for &quot;{query}&quot;
            </div>
          ) : (
            <div className="space-y-1">
              {groupedCommands.map(([category, categoryCommands]) => (
                <div key={category}>
                  <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
                    {category}
                  </div>
                  {categoryCommands.map((cmd) => {
                    const globalIndex = filteredCommands.indexOf(cmd);
                    const isSelected = globalIndex === selectedIndex;
                    const Icon = cmd.icon;

                    return (
                      <button
                        key={cmd.id}
                        data-index={globalIndex}
                        onClick={() => {
                          cmd.onSelect();
                          setOpen(false);
                          setQuery('');
                        }}
                        onMouseEnter={() => setSelectedIndex(globalIndex)}
                        className={`w-full flex items-center justify-between px-3 py-2 rounded text-sm transition-colors ${
                          isSelected ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50'
                        }`}
                      >
                        <div className="flex items-center gap-3 flex-1 min-w-0">
                          {Icon && <Icon className="h-4 w-4 flex-shrink-0" />}
                          <div className="flex flex-col items-start flex-1 min-w-0">
                            <span className="font-medium truncate w-full text-left">
                              {cmd.label}
                            </span>
                            {cmd.description && (
                              <span className="text-xs text-muted-foreground truncate w-full text-left">
                                {cmd.description}
                              </span>
                            )}
                          </div>
                        </div>
                        {cmd.shortcut && (
                          <kbd className="px-2 py-1 text-xs font-mono bg-secondary border border-border rounded flex-shrink-0">
                            {cmd.shortcut}
                          </kbd>
                        )}
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer hint */}
        <div className="border-t p-2 flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-4">
            <span>
              <kbd className="px-1 py-0.5 bg-secondary border rounded">↑↓</kbd> Navigate
            </span>
            <span>
              <kbd className="px-1 py-0.5 bg-secondary border rounded">Enter</kbd> Select
            </span>
            <span>
              <kbd className="px-1 py-0.5 bg-secondary border rounded">Esc</kbd> Close
            </span>
          </div>
          <span>
            <kbd className="px-1 py-0.5 bg-secondary border rounded">Ctrl+K</kbd> to open
          </span>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Example commands for common Alma Kanban actions.
 */
export const exampleCommands: Command[] = [
  // Goal actions
  {
    id: 'new-goal',
    label: 'Create New Goal',
    description: 'Define a new development goal',
    icon: Target,
    shortcut: 'n g',
    category: 'Goals',
    onSelect: () => console.log('Create new goal'),
    keywords: ['add', 'goal', 'objective'],
  },
  {
    id: 'generate-tickets',
    label: 'Generate Tickets from Goal',
    description: 'AI-generate tickets for the selected goal',
    icon: FileText,
    shortcut: 'g t',
    category: 'Goals',
    onSelect: () => console.log('Generate tickets'),
    keywords: ['plan', 'tickets', 'ai'],
  },

  // Ticket actions
  {
    id: 'execute-all',
    label: 'Execute All Ready Tickets',
    description: 'Start autonomous execution of all planned tickets',
    icon: Play,
    shortcut: 'e a',
    category: 'Tickets',
    onSelect: () => console.log('Execute all tickets'),
    keywords: ['run', 'start', 'execute'],
  },
  {
    id: 'verify-all',
    label: 'Verify All Completed Tickets',
    description: 'Run verification commands on completed tickets',
    icon: CheckSquare,
    shortcut: 'v a',
    category: 'Tickets',
    onSelect: () => console.log('Verify all tickets'),
    keywords: ['test', 'verify', 'check'],
  },

  // Navigation
  {
    id: 'goto-board',
    label: 'Go to Board',
    description: 'View the kanban board',
    icon: List,
    shortcut: 'g b',
    category: 'Navigation',
    onSelect: () => console.log('Go to board'),
  },

  // Executor
  {
    id: 'select-executor',
    label: 'Select Executor',
    description: 'Choose which AI coding agent to use',
    icon: Settings,
    shortcut: 's e',
    category: 'Settings',
    onSelect: () => console.log('Select executor'),
    keywords: ['agent', 'claude', 'cursor'],
  },
];
