import { useState, useEffect, useCallback } from "react";
import {
  DragDropContext,
  Droppable,
  type DropResult,
} from "@hello-pangea/dnd";
import { TicketCard } from "@/components/TicketCard";
import { TicketDetailDrawer } from "@/components/TicketDetailDrawer";
import { fetchBoard, transitionTicket } from "@/services/api";
import {
  type Ticket,
  type BoardResponse,
  TicketState,
  ActorType,
  COLUMN_ORDER,
  STATE_DISPLAY_NAMES,
  STATE_COLORS,
} from "@/types/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Loader2, AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface KanbanBoardProps {
  refreshTrigger?: number;
}

export function KanbanBoard({ refreshTrigger }: KanbanBoardProps) {
  const [board, setBoard] = useState<BoardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const loadBoard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBoard();
      setBoard(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load board";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBoard();
  }, [loadBoard, refreshTrigger]);

  const handleTicketClick = (ticket: Ticket) => {
    setSelectedTicket(ticket);
    setDrawerOpen(true);
  };

  const handleDragEnd = async (result: DropResult) => {
    const { destination, source, draggableId } = result;

    // Dropped outside a droppable area
    if (!destination) return;

    // Dropped in the same position
    if (
      destination.droppableId === source.droppableId &&
      destination.index === source.index
    ) {
      return;
    }

    const targetState = destination.droppableId as TicketState;
    const sourceState = source.droppableId as TicketState;

    // If same column, just reorder (we don't persist order to backend in MVP)
    if (targetState === sourceState) {
      // Optimistic reorder within column
      if (!board) return;
      
      const newColumns = board.columns.map((col) => {
        if (col.state !== sourceState) return col;
        
        const tickets = [...col.tickets];
        const [removed] = tickets.splice(source.index, 1);
        tickets.splice(destination.index, 0, removed);
        
        return { ...col, tickets };
      });
      
      setBoard({ ...board, columns: newColumns });
      return;
    }

    // Find the ticket being moved
    const sourceColumn = board?.columns.find((col) => col.state === sourceState);
    const ticket = sourceColumn?.tickets.find((t) => t.id === draggableId);

    if (!ticket || !board) return;

    // Optimistic update
    const updatedTicket = { ...ticket, state: targetState };
    const newColumns = board.columns.map((col) => {
      if (col.state === sourceState) {
        return {
          ...col,
          tickets: col.tickets.filter((t) => t.id !== draggableId),
        };
      }
      if (col.state === targetState) {
        const tickets = [...col.tickets];
        tickets.splice(destination.index, 0, updatedTicket);
        return { ...col, tickets };
      }
      return col;
    });

    setBoard({ ...board, columns: newColumns });

    // Call backend to transition
    try {
      await transitionTicket(draggableId, {
        to_state: targetState,
        actor_type: ActorType.HUMAN,
        reason: `Moved from ${STATE_DISPLAY_NAMES[sourceState]} to ${STATE_DISPLAY_NAMES[targetState]}`,
      });
      toast.success(`Ticket moved to ${STATE_DISPLAY_NAMES[targetState]}`);
    } catch (err) {
      // Revert on error
      const message = err instanceof Error ? err.message : "Failed to move ticket";
      toast.error(message);
      // Reload board to get correct state
      loadBoard();
    }
  };

  // Get tickets for a specific state column
  const getColumnTickets = (state: TicketState): Ticket[] => {
    const column = board?.columns.find((col) => col.state === state);
    return column?.tickets || [];
  };

  if (loading && !board) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-200px)]">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Loading board...</p>
        </div>
      </div>
    );
  }

  if (error && !board) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-200px)]">
        <div className="flex flex-col items-center gap-4 text-center">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <div>
            <p className="font-medium text-destructive">Failed to load board</p>
            <p className="text-sm text-muted-foreground mt-1">{error}</p>
          </div>
          <Button onClick={loadBoard} variant="outline" size="sm">
            <RefreshCw className="h-4 w-4 mr-2" />
            Try Again
          </Button>
        </div>
      </div>
    );
  }

  return (
    <>
      <DragDropContext onDragEnd={handleDragEnd}>
        {/* Column Headers Row */}
        <div className="flex gap-3 mb-2 px-1">
          {COLUMN_ORDER.map((state) => {
            const tickets = getColumnTickets(state);
            const stateIcon = 
              state === "to_do" ? "●" :
              state === "in_progress" ? "●" :
              state === "in_review" ? "●" :
              state === "done" ? "●" :
              state === "cancelled" ? "●" : "●";
            
            const stateColor =
              state === "to_do" ? "text-gray-400" :
              state === "in_progress" ? "text-blue-500" :
              state === "in_review" ? "text-orange-500" :
              state === "done" ? "text-green-500" :
              state === "cancelled" ? "text-red-500" : "text-gray-400";

            return (
              <div key={state} className="flex-shrink-0 w-[180px]">
                <div className="flex items-center gap-1.5 text-xs">
                  <span className={stateColor}>{stateIcon}</span>
                  <span className="font-medium">{STATE_DISPLAY_NAMES[state]}</span>
                  {/* Show "(unmerged)" for Verified state to clarify it's not merged */}
                  {state === TicketState.DONE && (
                    <span className="text-muted-foreground text-[10px]">(unmerged)</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Columns */}
        <div className="flex gap-3 overflow-x-auto pb-4 px-1">
          {COLUMN_ORDER.map((state) => {
            const tickets = getColumnTickets(state);
            return (
              <div
                key={state}
                className="flex-shrink-0 w-[180px] flex flex-col"
              >
                {/* Column Content */}
                <Droppable droppableId={state}>
                  {(provided, snapshot) => (
                    <div
                      ref={provided.innerRef}
                      {...provided.droppableProps}
                      className={cn(
                        "flex-1 min-h-[400px] transition-colors",
                        snapshot.isDraggingOver && "bg-muted/30"
                      )}
                    >
                      <div className="space-y-2">
                        {tickets.map((ticket, index) => (
                          <TicketCard
                            key={ticket.id}
                            ticket={ticket}
                            index={index}
                            onClick={handleTicketClick}
                          />
                        ))}
                        {provided.placeholder}
                      </div>
                      
                      {tickets.length === 0 && !snapshot.isDraggingOver && (
                        <div className="flex items-center justify-center h-[100px] text-xs text-muted-foreground">
                          
                        </div>
                      )}
                    </div>
                  )}
                </Droppable>
              </div>
            );
          })}
        </div>
      </DragDropContext>

      <TicketDetailDrawer
        ticket={selectedTicket}
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
      />
    </>
  );
}

