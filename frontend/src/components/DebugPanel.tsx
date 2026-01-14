import { useState, useEffect, useRef, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  fetchSystemStatus,
  fetchOrchestratorLogs,
  fetchRecentEvents,
  fetchJobLogs,
  streamOrchestratorLogs,
  fetchQueueStatus,
  type SystemStatusResponse,
  type OrchestratorLogEntry,
  type RecentEvent,
  type QueueStatusResponse,
} from "@/services/api";
import {
  Bug,
  X,
  RefreshCw,
  Activity,
  Terminal,
  ScrollText,
  ChevronDown,
  ChevronRight,
  Play,
  Clock,
  Zap,
  AlertCircle,
  CheckCircle,
  XCircle,
  Loader2,
  Minimize2,
  Maximize2,
  Copy,
  Check,
  ListOrdered,
  Pause,
} from "lucide-react";

interface DebugPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

type TabType = "status" | "queue" | "orchestrator" | "agent" | "events";

function formatTime(timestamp: string): string {
  try {
    const date = new Date(timestamp);
    return date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return timestamp;
  }
}

function LogLevelBadge({ level }: { level: string }) {
  const colors: Record<string, string> = {
    DEBUG: "bg-gray-500/15 text-gray-500 border-gray-500/30",
    INFO: "bg-blue-500/15 text-blue-500 border-blue-500/30",
    WARNING: "bg-amber-500/15 text-amber-600 border-amber-500/30",
    ERROR: "bg-red-500/15 text-red-500 border-red-500/30",
  };

  return (
    <Badge
      variant="outline"
      className={cn("text-[9px] px-1 py-0 font-mono", colors[level] || colors.INFO)}
    >
      {level}
    </Badge>
  );
}

function StateBadge({ state }: { state: string }) {
  const colors: Record<string, string> = {
    proposed: "bg-slate-500/15 text-slate-600",
    planned: "bg-blue-500/15 text-blue-600",
    executing: "bg-emerald-500/15 text-emerald-600",
    verifying: "bg-purple-500/15 text-purple-600",
    needs_review: "bg-amber-500/15 text-amber-600",
    needs_human: "bg-orange-500/15 text-orange-600",
    blocked: "bg-red-500/15 text-red-600",
    done: "bg-green-500/15 text-green-600",
    abandoned: "bg-gray-500/15 text-gray-500",
  };

  return (
    <Badge variant="outline" className={cn("text-[10px] px-1.5", colors[state] || "")}>
      {state}
    </Badge>
  );
}

