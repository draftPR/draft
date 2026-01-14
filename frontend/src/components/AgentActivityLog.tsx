/**
 * AgentActivityLog component - displays the agent's chain of thought,
 * tool calls, file edits, and other execution details for a ticket.
 *
 * Styled to match vibe-kanban's clean conversation UI with proper
 * markdown rendering for agent responses.
 */

import { useState, useEffect, useCallback } from "react";
import {
  Brain,
  FileCode,
  FilePlus,
  FileX,
  Terminal,
  Wrench,
  AlertTriangle,
  MessageSquare,
  Info,
  ChevronDown,
  Loader2,
  RefreshCw,
  Clock,
  CheckCircle2,
  XCircle,
  Circle,
  Play,
  ListChecks,
  Bot,
  Check,
  Square,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  fetchTicketAgentLogs,
  streamAgentLogs,
  type TicketAgentLogsResponse,
  type JobExecutionSummary,
  type StreamNormalizedEntry,
} from "@/services/api";
import type { NormalizedLogEntry, LogEntryType } from "@/types/logs";
import { useRef } from "react";

interface Props {
  ticketId: string;
  className?: string;
}

// Entry type configuration matching vibe-kanban's minimal style
const ENTRY_CONFIG: Record<
  LogEntryType,
  { icon: typeof Brain; label: string; color?: string }
> = {
  thinking: { icon: Brain, label: "Thinking", color: "text-purple-400" },
  assistant_message: { icon: Bot, label: "Assistant" },
  file_edit: { icon: FileCode, label: "Edited", color: "text-blue-400" },
  file_create: { icon: FilePlus, label: "Created", color: "text-green-400" },
  file_delete: { icon: FileX, label: "Deleted", color: "text-red-400" },
  command_run: { icon: Terminal, label: "Command", color: "text-amber-400" },
  tool_call: { icon: Wrench, label: "Tool", color: "text-cyan-400" },
  error: { icon: AlertTriangle, label: "Error", color: "text-red-500" },
  user_message: { icon: MessageSquare, label: "User", color: "text-emerald-400" },
  system_message: { icon: Info, label: "System", color: "text-slate-400" },
  loading: { icon: Loader2, label: "Loading" },
  todo_list: { icon: ListChecks, label: "Tasks", color: "text-violet-400" },
};

// Job status with icon and color
const JOB_STATUS: Record<string, { icon: typeof Circle; color: string }> = {
  queued: { icon: Circle, color: "text-muted-foreground" },
  running: { icon: Play, color: "text-blue-500" },
  succeeded: { icon: CheckCircle2, color: "text-emerald-500" },
  failed: { icon: XCircle, color: "text-red-500" },
  canceled: { icon: XCircle, color: "text-amber-500" },
};

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

// Status dot component like vibe-kanban's ToolStatusDot
function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    succeeded: "bg-emerald-500",
    failed: "bg-red-500",
    running: "bg-blue-500 animate-pulse",
    queued: "bg-slate-400",
    canceled: "bg-amber-500",
  };
  return (
    <span
      className={cn(
        "absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border border-background",
        colors[status] || "bg-slate-400"
      )}
    />
  );
}

// Simple markdown-like rendering for agent messages
function RenderMarkdownContent({ content }: { content: string }) {
  // Split content by code blocks and render accordingly
  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className="space-y-3">
      {parts.map((part, i) => {
        if (part.startsWith("```") && part.endsWith("```")) {
          // Code block
          const codeContent = part.slice(3, -3);
          const firstLineEnd = codeContent.indexOf("\n");
          const language = firstLineEnd > 0 ? codeContent.slice(0, firstLineEnd).trim() : "";
          const code = firstLineEnd > 0 ? codeContent.slice(firstLineEnd + 1) : codeContent;

          return (
            <pre
              key={i}
              className="bg-muted/50 border rounded-md p-3 overflow-x-auto text-xs font-mono"
            >
              {language && (
                <div className="text-[10px] text-muted-foreground uppercase mb-2 font-sans">
                  {language}
                </div>
              )}
              <code>{code}</code>
            </pre>
          );
        }

        // Regular text - handle basic markdown
        return (
          <div key={i} className="space-y-2">
            {part.split("\n\n").map((paragraph, j) => (
              <RenderParagraph key={j} text={paragraph} />
            ))}
          </div>
        );
      })}
    </div>
  );
}

