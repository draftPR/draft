import { useState } from "react";
import { Draggable } from "@hello-pangea/dnd";
import type { Ticket } from "@/types/api";
import { TicketState } from "@/types/api";
import { cn } from "@/lib/utils";
import { Play, Loader2, X, Lock } from "lucide-react";
import { toast } from "sonner";
import { deleteTicket } from "@/services/api";
import { BlockingIndicator } from "@/components/BlockingIndicator";

interface TicketCardProps {
  ticket: Ticket;
  index: number;
  onClick: (ticket: Ticket) => void;
  onExecute?: (ticket: Ticket) => Promise<void>;
  onDelete?: (ticketId: string) => void;
  onNavigateToBlocker?: (ticketId: string) => void;
}

export function TicketCard({ ticket, index, onClick, onExecute, onDelete, onNavigateToBlocker }: TicketCardProps) {
  const [executing, setExecuting] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const isBlocked = ticket.blocked_by_ticket_id !== null;
  const canExecute = ticket.state === TicketState.PLANNED && !isBlocked;

  const handleExecute = async (e: React.MouseEvent) => {
    e.stopPropagation(); // Don't open the drawer
    if (!onExecute || executing) return;

    // Check if blocked
    if (isBlocked) {
      toast.error("Cannot execute ticket", {
        description: ticket.blocked_by_ticket_title
          ? `Blocked by: "${ticket.blocked_by_ticket_title}" - Complete that ticket first.`
          : "This ticket is blocked by a dependency. Complete the blocker first.",
      });
      return;
    }

    setExecuting(true);
    try {
      await onExecute(ticket);
      toast.success(`Started execution: ${ticket.title}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to start execution";
      toast.error(message);
    } finally {
      setExecuting(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation(); // Don't open the drawer
    if (deleting) return;

    if (!confirm(`Delete ticket "${ticket.title}"?\n\nThis action cannot be undone.`)) {
      return;
    }

    setDeleting(true);
    try {
      await deleteTicket(ticket.id);
      toast.success("Ticket deleted");
      onDelete?.(ticket.id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete ticket";
      toast.error(message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Draggable draggableId={ticket.id} index={index}>
      {(provided, snapshot) => (
        <div
          ref={provided.innerRef}
          {...provided.draggableProps}
          {...provided.dragHandleProps}
          className="animate-in fade-in slide-in-from-left-4 duration-300"
        >
          <div
            className={cn(
              "cursor-pointer transition-all duration-300 ease-in-out",
              "bg-card border border-border rounded",
              "px-2 py-2 text-xs",
              "hover:shadow-md hover:border-foreground/20 hover:scale-[1.02] hover:-translate-y-0.5",
              "transform-gpu",
              isBlocked && "opacity-70 border-amber-500/50",
              snapshot.isDragging && "shadow-xl opacity-90 rotate-2 scale-105 ring-2 ring-primary/20"
            )}
            onClick={() => onClick(ticket)}
          >
            {/* Blocking indicator */}
            {isBlocked && (
              <div className="mb-1.5">
                <BlockingIndicator
                  blockedByTicketId={ticket.blocked_by_ticket_id!}
                  blockedByTicketTitle={ticket.blocked_by_ticket_title}
                  onNavigateToBlocker={onNavigateToBlocker}
                />
              </div>
            )}

            <div className="flex items-start justify-between gap-2">
              <div className="font-normal leading-relaxed text-foreground flex-1 min-w-0">
                {ticket.title}
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                {ticket.state === TicketState.PLANNED && onExecute && (
                  <button
                    onClick={handleExecute}
                    disabled={executing || isBlocked}
                    className={cn(
                      "p-1 rounded transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                      isBlocked
                        ? "bg-gray-100 text-gray-400 cursor-not-allowed dark:bg-gray-800 dark:text-gray-600"
                        : "bg-emerald-100 hover:bg-emerald-200 text-emerald-700 dark:bg-emerald-900/30 dark:hover:bg-emerald-900/50 dark:text-emerald-400",
                      "disabled:opacity-50"
                    )}
                    title={isBlocked ? "Cannot execute: blocked by dependency" : "Execute this ticket"}
                  >
                    {executing ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : isBlocked ? (
                      <Lock className="h-3 w-3" />
                    ) : (
                      <Play className="h-3 w-3" />
                    )}
                  </button>
                )}
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className={cn(
                    "p-1 rounded transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                    "bg-red-100 hover:bg-red-200 text-red-700",
                    "dark:bg-red-900/30 dark:hover:bg-red-900/50 dark:text-red-400",
                    "disabled:opacity-50 disabled:cursor-not-allowed"
                  )}
                  title="Delete this ticket"
                >
                  {deleting ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <X className="h-3 w-3" />
                  )}
                </button>
              </div>
            </div>
            {ticket.description && (
              <div className="text-muted-foreground mt-1.5 line-clamp-2 text-[11px]">
                {ticket.description}
              </div>
            )}
          </div>
        </div>
      )}
    </Draggable>
  );
}