export function DebugPanel({ isOpen, onClose }: DebugPanelProps) {
  const [activeTab, setActiveTab] = useState<TabType>("status");
  const [isMinimized, setIsMinimized] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  
  // Data states
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(null);
  const [queueStatus, setQueueStatus] = useState<QueueStatusResponse | null>(null);
  const [orchestratorLogs, setOrchestratorLogs] = useState<OrchestratorLogEntry[]>([]);
  const [recentEvents, setRecentEvents] = useState<RecentEvent[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [agentLogs, setAgentLogs] = useState<string>("");
  
  // UI states
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [copied, setCopied] = useState(false);
  
  // Refs
  const logsEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Load system status
  const loadSystemStatus = useCallback(async () => {
    try {
      const status = await fetchSystemStatus();
      setSystemStatus(status);
    } catch (err) {
      console.error("Failed to load system status:", err);
    }
  }, []);

  // Load queue status
  const loadQueueStatus = useCallback(async () => {
    try {
      const status = await fetchQueueStatus();
      setQueueStatus(status);
    } catch (err) {
      console.error("Failed to load queue status:", err);
    }
  }, []);

  // Load orchestrator logs
  const loadOrchestratorLogs = useCallback(async () => {
    try {
      const response = await fetchOrchestratorLogs(200);
      setOrchestratorLogs(response.logs);
    } catch (err) {
      console.error("Failed to load orchestrator logs:", err);
    }
  }, []);

  // Load recent events
  const loadRecentEvents = useCallback(async () => {
    try {
      const events = await fetchRecentEvents(100);
      setRecentEvents(events);
    } catch (err) {
      console.error("Failed to load recent events:", err);
    }
  }, []);

  // Load agent logs for selected job
  const loadAgentLogs = useCallback(async (jobId: string) => {
    setLoading(true);
    try {
      const logs = await fetchJobLogs(jobId);
      setAgentLogs(logs);
    } catch (err) {
      setAgentLogs(`Error loading logs: ${err}`);
    } finally {
      setLoading(false);
    }
  }, []);

  // Start streaming orchestrator logs
  const startStreaming = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const eventSource = streamOrchestratorLogs(
      (log) => {
        setOrchestratorLogs((prev) => {
          const newLogs = [...prev, log];
          // Keep last 500 entries
          return newLogs.slice(-500);
        });
      },
      (err) => {
        console.error("Orchestrator stream error:", err);
        setIsStreaming(false);
      }
    );

    eventSourceRef.current = eventSource;
    setIsStreaming(true);
  }, []);

  // Stop streaming
  const stopStreaming = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  // Initial load and polling
  useEffect(() => {
    if (!isOpen) return;

    loadSystemStatus();
    loadQueueStatus();
    loadOrchestratorLogs();
    loadRecentEvents();

    // Poll every 2 seconds
    const interval = setInterval(() => {
      loadSystemStatus();
      if (activeTab === "queue") {
        loadQueueStatus();
      }
      if (activeTab === "events") {
        loadRecentEvents();
      }
      if (selectedJobId && activeTab === "agent") {
        loadAgentLogs(selectedJobId);
      }
    }, 2000);

    return () => {
      clearInterval(interval);
      stopStreaming();
    };
  }, [isOpen, activeTab, selectedJobId, loadSystemStatus, loadQueueStatus, loadOrchestratorLogs, loadRecentEvents, loadAgentLogs, stopStreaming]);

  // Auto-scroll logs
  useEffect(() => {
    if (autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [orchestratorLogs, agentLogs, autoScroll]);

  // Copy logs to clipboard
  const copyLogs = useCallback(() => {
    const text = activeTab === "orchestrator"
      ? orchestratorLogs.map(l => `[${l.timestamp}] ${l.level}: ${l.message}`).join("\n")
      : agentLogs;
    
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [activeTab, orchestratorLogs, agentLogs]);

  if (!isOpen) return null;

  const tabs: { id: TabType; label: string; icon: React.ReactNode }[] = [
    { id: "status", label: "Status", icon: <Activity className="h-3.5 w-3.5" /> },
    { id: "queue", label: "Queue", icon: <ListOrdered className="h-3.5 w-3.5" /> },
    { id: "orchestrator", label: "Orchestrator", icon: <Zap className="h-3.5 w-3.5" /> },
    { id: "agent", label: "Agent", icon: <Terminal className="h-3.5 w-3.5" /> },
    { id: "events", label: "Events", icon: <ScrollText className="h-3.5 w-3.5" /> },
  ];

  return (
    <div
      className={cn(
        "fixed bottom-0 left-0 right-0 z-50 bg-background border-t shadow-lg transition-all duration-200",
        isMinimized ? "h-10" : "h-[45vh]"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 h-10 border-b bg-muted/30">
        <div className="flex items-center gap-2">
          <Bug className="h-4 w-4 text-amber-500" />
          <span className="text-sm font-semibold">Debug Panel</span>
          
          {/* Live indicator */}
          {isStreaming && (
            <div className="flex items-center gap-1.5 text-emerald-500">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span className="text-[10px] font-medium uppercase tracking-wide">Live</span>
            </div>
          )}
        </div>

        {/* Tabs - only show when not minimized */}
        {!isMinimized && (
          <div className="flex items-center gap-1">
            {tabs.map((tab) => (
              <Button
                key={tab.id}
                variant={activeTab === tab.id ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setActiveTab(tab.id)}
                className="h-7 px-2.5 text-xs gap-1.5"
              >
                {tab.icon}
                {tab.label}
              </Button>
            ))}
          </div>
        )}

        {/* Controls */}
        <div className="flex items-center gap-1">
          {!isMinimized && activeTab === "orchestrator" && (
            <Button
              variant={isStreaming ? "secondary" : "ghost"}
              size="sm"
              onClick={isStreaming ? stopStreaming : startStreaming}
              className="h-7 px-2 text-xs"
            >
              {isStreaming ? (
                <>
                  <XCircle className="h-3 w-3 mr-1" />
                  Stop
                </>
              ) : (
                <>
                  <Play className="h-3 w-3 mr-1" />
                  Stream
                </>
              )}
            </Button>
          )}
          
          {!isMinimized && (activeTab === "orchestrator" || activeTab === "agent") && (
            <Button
              variant="ghost"
              size="sm"
              onClick={copyLogs}
              className="h-7 px-2 text-xs"
            >
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            </Button>
          )}
          
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsMinimized(!isMinimized)}
            className="h-7 w-7 p-0"
          >
            {isMinimized ? <Maximize2 className="h-3.5 w-3.5" /> : <Minimize2 className="h-3.5 w-3.5" />}
          </Button>
          
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="h-7 w-7 p-0"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Content */}
      {!isMinimized && (
        <div className="h-[calc(45vh-2.5rem)] overflow-hidden">
          {/* Status Tab */}
          {activeTab === "status" && (
            <div className="p-4 h-full overflow-y-auto">
              {systemStatus ? (
                <div className="grid grid-cols-3 gap-4">
                  {/* Running Jobs */}
                  <div className="space-y-2">
                    <h3 className="text-sm font-semibold flex items-center gap-2">
                      <Play className="h-4 w-4 text-emerald-500" />
                      Running Jobs ({systemStatus.running_jobs.length})
                    </h3>
                    {systemStatus.running_jobs.length === 0 ? (
                      <p className="text-xs text-muted-foreground">No jobs running</p>
                    ) : (
                      <div className="space-y-2">
                        {systemStatus.running_jobs.map((job) => (
                          <div
                            key={job.job_id}
                            className="p-2 rounded border bg-emerald-500/5 border-emerald-500/20 cursor-pointer hover:bg-emerald-500/10"
                            onClick={() => {
                              setSelectedJobId(job.job_id);
                              setActiveTab("agent");
                              loadAgentLogs(job.job_id);
                            }}
                          >
                            <p className="text-xs font-medium truncate">{job.ticket_title}</p>
                            <p className="text-[10px] text-muted-foreground">
                              {job.kind} • {job.started_at ? formatTime(job.started_at) : "Starting..."}
                            </p>
                            {job.log_preview && (
                              <pre className="mt-1 text-[10px] text-muted-foreground font-mono truncate">
                                {job.log_preview.split("\n").pop()}
                              </pre>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Ticket States */}
                  <div className="space-y-2">
                    <h3 className="text-sm font-semibold flex items-center gap-2">
                      <Activity className="h-4 w-4 text-blue-500" />
                      Tickets by State
                    </h3>
                    <div className="space-y-1">
                      {Object.entries(systemStatus.tickets_by_state).map(([state, count]) => (
                        <div key={state} className="flex items-center justify-between">
                          <StateBadge state={state} />
                          <span className="text-sm font-mono">{count}</span>
                        </div>
                      ))}
                      {Object.keys(systemStatus.tickets_by_state).length === 0 && (
                        <p className="text-xs text-muted-foreground">No tickets</p>
                      )}
                    </div>
                  </div>

                  {/* Quick Stats */}
                  <div className="space-y-2">
                    <h3 className="text-sm font-semibold flex items-center gap-2">
                      <Zap className="h-4 w-4 text-amber-500" />
                      Quick Stats
                    </h3>
                    <div className="space-y-2 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Queued Jobs</span>
                        <span className="font-mono">{systemStatus.queued_count}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Events (1h)</span>
                        <span className="font-mono">{systemStatus.recent_events_count}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Last Update</span>
                        <span className="font-mono text-xs">{formatTime(systemStatus.timestamp)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              )}
            </div>
          )}

          {/* Queue Tab */}
          {activeTab === "queue" && (
            <div className="p-4 h-full overflow-y-auto">
              {queueStatus ? (
                <div className="grid grid-cols-2 gap-6">
                  {/* Running Jobs */}
                  <div className="space-y-3">
                    <h3 className="text-sm font-semibold flex items-center gap-2">
                      <Play className="h-4 w-4 text-emerald-500" />
                      Running ({queueStatus.total_running})
                    </h3>
                    {queueStatus.running.length === 0 ? (
                      <p className="text-xs text-muted-foreground italic">No jobs running</p>
                    ) : (
                      <div className="space-y-2">
                        {queueStatus.running.map((job) => (
                          <div
                            key={job.id}
                            className="p-3 rounded-lg border bg-emerald-500/5 border-emerald-500/20 cursor-pointer hover:bg-emerald-500/10 transition-colors"
                            onClick={() => {
                              setSelectedJobId(job.id);
                              setActiveTab("agent");
                              loadAgentLogs(job.id);
                            }}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <Badge variant="outline" className="text-[10px] bg-emerald-500/10 text-emerald-600 border-emerald-500/30">
                                {job.kind}
                              </Badge>
                              <span className="text-[10px] text-muted-foreground font-mono">
                                {job.id.slice(0, 8)}
                              </span>
                            </div>
                            <p className="text-sm font-medium truncate">{job.ticket_title}</p>
                            <p className="text-[10px] text-muted-foreground mt-1">
                              Started: {job.started_at ? formatTime(job.started_at) : "Starting..."}
                            </p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Queued Jobs */}
                  <div className="space-y-3">
                    <h3 className="text-sm font-semibold flex items-center gap-2">
                      <Pause className="h-4 w-4 text-amber-500" />
                      Queued ({queueStatus.total_queued})
                    </h3>
                    {queueStatus.queued.length === 0 ? (
                      <p className="text-xs text-muted-foreground italic">No jobs in queue</p>
                    ) : (
                      <div className="space-y-2">
                        {queueStatus.queued.map((job, index) => (
                          <div
                            key={job.id}
                            className="p-3 rounded-lg border bg-amber-500/5 border-amber-500/20"
                          >
                            <div className="flex items-center justify-between mb-1">
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-mono text-amber-600 bg-amber-500/10 px-1.5 py-0.5 rounded">
                                  #{index + 1}
                                </span>
                                <Badge variant="outline" className="text-[10px] bg-amber-500/10 text-amber-600 border-amber-500/30">
                                  {job.kind}
                                </Badge>
                              </div>
                              <span className="text-[10px] text-muted-foreground font-mono">
                                {job.id.slice(0, 8)}
                              </span>
                            </div>
                            <p className="text-sm font-medium truncate">{job.ticket_title}</p>
                            <p className="text-[10px] text-muted-foreground mt-1">
                              Queued: {formatTime(job.created_at)}
                            </p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              )}
            </div>
          )}

          {/* Orchestrator Logs Tab */}
          {activeTab === "orchestrator" && (
            <div className="h-full flex flex-col">
              <div className="flex-1 overflow-y-auto p-2 font-mono text-xs bg-black/5 dark:bg-white/5">
                {orchestratorLogs.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                    <Terminal className="h-8 w-8 mb-2 opacity-50" />
                    <p>No orchestrator logs yet</p>
                    <p className="text-[10px]">Run the planner to generate logs</p>
                  </div>
                ) : (
                  <div className="space-y-0.5">
                    {orchestratorLogs.map((log, i) => (
                      <div key={i} className="flex items-start gap-2 hover:bg-muted/30 px-1 py-0.5 rounded">
                        <span className="text-muted-foreground shrink-0 w-20">
                          {formatTime(log.timestamp)}
                        </span>
                        <LogLevelBadge level={log.level} />
                        <span className="flex-1">{log.message}</span>
                        {Object.keys(log.data).length > 0 && (
                          <span className="text-muted-foreground text-[10px] shrink-0">
                            {JSON.stringify(log.data)}
                          </span>
                        )}
                      </div>
                    ))}
                    <div ref={logsEndRef} />
                  </div>
                )}
              </div>
              
              {/* Auto-scroll toggle */}
              <div className="flex items-center justify-between px-2 py-1 border-t bg-muted/20 text-[10px]">
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={autoScroll}
                    onChange={(e) => setAutoScroll(e.target.checked)}
                    className="w-3 h-3"
                  />
                  Auto-scroll
                </label>
                <span className="text-muted-foreground">{orchestratorLogs.length} entries</span>
              </div>
            </div>
          )}

          {/* Agent Logs Tab */}
          {activeTab === "agent" && (
            <div className="h-full flex flex-col">
              {/* Job selector */}
              {systemStatus && systemStatus.running_jobs.length > 0 && (
                <div className="flex items-center gap-2 px-3 py-2 border-b">
                  <span className="text-xs text-muted-foreground">Job:</span>
                  <select
                    value={selectedJobId || ""}
                    onChange={(e) => {
                      setSelectedJobId(e.target.value || null);
                      if (e.target.value) {
                        loadAgentLogs(e.target.value);
                      }
                    }}
                    className="text-xs bg-muted/30 border rounded px-2 py-1"
                  >
                    <option value="">Select a job...</option>
                    {systemStatus.running_jobs.map((job) => (
                      <option key={job.job_id} value={job.job_id}>
                        {job.ticket_title} ({job.kind})
                      </option>
                    ))}
                  </select>
                  {selectedJobId && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => loadAgentLogs(selectedJobId)}
                      className="h-6 px-2 text-xs"
                    >
                      <RefreshCw className="h-3 w-3" />
                    </Button>
                  )}
                </div>
              )}
              
              {/* Agent log content */}
              <div className="flex-1 overflow-y-auto p-2 font-mono text-xs bg-black/5 dark:bg-white/5 whitespace-pre-wrap">
                {loading ? (
                  <div className="flex items-center justify-center h-full">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : agentLogs ? (
                  <>
                    {agentLogs}
                    <div ref={logsEndRef} />
                  </>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                    <Terminal className="h-8 w-8 mb-2 opacity-50" />
                    <p>Select a running job to view logs</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Events Tab */}
          {activeTab === "events" && (
            <div className="h-full overflow-y-auto p-2">
              {recentEvents.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                  <ScrollText className="h-8 w-8 mb-2 opacity-50" />
                  <p>No recent events</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {recentEvents.map((event) => (
                    <div
                      key={event.id}
                      className="flex items-start gap-2 p-2 rounded hover:bg-muted/30 text-xs"
                    >
                      <span className="text-muted-foreground shrink-0 w-16 font-mono">
                        {formatTime(event.created_at)}
                      </span>
                      <Badge variant="outline" className="text-[9px] px-1 shrink-0">
                        {event.event_type}
                      </Badge>
                      <span className="text-muted-foreground shrink-0">
                        {event.actor_type}/{event.actor_id}
                      </span>
                      <span className="flex-1 truncate" title={event.ticket_title || undefined}>
                        {event.ticket_title || event.ticket_id.slice(0, 8)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