function RenderParagraph({ text }: { text: string }) {
  const lines = text.split("\n");

  // Check if this is a list
  const isBulletList = lines.every(
    (l) => !l.trim() || l.trim().startsWith("- ") || l.trim().startsWith("* ") || l.trim().startsWith("• ")
  );
  const isNumberedList = lines.every(
    (l) => !l.trim() || /^\d+\.\s/.test(l.trim())
  );

  if (isBulletList && lines.some((l) => l.trim())) {
    return (
      <ul className="space-y-1 ml-1">
        {lines.map((line, i) => {
          const trimmed = line.trim();
          if (!trimmed) return null;
          const content = trimmed.replace(/^[-*•]\s*/, "");
          return (
            <li key={i} className="flex items-start gap-2 text-sm">
              <span className="text-muted-foreground mt-1.5">•</span>
              <span className="leading-relaxed">{renderInlineStyles(content)}</span>
            </li>
          );
        })}
      </ul>
    );
  }

  if (isNumberedList && lines.some((l) => l.trim())) {
    return (
      <ol className="space-y-1 ml-1">
        {lines.map((line, i) => {
          const trimmed = line.trim();
          if (!trimmed) return null;
          const match = trimmed.match(/^(\d+)\.\s*(.*)/);
          if (!match) return null;
          return (
            <li key={i} className="flex items-start gap-2 text-sm">
              <span className="text-muted-foreground font-medium min-w-[1.5rem]">
                {match[1]}.
              </span>
              <span className="leading-relaxed">{renderInlineStyles(match[2])}</span>
            </li>
          );
        })}
      </ol>
    );
  }

  // Check for heading
  if (text.trim().startsWith("## ")) {
    return (
      <h3 className="text-sm font-semibold mt-3 mb-1">
        {text.trim().slice(3)}
      </h3>
    );
  }
  if (text.trim().startsWith("# ")) {
    return (
      <h2 className="text-base font-semibold mt-4 mb-2">
        {text.trim().slice(2)}
      </h2>
    );
  }

  // Regular paragraph
  return (
    <p className="text-sm leading-relaxed">
      {lines.map((line, i) => (
        <span key={i}>
          {renderInlineStyles(line)}
          {i < lines.length - 1 && <br />}
        </span>
      ))}
    </p>
  );
}

