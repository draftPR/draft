import { useState, useEffect, useCallback, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  DragDropContext,
  Droppable,
  type DropResult,
} from "@hello-pangea/dnd";
import { TicketCard } from "@/components/TicketCard";
import { runPlannerStart, fetchPlannerStatus, fetchGoals } from "@/services/api";
import { useTransitionTicket, useExecuteTicket } from "@/hooks/useMutations";
import { usePlannerStatusQuery } from "@/hooks/useQueries";
import { useTicketSelectionStore } from "@/stores/ticketStore";
import {
  type Ticket,
  type Goal,
  type PlannerStartResponse,
  TicketState,
  ActorType,
  COLUMN_ORDER,
  STATE_DISPLAY_NAMES,
} from "@/types/api";
import { useBoard } from "@/contexts/BoardContext";
import { useBoardViewQuery } from "@/hooks/useQueries";
import { queryKeys } from "@/hooks/queryKeys";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { KanbanBoardSkeleton } from "@/components/skeletons/KanbanBoardSkeleton";
import { EmptyState } from "@/components/EmptyState";
import { Loader2, AlertCircle, RefreshCw, Zap, Check, X, Info, Target, Lock, Inbox, Search, ChevronRight, Settings } from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface KanbanBoardProps {
  refreshTrigger?: number;
}

