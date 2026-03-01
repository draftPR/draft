import { useState, memo } from "react";
import { Draggable } from "@hello-pangea/dnd";
import type { Ticket } from "@/types/api";
import { TicketState } from "@/types/api";
import { cn } from "@/lib/utils";
import { Play, Loader2, X, Lock } from "lucide-react";
import { toast } from "sonner";
import { deleteTicket } from "@/services/api";
import { BlockingIndicator } from "@/components/BlockingIndicator";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface TicketCardProps {
  ticket: Ticket;
  index: number;
  onClick: (ticket: Ticket) => void;
  onExecute?: (ticket: Ticket) => Promise<void>;
  onDelete?: (ticketId: string) => void;
  onNavigateToBlocker?: (ticketId: string) => void;
}

export const TicketCard = memo(function TicketCard({ ticket, index, onClick, onExecute, onDelete, onNavigateToBlocker }: TicketCardProps) {
  const [executing, setExecuting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const isBlocked = ticket.blocked_by_ticket_id !== null;

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

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (deleting) return;
    setShowDeleteConfirm(true);
  };

  const handleDeleteConfirm = async () => {
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
      setShowDeleteConfirm(false);
    }
  };

  return (
    <>
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
                  onClick={handleDeleteClick}
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

      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent onClick={(e) => e.stopPropagation()}>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete ticket</AlertDialogTitle>
            <AlertDialogDescription>
              Delete &quot;{ticket.title}&quot;? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}, (prev, next) =>
  prev.ticket.id === next.ticket.id &&
  prev.ticket.title === next.ticket.title &&
  prev.ticket.description === next.ticket.description &&
  prev.ticket.state === next.ticket.state &&
  prev.ticket.priority === next.ticket.priority &&
  prev.ticket.blocked_by_ticket_id === next.ticket.blocked_by_ticket_id &&
  prev.index === next.index
);

