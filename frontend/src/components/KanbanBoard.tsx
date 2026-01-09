import { useState, useEffect, useCallback } from "react";
import {
  DragDropContext,
  Droppable,
  type DropResult,
} from "@hello-pangea/dnd";
import { TicketCard } from "@/components/TicketCard";
import { TicketDetailDrawer } from "@/components/TicketDetailDrawer";
import { fetchBoard, transitionTicket, runPlannerStart, fetchPlannerStatus, executeTicket } from "@/services/api";
import {
  type Ticket,
  type BoardResponse,
  type PlannerStartResponse,
  type PlannerStatusResponse,
  TicketState,
  ActorType,
  COLUMN_ORDER,
  STATE_DISPLAY_NAMES,
  PlannerActionType,
} from "@/types/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Loader2, AlertCircle, RefreshCw, Zap, Check, X, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";

interface KanbanBoardProps {
  refreshTrigger?: number;
}

export function KanbanBoard({ refreshTrigger }: KanbanBoardProps) {
  const [board, setBoard] = useState<BoardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [autopilotLoading, setAutopilotLoading] = useState(false);
  const [plannerStatus, setPlannerStatus] = useState<PlannerStatusResponse | null>(null);
  const [showStatusPanel, setShowStatusPanel] = useState(false);
  const [healthCheckLoading, setHealthCheckLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastRefreshTime, setLastRefreshTime] = useState<Date>(new Date());

  // Load planner status on mount
  useEffect(() => {
    fetchPlannerStatus()
      .then(setPlannerStatus)
      .catch((err) => {
        console.error("Failed to load planner status:", err);
      });
  }, []);

  const loadBoard = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true);
    }
    setError(null);
    try {
      const data = await fetchBoard();
      setBoard(data);
      setLastRefreshTime(new Date());
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load board";
      setError(message);
      if (!silent) {
        toast.error(message);
      }
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    loadBoard();
  }, [loadBoard, refreshTrigger]);

  // Auto-refresh interval
  useEffect(() => {
    if (!autoRefresh) return;

    const intervalId = setInterval(() => {
      loadBoard(true); // Silent refresh
    }, 3000); // Refresh every 3 seconds

    return () => clearInterval(intervalId);
  }, [autoRefresh, loadBoard]);

  const handleAutopilotStart = useCallback(async () => {
    setAutopilotLoading(true);
    toast.info("Autopilot started", {
      description: "Processing all planned tickets...",
    });
    
    try {
      const result: PlannerStartResponse = await runPlannerStart();
      
      // Show summary based on status
      if (result.status === "completed") {
        if (result.tickets_queued === 0) {
          toast.info("Autopilot: No planned tickets", {
            description: result.message,
          });
        } else {
          // Build a detailed description
          const parts: string[] = [];
          if (result.tickets_completed > 0) {
            parts.push(`${result.tickets_completed} completed`);
          }
          if (result.tickets_failed > 0) {
            parts.push(`${result.tickets_failed} failed/blocked`);
          }
          
          toast.success(`Autopilot complete: ${result.tickets_queued} ticket(s) processed`, {
            description: parts.join(", ") || result.message,
            duration: 5000,
          });
        }
      } else if (result.status === "timeout") {
        toast.warning("Autopilot timed out", {
          description: result.message,
          duration: 5000,
        });
      } else {
        toast.error("Autopilot error", {
          description: result.message,
        });
      }
      
      // Refresh the board and planner status to show changes
      await loadBoard();
      fetchPlannerStatus()
        .then(setPlannerStatus)
        .catch(console.error);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Autopilot failed";
      toast.error("Autopilot failed", {
        description: message,
      });
    } finally {
      setAutopilotLoading(false);
    }
  }, [loadBoard]);

  const handleTicketClick = (ticket: Ticket) => {
    setSelectedTicket(ticket);
    setDrawerOpen(true);
  };

  const handleExecuteTicket = useCallback(async (ticket: Ticket) => {
    // Optimistic update: Move ticket to Executing column immediately
    if (board) {
      const updatedTicket = { ...ticket, state: TicketState.EXECUTING };
      const newColumns = board.columns.map((col) => {
        if (col.state === ticket.state) {
          // Remove from current column
          return {
            ...col,
            tickets: col.tickets.filter((t) => t.id !== ticket.id),
          };
        }
        if (col.state === TicketState.EXECUTING) {
          // Add to executing column at the top
          return {
            ...col,
            tickets: [updatedTicket, ...col.tickets],
          };
        }
        return col;
      });
      setBoard({ ...board, columns: newColumns });
    }
    
    // Queue the job - don't immediately refresh as that overwrites the optimistic update
    // The auto-refresh will pick up the real state when the job starts running
    await executeTicket(ticket.id);
  }, [board]);

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
          <Button onClick={() => loadBoard()} variant="outline" size="sm">
            <RefreshCw className="h-4 w-4 mr-2" />
            Try Again
          </Button>
        </div>
      </div>
    );
  }

  return (
    <>
      {/* Autopilot Controls */}
      <div className="flex items-center justify-between mb-4 px-1">
        <div className="flex items-center gap-3">
          <Button
            onClick={handleAutopilotStart}
            disabled={autopilotLoading || loading}
            size="sm"
            variant="outline"
            className="gap-2"
          >
            {autopilotLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Zap className="h-4 w-4" />
            )}
            {autopilotLoading ? "Running..." : "Start Autopilot"}
          </Button>
          
          {/* Planner Status Indicator */}
          <button
            onClick={() => setShowStatusPanel(!showStatusPanel)}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <Info className="h-3.5 w-3.5" />
            {plannerStatus ? (
              <span className={cn(
                plannerStatus.llm_configured ? "text-emerald-600" : "text-amber-600"
              )}>
                {plannerStatus.llm_configured ? "LLM ready" : "LLM not configured"}
              </span>
            ) : (
              <span>Loading...</span>
            )}
          </button>
        </div>
        
        <div className="flex items-center gap-3">
          {/* Auto-refresh toggle */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <Switch
                id="auto-refresh"
                checked={autoRefresh}
                onCheckedChange={setAutoRefresh}
              />
              {autoRefresh && (
                <span className="absolute -top-1 -right-1 flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
              )}
            </div>
            <Label
              htmlFor="auto-refresh"
              className="text-xs text-muted-foreground cursor-pointer flex items-center gap-1.5"
            >
              Auto-refresh
              {autoRefresh && (
                <span className="text-[10px] text-muted-foreground">
                  (last: {lastRefreshTime.toLocaleTimeString()})
                </span>
              )}
            </Label>
          </div>
          
          <Button
            onClick={() => loadBoard()}
            disabled={loading}
            size="sm"
            variant="ghost"
            className="gap-2"
          >
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Planner Status Panel */}
      {showStatusPanel && plannerStatus && (
        <div className="mb-4 px-1">
          <div className="bg-muted/50 rounded-lg p-3 text-xs space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-medium">Planner Status</span>
              <button 
                onClick={() => setShowStatusPanel(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              <div className="flex items-center gap-1.5">
                <span className="text-muted-foreground">Model:</span>
                <span className="font-mono">{plannerStatus.model}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-muted-foreground">LLM:</span>
                {plannerStatus.llm_configured ? (
                  <span className="flex items-center gap-1 text-emerald-600">
                    <Check className="h-3 w-3" />
                    {plannerStatus.llm_provider || "configured"}
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-amber-600">
                    <X className="h-3 w-3" />
                    not configured
                  </span>
                )}
              </div>
            </div>

            {/* Health Check Section */}
            {plannerStatus.llm_configured && (
              <div className="flex items-center gap-2 pt-1 border-t border-border/50">
                <button
                  onClick={async () => {
                    setHealthCheckLoading(true);
                    try {
                      const status = await fetchPlannerStatus(true);
                      setPlannerStatus(status);
                      if (status.llm_health?.healthy) {
                        toast.success(`LLM healthy (${status.llm_health.latency_ms}ms)`);
                      } else {
                        toast.error(status.llm_health?.error || "LLM health check failed");
                      }
                    } catch {
                      toast.error("Failed to run health check");
                    } finally {
                      setHealthCheckLoading(false);
                    }
                  }}
                  disabled={healthCheckLoading}
                  className="text-[10px] px-2 py-1 rounded bg-muted hover:bg-muted/80 transition-colors disabled:opacity-50"
                >
                  {healthCheckLoading ? (
                    <span className="flex items-center gap-1">
                      <Loader2 className="h-2.5 w-2.5 animate-spin" />
                      Checking...
                    </span>
                  ) : (
                    "Test Connection"
                  )}
                </button>
                {plannerStatus.llm_health && (
                  <span className={cn(
                    "text-[10px] flex items-center gap-1",
                    plannerStatus.llm_health.healthy ? "text-emerald-600" : "text-red-600"
                  )}>
                    {plannerStatus.llm_health.healthy ? (
                      <>
                        <Check className="h-2.5 w-2.5" />
                        Healthy ({plannerStatus.llm_health.latency_ms}ms)
                      </>
                    ) : (
                      <>
                        <X className="h-2.5 w-2.5" />
                        {plannerStatus.llm_health.error?.slice(0, 50) || "Failed"}
                      </>
                    )}
                  </span>
                )}
              </div>
            )}

            <div className="flex flex-wrap gap-2 pt-1">
              <span className="text-muted-foreground">Features:</span>
              <span className={cn(
                "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]",
                plannerStatus.features.auto_execute 
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400" 
                  : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500"
              )}>
                {plannerStatus.features.auto_execute ? <Check className="h-2.5 w-2.5" /> : <X className="h-2.5 w-2.5" />}
                execute
              </span>
              <span className={cn(
                "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]",
                plannerStatus.features.propose_followups 
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400" 
                  : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500"
              )}>
                {plannerStatus.features.propose_followups ? <Check className="h-2.5 w-2.5" /> : <X className="h-2.5 w-2.5" />}
                followups
              </span>
              <span className={cn(
                "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]",
                plannerStatus.features.generate_reflections 
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400" 
                  : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500"
              )}>
                {plannerStatus.features.generate_reflections ? <Check className="h-2.5 w-2.5" /> : <X className="h-2.5 w-2.5" />}
                reflections
              </span>
            </div>

            <div className="text-[10px] text-muted-foreground pt-1 border-t border-border/50">
              Caps: {plannerStatus.max_followups_per_ticket} follow-ups/ticket, {plannerStatus.max_followups_per_tick} follow-ups/tick
            </div>

            {/* Last Tick Stats */}
            {plannerStatus.last_tick && (
              <div className="pt-2 border-t border-border/50">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-medium">Last Tick</span>
                  <span className="text-[10px] text-muted-foreground">
                    {new Date(plannerStatus.last_tick.last_tick_at || "").toLocaleTimeString()}
                  </span>
                </div>
                <div className="flex gap-3">
                  <div className="flex items-center gap-1">
                    <span className="text-muted-foreground">executed:</span>
                    <span className={cn(
                      "font-mono",
                      plannerStatus.last_tick.executed > 0 ? "text-blue-600" : ""
                    )}>
                      {plannerStatus.last_tick.executed}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="text-muted-foreground">follow-ups:</span>
                    <span className={cn(
                      "font-mono",
                      plannerStatus.last_tick.followups_created > 0 ? "text-amber-600" : ""
                    )}>
                      {plannerStatus.last_tick.followups_created}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="text-muted-foreground">reflections:</span>
                    <span className={cn(
                      "font-mono",
                      plannerStatus.last_tick.reflections_added > 0 ? "text-emerald-600" : ""
                    )}>
                      {plannerStatus.last_tick.reflections_added}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <DragDropContext onDragEnd={handleDragEnd}>
        {/* Scrollable container for both headers and columns */}
        <div className="overflow-x-auto pb-4">
          {/* Column Headers Row */}
          <div className="flex gap-3 mb-2 px-1 sticky top-0 bg-background z-10">
            {COLUMN_ORDER.map((state) => {
              return (
                <div key={state} className="flex-shrink-0 w-[180px]">
                  <div className="flex items-center gap-1.5 text-xs">
                    <span className="text-muted-foreground">●</span>
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
          <div className="flex gap-3 px-1">
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
                          "flex-1 min-h-[400px] transition-all duration-200 rounded-lg",
                          snapshot.isDraggingOver && "bg-muted/30 ring-2 ring-primary/20"
                        )}
                      >
                        <div className="space-y-2">
                          {tickets.map((ticket, index) => (
                            <TicketCard
                              key={ticket.id}
                              ticket={ticket}
                              index={index}
                              onClick={handleTicketClick}
                              onExecute={handleExecuteTicket}
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

