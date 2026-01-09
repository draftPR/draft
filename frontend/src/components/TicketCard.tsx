import { useState } from "react";
import { Draggable } from "@hello-pangea/dnd";
import type { Ticket } from "@/types/api";
import { TicketState } from "@/types/api";
import { cn } from "@/lib/utils";
import { Play, Loader2 } from "lucide-react";
import { toast } from "sonner";

interface TicketCardProps {
  ticket: Ticket;
  index: number;
  onClick: (ticket: Ticket) => void;
  onExecute?: (ticket: Ticket) => Promise<void>;
}

export function TicketCard({ ticket, index, onClick, onExecute }: TicketCardProps) {
  const [executing, setExecuting] = useState(false);
  
  const canExecute = ticket.state === TicketState.PLANNED;

  const handleExecute = async (e: React.MouseEvent) => {
    e.stopPropagation(); // Don't open the drawer
    if (!onExecute || executing) return;
    
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
              "hover:shadow-md hover:border-foreground/20 hover:scale-[1.02]",
              "transform-gpu",
              snapshot.isDragging && "shadow-xl opacity-90 rotate-2 scale-105 ring-2 ring-primary/20"
            )}
            onClick={() => onClick(ticket)}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="font-normal leading-relaxed text-foreground flex-1 min-w-0">
                {ticket.title}
              </div>
              {canExecute && onExecute && (
                <button
                  onClick={handleExecute}
                  disabled={executing}
                  className={cn(
                    "flex-shrink-0 p-1 rounded transition-colors",
                    "bg-emerald-100 hover:bg-emerald-200 text-emerald-700",
                    "dark:bg-emerald-900/30 dark:hover:bg-emerald-900/50 dark:text-emerald-400",
                    "disabled:opacity-50 disabled:cursor-not-allowed"
                  )}
                  title="Execute this ticket"
                >
                  {executing ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Play className="h-3 w-3" />
                  )}
                </button>
              )}
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

