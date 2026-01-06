import { Draggable } from "@hello-pangea/dnd";
import type { Ticket } from "@/types/api";
import { cn } from "@/lib/utils";

interface TicketCardProps {
  ticket: Ticket;
  index: number;
  onClick: (ticket: Ticket) => void;
}

export function TicketCard({ ticket, index, onClick }: TicketCardProps) {
  return (
    <Draggable draggableId={ticket.id} index={index}>
      {(provided, snapshot) => (
        <div
          ref={provided.innerRef}
          {...provided.draggableProps}
          {...provided.dragHandleProps}
        >
          <div
            className={cn(
              "cursor-pointer transition-all duration-200",
              "bg-card border border-border rounded",
              "px-2 py-2 text-xs",
              "hover:shadow-md hover:border-foreground/20",
              snapshot.isDragging && "shadow-lg opacity-80 rotate-1"
            )}
            onClick={() => onClick(ticket)}
          >
            <div className="font-normal leading-relaxed text-foreground">
              {ticket.title}
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