function renderInlineStyles(text: string): React.ReactNode {
  // Handle inline code
  const parts = text.split(/(`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={i} className="bg-muted px-1 py-0.5 rounded text-xs font-mono">
          {part.slice(1, -1)}
        </code>
      );
    }
    // Handle bold
    const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
    return boldParts.map((bp, j) => {
      if (bp.startsWith("**") && bp.endsWith("**")) {
        return <strong key={`${i}-${j}`}>{bp.slice(2, -2)}</strong>;
      }
      return bp;
    });
  });
}

// Todo list component
function TodoList({ todos }: { todos: Array<{ content: string; completed: boolean }> }) {
  return (
    <div className="space-y-1.5">
      {todos.map((todo, i) => (
        <div key={i} className="flex items-start gap-2 text-sm">
          {todo.completed ? (
            <Check className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" />
          ) : (
            <Square className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
          )}
          <span className={cn(todo.completed && "text-muted-foreground line-through")}>
            {todo.content}
          </span>
        </div>
      ))}
    </div>
  );
}

// Individual log entry - clean layout like vibe-kanban
function LogEntry({ entry }: { entry: NormalizedLogEntry }) {
  const [expanded, setExpanded] = useState(
    entry.entry_type === "assistant_message" || entry.entry_type === "todo_list"
  );
  const config = ENTRY_CONFIG[entry.entry_type] || ENTRY_CONFIG.system_message;
  const Icon = config.icon;

  const metadata = entry.metadata as {
    file_path?: string;
    diff?: string;
    command?: string;
    exit_code?: number;
    tool_name?: string;
    todos?: Array<{ content: string; completed: boolean }>;
  };

  const isThinking = entry.entry_type === "thinking";
  const isError = entry.entry_type === "error";
  const isAssistant = entry.entry_type === "assistant_message";
  const isTodoList = entry.entry_type === "todo_list";
  const isFileOp = ["file_edit", "file_create", "file_delete"].includes(entry.entry_type);
  const isCommand = entry.entry_type === "command_run";

  const hasExpandableContent = entry.content.length > 300 || metadata.diff;

  // For assistant messages, always show full content with markdown
  if (isAssistant) {
    return (
      <div className="text-sm">
        <RenderMarkdownContent content={entry.content} />
      </div>
    );
  }

  // For todo lists, render with checkboxes
  if (isTodoList && metadata.todos) {
    return (
      <div className="flex items-start gap-3 text-sm">
        <span className="relative shrink-0 mt-0.5">
          <ListChecks className={cn("h-4 w-4", config.color)} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-medium text-muted-foreground mb-2">
            Todos ({metadata.todos.length})
          </div>
          <TodoList todos={metadata.todos} />
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex items-start gap-3 text-sm",
        isThinking && "text-muted-foreground",
        isError && "text-red-500"
      )}
    >
      {/* Icon */}
      <span className="relative shrink-0 mt-0.5">
        <Icon className={cn("h-4 w-4", config.color)} />
      </span>

      {/* Content */}
      <div className="flex-1 min-w-0 space-y-1">
        {/* Header with file path or command */}
        {(metadata.file_path || metadata.command || metadata.tool_name) && (
          <div className="flex items-center gap-2 flex-wrap">
            {metadata.file_path && (
              <code className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono">
                {metadata.file_path}
              </code>
            )}
            {metadata.tool_name && (
              <span className="text-xs text-muted-foreground">
                {metadata.tool_name}
              </span>
            )}
            {metadata.command && (
              <code className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono truncate max-w-[300px]">
                $ {metadata.command}
              </code>
            )}
            {metadata.exit_code !== undefined && (
              <span
                className={cn(
                  "text-xs",
                  metadata.exit_code === 0 ? "text-emerald-500" : "text-red-500"
                )}
              >
                exit {metadata.exit_code}
              </span>
            )}
          </div>
        )}

        {/* Main content */}
        <div
          className={cn(
            "text-sm",
            isThinking && "opacity-70 italic",
            !expanded && hasExpandableContent && "line-clamp-3"
          )}
        >
          <span className="whitespace-pre-wrap break-words font-light leading-relaxed">
            {expanded ? entry.content : entry.content.slice(0, 250)}
            {!expanded && entry.content.length > 250 && "..."}
          </span>
        </div>

        {/* Expand toggle */}
        {hasExpandableContent && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
          >
            <ChevronDown
              className={cn(
                "h-3 w-3 transition-transform",
                expanded && "rotate-180"
              )}
            />
            {expanded ? "Show less" : "Show more"}
          </button>
        )}

        {/* Diff viewer */}
        {expanded && metadata.diff && (
          <pre className="mt-2 text-xs bg-muted/50 p-3 rounded overflow-x-auto font-mono border">
            {metadata.diff}
          </pre>
        )}
      </div>
    </div>
  );
}

// Embedded live streaming logs for running jobs
function LiveAgentLogsEmbed({ 
  jobId, 
  jobStatus 
}: { 
  jobId: string; 
  jobStatus: string;
}) {
  const [entries, setEntries] = useState<Map<number, StreamNormalizedEntry>>(new Map());
  const [rawLogs, setRawLogs] = useState<string>("");
  const containerRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    if (jobStatus !== "running" && jobStatus !== "queued") return;
    
    const eventSource = streamAgentLogs(
      jobId,
      (data) => {
        if (data.content) {
          setRawLogs((prev) => prev + data.content);
        }
        if (data.normalized) {
          setEntries((prev) => {
            const updated = new Map(prev);
            updated.set(data.normalized!.sequence, data.normalized!);
            return updated;
          });
        }
        // Auto-scroll
        if (containerRef.current) {
          containerRef.current.scrollTop = containerRef.current.scrollHeight;
        }
      },
      () => {}
    );
    
    return () => eventSource.close();
  }, [jobId, jobStatus]);
  
  const sortedEntries = Array.from(entries.values()).sort((a, b) => a.sequence - b.sequence);
  
  if (sortedEntries.length === 0 && !rawLogs) {
    return (
      <div className="px-4 py-6 text-center text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin mx-auto mb-2" />
        Waiting for agent output...
      </div>
    );
  }
  
  return (
    <div 
      ref={containerRef}
      className="max-h-[400px] overflow-auto bg-gray-50 p-3"
    >
      {sortedEntries.length > 0 ? (
        sortedEntries.map((entry) => (
          <StreamEntryView key={entry.sequence} entry={entry} />
        ))
      ) : (
        <pre className="text-xs text-gray-600 whitespace-pre-wrap">{rawLogs}</pre>
      )}
    </div>
  );
}

// Render a streamed entry (similar to LiveAgentLogs)
function StreamEntryView({ entry }: { entry: StreamNormalizedEntry }) {
  const [expanded, setExpanded] = useState(entry.entry_type !== "thinking");
  
  const getConfig = () => {
    switch (entry.entry_type) {
      case "thinking": return { icon: Brain, label: "Thinking" };
      case "assistant_message": return { icon: MessageSquare, label: "Response" };
      case "system_message": return { icon: Bot, label: "System" };
      case "tool_use": return { icon: Terminal, label: "Tool" };
      case "error_message": return { icon: AlertTriangle, label: "Error" };
      default: return { icon: Info, label: "Info" };
    }
  };
  
  const config = getConfig();
  const Icon = config.icon;
  const isThinking = entry.entry_type === "thinking";
  const isError = entry.entry_type === "error_message";
  
  return (
    <div className={cn(
      "py-2 px-3 rounded border-l-2 mb-2",
      isThinking ? "border-l-gray-300 bg-gray-100" : "",
      entry.entry_type === "assistant_message" ? "border-l-blue-400 bg-white" : "",
      entry.entry_type === "tool_use" ? "border-l-gray-400 bg-white" : "",
      isError ? "border-l-red-400 bg-red-50" : "",
      entry.entry_type === "system_message" ? "border-l-gray-300 bg-gray-100" : "",
    )}>
      <div 
        className={cn("flex items-start gap-2", isThinking && "cursor-pointer")}
        onClick={() => isThinking && setExpanded(!expanded)}
      >
        <Icon className="h-4 w-4 mt-0.5 text-gray-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
            <span className="font-medium">{config.label}</span>
            {entry.tool_name && (
              <span className="bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded font-mono text-[10px]">
                {entry.tool_name}
              </span>
            )}
            {entry.tool_status === "completed" && (
              <Check className="h-3 w-3 text-green-500" />
            )}
            {isThinking && (
              <span className="text-gray-400">{expanded ? "▼" : "▶"}</span>
            )}
          </div>
          {(expanded || !isThinking) && (
            <div className={cn(
              "text-sm whitespace-pre-wrap break-words",
              isThinking ? "text-gray-500 italic text-xs" : "text-gray-700",
              isError && "text-red-600"
            )}>
              {entry.content}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Job execution card - collapsible like vibe-kanban
// Uses LiveAgentLogs for running jobs, shows parsed entries for completed jobs
function ExecutionCard({
  execution,
  defaultExpanded = false,
  onJobComplete,
}: {
  execution: JobExecutionSummary;
  defaultExpanded?: boolean;
  onJobComplete?: () => void;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [wasRunning, setWasRunning] = useState(
    execution.job_status === "running" || execution.job_status === "queued"
  );
  const status = JOB_STATUS[execution.job_status] || JOB_STATUS.queued;
  const StatusIcon = status.icon;
  
  const isRunning = execution.job_status === "running" || execution.job_status === "queued";
  
  // Detect when job transitions from running to completed
  useEffect(() => {
    if (wasRunning && !isRunning) {
      // Job just finished - trigger refresh to get parsed logs
      onJobComplete?.();
    }
    setWasRunning(isRunning);
  }, [isRunning, wasRunning, onJobComplete]);

  return (
    <div className="rounded-md border overflow-hidden bg-card">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={cn(
          "w-full px-4 py-3 flex items-center gap-3 text-left",
          "bg-muted/30 hover:bg-muted/50 transition-colors"
        )}
      >
        {/* Status icon with dot */}
        <span className="relative shrink-0">
          <StatusIcon className={cn("h-4 w-4", status.color)} />
          <StatusDot status={execution.job_status} />
        </span>

        {/* Job info */}
        <div className="flex-1 min-w-0 flex items-center gap-3">
          <span className="text-sm font-medium capitalize">
            {execution.job_kind}
          </span>
          <span className={cn("text-xs capitalize", status.color)}>
            {execution.job_status}
          </span>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-3 text-xs text-muted-foreground shrink-0">
          {execution.duration_seconds !== null && (
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatDuration(execution.duration_seconds)}
            </span>
          )}
          <span>{execution.entry_count} entries</span>
        </div>

        {/* Chevron */}
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
            !expanded && "-rotate-90"
          )}
        />
      </button>

      {/* Content */}
      {expanded && (
        <div className="border-t bg-background">
          {isRunning ? (
            // Use LiveAgentLogs for running jobs to show streaming output
            <LiveAgentLogsEmbed 
              jobId={execution.job_id} 
              jobStatus={execution.job_status}
            />
          ) : execution.entries.length > 0 ? (
            <div className="px-4 py-4 space-y-4">
              {execution.entries.map((entry) => (
                <LogEntry key={entry.id} entry={entry} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-4">
              No log entries recorded
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function AgentActivityLog({ ticketId, className }: Props) {
  const [data, setData] = useState<TicketAgentLogsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchTicketAgentLogs(ticketId);
      setData(response);
    } catch (err) {
      console.error("[AgentActivityLog] Error loading logs:", err);
      setError(err instanceof Error ? err.message : "Failed to load agent logs");
    } finally {
      setLoading(false);
    }
  }, [ticketId]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);
  
  // Poll for updates while any job is running
  const hasRunningJob = data?.executions.some(
    (e) => e.job_status === "running" || e.job_status === "queued"
  );
  
  useEffect(() => {
    if (!hasRunningJob) return;
    
    const interval = setInterval(() => {
      loadLogs();
    }, 3000); // Poll every 3 seconds
    
    return () => clearInterval(interval);
  }, [hasRunningJob, loadLogs]);

  if (loading) {
    return (
      <div className={cn("flex items-center gap-2 py-6 text-muted-foreground", className)}>
        <Loader2 className="h-4 w-4 animate-spin" />
        <span className="text-sm">Loading agent activity...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className={cn("text-center py-6", className)}>
        <AlertTriangle className="h-5 w-5 text-red-500 mx-auto mb-2" />
        <p className="text-sm text-red-500 mb-3">{error}</p>
        <Button variant="outline" size="sm" onClick={loadLogs}>
          <RefreshCw className="h-3 w-3 mr-1.5" />
          Retry
        </Button>
      </div>
    );
  }

  if (!data || data.total_jobs === 0) {
    return (
      <div className={cn("text-center py-6", className)}>
        <Brain className="h-5 w-5 mx-auto mb-2 text-muted-foreground/50" />
        <p className="text-sm text-muted-foreground">No agent activity yet</p>
        <p className="text-xs text-muted-foreground/70 mt-1">
          Logs will appear here after execution
        </p>
      </div>
    );
  }

  return (
    <div className={cn("space-y-4", className)}>
      {/* Summary header */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <span>
            {data.total_jobs} execution{data.total_jobs !== 1 ? "s" : ""}
          </span>
          <span className="text-border">·</span>
          <span>{data.total_entries} entries</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={loadLogs}
          className="h-6 w-6 p-0"
        >
          <RefreshCw className="h-3 w-3" />
        </Button>
      </div>

      {/* Execution cards */}
      <div className="space-y-3">
        {data.executions.map((execution, index) => (
          <ExecutionCard
            key={execution.job_id}
            execution={execution}
            defaultExpanded={index === 0}
            onJobComplete={loadLogs}
          />
        ))}
      </div>
    </div>
  );
}
