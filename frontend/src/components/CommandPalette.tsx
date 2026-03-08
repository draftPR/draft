/**
 * CommandPalette -- Cmd+K command palette using cmdk.
 *
 * Provides fuzzy search across tickets and quick actions.
 * Replaces the previous custom Dialog-based implementation with cmdk for
 * better built-in fuzzy search, keyboard navigation, and accessibility.
 */

import { useEffect, useState, useMemo, useCallback } from "react";
import { Command } from "cmdk";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/hooks/queryKeys";
import { useBoardStore } from "@/stores/boardStore";
import { useTicketSelectionStore } from "@/stores/ticketStore";
import type { BoardResponse, Ticket } from "@/types/api";
import { STATE_DISPLAY_NAMES } from "@/types/api";
import { Search } from "lucide-react";

export interface CommandAction {
  id: string;
  label: string;
  description?: string;
  icon?: React.ComponentType<{ className?: string }>;
  shortcut?: string;
  category?: string;
  onSelect: () => void;
  keywords?: string[];
}

interface CommandPaletteProps {
  /** List of available commands/actions */
  commands: CommandAction[];
}

// Color dot for ticket state
const STATE_DOT_COLORS: Record<string, string> = {
  proposed: "bg-slate-400",
  planned: "bg-blue-400",
  executing: "bg-amber-400",
  verifying: "bg-purple-400",
  needs_human: "bg-orange-400",
  blocked: "bg-red-400",
  done: "bg-emerald-400",
  abandoned: "bg-gray-400",
};

export function CommandPalette({ commands }: CommandPaletteProps) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const boardId = useBoardStore((s) => s.currentBoardId);
  const selectTicket = useTicketSelectionStore((s) => s.selectTicket);

  // Toggle on Cmd+K / Ctrl+K, close on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Get tickets from React Query cache
  const allTickets = useMemo(() => {
    if (!boardId) return [];
    const boardData = queryClient.getQueryData<BoardResponse>(
      queryKeys.boards.view(boardId)
    );
    if (!boardData?.columns) return [];
    return boardData.columns.flatMap((col) => col.tickets);
  }, [boardId, queryClient, open]); // eslint-disable-line react-hooks/exhaustive-deps

  // Group commands by category
  const groupedCommands = useMemo(() => {
    const groups: Record<string, CommandAction[]> = {};
    for (const cmd of commands) {
      const cat = cmd.category || "Other";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(cmd);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [commands]);

  const handleTicketSelect = useCallback(
    (ticketId: string) => {
      setOpen(false);
      selectTicket(ticketId);
    },
    [selectTicket]
  );

  const handleCommandSelect = useCallback(
    (cmd: CommandAction) => {
      setOpen(false);
      cmd.onSelect();
    },
    []
  );

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={() => setOpen(false)}
      />

      {/* Command dialog */}
      <div className="absolute top-[20%] left-1/2 -translate-x-1/2 w-full max-w-lg">
        <Command
          className="rounded-xl border border-border bg-popover shadow-2xl overflow-hidden"
          loop
        >
          <div className="flex items-center gap-2 border-b border-border px-3">
            <Search className="h-4 w-4 text-muted-foreground shrink-0" />
            <Command.Input
              placeholder="Search tickets, actions..."
              className="flex h-11 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              autoFocus
            />
          </div>

          <Command.List className="max-h-80 overflow-y-auto p-1.5">
            <Command.Empty className="py-6 text-center text-sm text-muted-foreground">
              No results found.
            </Command.Empty>

            {/* Quick Actions by category */}
            {groupedCommands.map(([category, cmds]) => (
              <Command.Group
                key={category}
                heading={category}
                className="px-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5"
              >
                {cmds.map((cmd) => {
                  const Icon = cmd.icon;
                  return (
                    <Command.Item
                      key={cmd.id}
                      value={`${cmd.label} ${cmd.description || ""} ${(cmd.keywords || []).join(" ")}`}
                      onSelect={() => handleCommandSelect(cmd)}
                      className="flex items-center justify-between gap-2 px-2 py-1.5 text-sm rounded-md cursor-pointer aria-selected:bg-accent"
                    >
                      <div className="flex items-center gap-2 flex-1 min-w-0">
                        {Icon && (
                          <Icon className="h-4 w-4 text-muted-foreground shrink-0" />
                        )}
                        <div className="flex flex-col min-w-0">
                          <span className="truncate">{cmd.label}</span>
                          {cmd.description && (
                            <span className="text-[11px] text-muted-foreground truncate">
                              {cmd.description}
                            </span>
                          )}
                        </div>
                      </div>
                      {cmd.shortcut && (
                        <kbd className="px-1.5 py-0.5 text-[10px] font-mono bg-muted border border-border rounded shrink-0">
                          {cmd.shortcut}
                        </kbd>
                      )}
                    </Command.Item>
                  );
                })}
              </Command.Group>
            ))}

            {/* Tickets */}
            {allTickets.length > 0 && (
              <Command.Group
                heading="Tickets"
                className="px-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5"
              >
                {allTickets.map((ticket: Ticket) => (
                  <Command.Item
                    key={ticket.id}
                    value={`${ticket.title} ${ticket.id}`}
                    onSelect={() => handleTicketSelect(ticket.id)}
                    className="flex items-center gap-2 px-2 py-1.5 text-sm rounded-md cursor-pointer aria-selected:bg-accent"
                  >
                    <span
                      className={`inline-block w-2 h-2 rounded-full shrink-0 ${
                        STATE_DOT_COLORS[ticket.state] || "bg-gray-400"
                      }`}
                    />
                    <span className="truncate flex-1">{ticket.title}</span>
                    <span className="text-[10px] text-muted-foreground shrink-0">
                      {STATE_DISPLAY_NAMES[ticket.state]}
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>
            )}
          </Command.List>

          {/* Footer */}
          <div className="border-t border-border px-3 py-2 flex items-center justify-between text-[11px] text-muted-foreground">
            <div className="flex items-center gap-3">
              <span>
                <kbd className="bg-muted px-1 py-0.5 rounded text-[10px]">
                  ↑↓
                </kbd>{" "}
                navigate
              </span>
              <span>
                <kbd className="bg-muted px-1 py-0.5 rounded text-[10px]">
                  ↵
                </kbd>{" "}
                select
              </span>
              <span>
                <kbd className="bg-muted px-1 py-0.5 rounded text-[10px]">
                  esc
                </kbd>{" "}
                close
              </span>
            </div>
            <span>
              <kbd className="bg-muted px-1 py-0.5 rounded text-[10px]">
                ⌘K
              </kbd>{" "}
              to open
            </span>
          </div>
        </Command>
      </div>
    </div>
  );
}