export function KanbanBoard({ refreshTrigger }: KanbanBoardProps = {}) {
  const { currentBoard } = useBoard();
  const ui = useUIStore();
  const queryClient = useQueryClient();
  const transitionMutation = useTransitionTicket(currentBoard?.id);
  const executeMutation = useExecuteTicket(currentBoard?.id);
  const { selectTicket } = useTicketSelectionStore();
  const [autopilotLoading, setAutopilotLoading] = useState(false);
  const { data: plannerStatus, refetch: refetchPlannerStatus } = usePlannerStatusQuery();
  const [showStatusPanel, setShowStatusPanel] = useState(false);
  const [healthCheckLoading, setHealthCheckLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [boardSearch, setBoardSearch] = useState("");
  const [collapsedColumns, setCollapsedColumns] = useState<Set<TicketState>>(new Set());
  const [selectedGoalId, setSelectedGoalId] = useState<string>("all");
  const [goals, setGoals] = useState<Goal[]>([]);

  // Use React Query for board data with auto-refetch
  const {
    data: board,
    isLoading: loading,
    error: boardError,
    dataUpdatedAt,
    refetch,
  } = useBoardViewQuery(currentBoard?.id, autoRefresh);

  const error = boardError ? (boardError instanceof Error ? boardError.message : "Failed to load board") : null;
  const lastRefreshTime = new Date(dataUpdatedAt || Date.now());

  // Fetch goals for the filter dropdown
  useEffect(() => {
    if (currentBoard?.id) {
      setSelectedGoalId("all");
      fetchGoals(currentBoard.id)
        .then((res) => setGoals(res.goals))
        .catch(() => setGoals([]));
    } else {
      setGoals([]);
    }
  }, [currentBoard?.id]);

  // Refetch when refreshTrigger changes
  useEffect(() => {
    if (refreshTrigger !== undefined) {
      refetch();
    }
  }, [refreshTrigger, refetch]);

  const loadBoard = useCallback(async () => {
    await refetch();
  }, [refetch]);

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
      refetchPlannerStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Autopilot failed";
      toast.error("Autopilot failed", {
        description: message,
      });
    } finally {
      setAutopilotLoading(false);
    }
  }, [loadBoard, refetchPlannerStatus]);

  const handleTicketClick = (ticket: Ticket) => {
    selectTicket(ticket.id);
  };

  const handleNavigateToBlocker = useCallback((ticketId: string) => {
    selectTicket(ticketId);
  }, [selectTicket]);

  const handleExecuteTicket = useCallback(async (ticket: Ticket) => {
    await executeMutation.mutateAsync(ticket.id);
  }, [executeMutation]);

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
      if (!board || !currentBoard) return;

      const boardKey = queryKeys.boards.view(currentBoard.id);
      const newColumns = board.columns.map((col) => {
        if (col.state !== sourceState) return col;
        const tickets = [...col.tickets];
        const [removed] = tickets.splice(source.index, 1);
        tickets.splice(destination.index, 0, removed);
        return { ...col, tickets };
      });

      queryClient.setQueryData(boardKey, { ...board, columns: newColumns });
      return;
    }

    // Find the ticket being moved
    const sourceColumn = board?.columns.find((col) => col.state === sourceState);
    const ticket = sourceColumn?.tickets.find((t) => t.id === draggableId);

    if (!ticket || !board || !currentBoard) return;

    // Use optimistic mutation hook
    try {
      await transitionMutation.mutateAsync({
        ticketId: draggableId,
        data: {
          to_state: targetState,
          actor_type: ActorType.HUMAN,
          reason: `Moved from ${STATE_DISPLAY_NAMES[sourceState]} to ${STATE_DISPLAY_NAMES[targetState]}`,
        },
      });
      toast.success(`Ticket moved to ${STATE_DISPLAY_NAMES[targetState]}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to move ticket";
      toast.error(message);
    }
  };

  // Get tickets for a specific state column, filtered by search and goal
  const getColumnTickets = useCallback((state: TicketState): Ticket[] => {
    const column = board?.columns.find((col) => col.state === state);
    let tickets = column?.tickets || [];
    if (selectedGoalId !== "all") {
      tickets = tickets.filter((t) => t.goal_id === selectedGoalId);
    }
    if (!boardSearch) return tickets;
    const q = boardSearch.toLowerCase();
    return tickets.filter(
      (t) =>
        t.title.toLowerCase().includes(q) ||
        t.description?.toLowerCase().includes(q)
    );
  }, [board, boardSearch, selectedGoalId]);

  const toggleColumn = useCallback((state: TicketState) => {
    setCollapsedColumns((prev) => {
      const next = new Set(prev);
      if (next.has(state)) next.delete(state);
      else next.add(state);
      return next;
    });
  }, []);

  // Total ticket count for search results feedback
  const totalTickets = useMemo(() => {
    if (!board) return 0;
    return COLUMN_ORDER.reduce((sum, state) => sum + getColumnTickets(state).length, 0);
  }, [board, getColumnTickets]);

  // Show message when no board is selected
  if (!currentBoard) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-200px)]">
        <div className="flex flex-col items-center gap-4 text-center max-w-md">
          <Target className="h-12 w-12 text-muted-foreground" />
          <div>
            <p className="font-medium text-foreground">No Project Selected</p>
            <p className="text-sm text-muted-foreground mt-2">
              Select a project from the dropdown above or add a new project to get started.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (loading && !board) {
    return <KanbanBoardSkeleton />;
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
                {plannerStatus.llm_configured
                  ? `Planner ready`
                  : "Planner ready · CLI mode"}
              </span>
            ) : (
              <span>Loading...</span>
            )}
          </button>
        </div>
        
        <div className="flex items-center gap-3">
          {/* Goal filter */}
          {goals.length > 1 && (
            <Select value={selectedGoalId} onValueChange={setSelectedGoalId}>
              <SelectTrigger className="h-8 w-40 text-xs">
                <Target className="h-3 w-3 mr-1 flex-shrink-0" />
                <SelectValue placeholder="All goals" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All goals</SelectItem>
                {goals.map((g) => (
                  <SelectItem key={g.id} value={g.id}>
                    {g.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          {/* Board search */}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="text"
              value={boardSearch}
              onChange={(e) => setBoardSearch(e.target.value)}
              placeholder="Filter tickets..."
              className="h-8 w-40 rounded-md border border-input bg-background pl-8 pr-3 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
            {boardSearch && (
              <button
                onClick={() => setBoardSearch("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
          {boardSearch && (
            <span className="text-[10px] text-muted-foreground">
              {totalTickets} match{totalTickets !== 1 ? "es" : ""}
            </span>
          )}

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
          <Button
            onClick={() => ui.setBoardSettingsOpen(true)}
            size="sm"
            variant="ghost"
            title="Board Settings"
          >
            <Settings className="h-4 w-4" />
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
                    {plannerStatus.llm_provider || "ready"}
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-amber-600">
                    <X className="h-3 w-3" />
                    needs API key
                  </span>
                )}
              </div>
            </div>

            {/* Not configured explanation */}
            {!plannerStatus.llm_configured && (
              <div className="text-[10px] text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded px-2 py-1.5 leading-relaxed border border-amber-200 dark:border-amber-800">
                <strong>Why?</strong> The planner uses LLM for follow-ups &amp; reflections.
                Set <code className="font-mono">ANTHROPIC_API_KEY</code> or <code className="font-mono">OPENAI_API_KEY</code> in your <code className="font-mono">.env</code>,
                or switch the model to <code className="font-mono">cli/claude</code> in the planner settings to use the Claude CLI instead.
                Auto-execute still works without this.
              </div>
            )}

            {/* Health Check Section */}
            {plannerStatus.llm_configured && (
              <div className="flex items-center gap-2 pt-1 border-t border-border/50">
                <button
                  onClick={async () => {
                    setHealthCheckLoading(true);
                    try {
                      const status = await fetchPlannerStatus(true);
                      refetchPlannerStatus();
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
              const tickets = getColumnTickets(state);
              const isCollapsed = collapsedColumns.has(state);
              const blockedCount = state === TicketState.PLANNED
                ? tickets.filter(t => t.blocked_by_ticket_id !== null).length
                : 0;
              const readyCount = state === TicketState.PLANNED
                ? tickets.filter(t => t.blocked_by_ticket_id === null).length
                : 0;

              return (
                <div key={state} className={cn("flex-shrink-0", isCollapsed ? "w-[36px]" : "w-[180px]")}>
                  {isCollapsed ? (
                    <button
                      onClick={() => toggleColumn(state)}
                      className="flex flex-col items-center gap-1 py-1 text-muted-foreground hover:text-foreground transition-colors"
                      title={`Expand ${STATE_DISPLAY_NAMES[state]}`}
                    >
                      <ChevronRight className="h-3 w-3" />
                      <span className="text-[10px] font-medium [writing-mode:vertical-lr] rotate-180">
                        {STATE_DISPLAY_NAMES[state]}
                      </span>
                      {tickets.length > 0 && (
                        <span className="text-[9px] bg-muted rounded-full px-1.5 py-0.5 min-w-[18px] text-center">
                          {tickets.length}
                        </span>
                      )}
                    </button>
                  ) : (
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-1.5 text-xs">
                        <button
                          onClick={() => toggleColumn(state)}
                          className="text-muted-foreground hover:text-foreground transition-colors"
                          title={`Collapse ${STATE_DISPLAY_NAMES[state]}`}
                        >
                          ●
                        </button>
                        <span className="font-medium">{STATE_DISPLAY_NAMES[state]}</span>
                        {tickets.length > 0 && (
                          <span className="text-[10px] bg-muted text-muted-foreground rounded-full px-1.5 py-0.5 min-w-[18px] text-center leading-none">
                            {tickets.length}
                          </span>
                        )}
                      </div>
                      {state === TicketState.PLANNED && blockedCount > 0 && (
                        <div className="flex items-center gap-1 text-[10px] text-amber-600 dark:text-amber-400">
                          <Lock className="h-2.5 w-2.5" />
                          <span>{blockedCount} blocked, {readyCount} ready</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Columns */}
          <div className="flex gap-3 px-1">
            {COLUMN_ORDER.map((state) => {
              const tickets = getColumnTickets(state);
              const isCollapsed = collapsedColumns.has(state);

              if (isCollapsed) {
                return (
                  <Droppable key={state} droppableId={state}>
                    {(provided, snapshot) => (
                      <div
                        ref={provided.innerRef}
                        {...provided.droppableProps}
                        className={cn(
                          "flex-shrink-0 w-[36px] min-h-[400px] rounded-lg transition-all duration-200",
                          snapshot.isDraggingOver && "bg-primary/10 ring-2 ring-primary/30"
                        )}
                      >
                        {snapshot.isDraggingOver && (
                          <div className="flex items-center justify-center h-20 mt-2">
                            <span className="text-[9px] text-primary font-medium [writing-mode:vertical-lr] rotate-180">
                              Drop here
                            </span>
                          </div>
                        )}
                        <div className="hidden">{provided.placeholder}</div>
                      </div>
                    )}
                  </Droppable>
                );
              }

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
                              onDelete={() => loadBoard()}
                              onNavigateToBlocker={handleNavigateToBlocker}
                            />
                          ))}
                          {provided.placeholder}
                        </div>

                        {tickets.length === 0 && !snapshot.isDraggingOver && (
                          <EmptyState icon={Inbox} title="No tickets" compact />
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

    </>
  );
}

