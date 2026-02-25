import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { streamAgentLogs, fetchJobLogs, type StreamNormalizedEntry } from "@/services/api";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";
import { cn } from "@/lib/utils";
import {
  Loader2,
  Terminal,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  Radio,
  Square,
  Brain,
  MessageSquare,
  FileCode,
  FolderOpen,
  Search,
  TerminalSquare,
  Bot,
  AlertCircle,
  Filter,
  Clock,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { JobStatus } from "@/types/api";

interface LiveAgentLogsProps {
  jobId: string;
  jobStatus: JobStatus;
  jobKind: string;
  className?: string;
  defaultExpanded?: boolean;
}

interface ProgressState {
  pct: number;
  stage: string;
}

// Clean, minimal icon and label mapping
const ENTRY_CONFIG: Record<string, { icon: typeof Brain; label: string }> = {
  thinking: { icon: Brain, label: "Thinking" },
  assistant_message: { icon: MessageSquare, label: "Response" },
  system_message: { icon: Bot, label: "System" },
  tool_use: { icon: FileCode, label: "Tool" },
  error_message: { icon: AlertCircle, label: "Error" },
};

const ACTION_ICONS: Record<string, typeof FileCode> = {
  read_file: FileCode,
  write_file: FileCode,
  edit_file: FileCode,
  list_dir: FolderOpen,
  search: Search,
  shell: TerminalSquare,
};

/**
 * Render a single normalized entry with clean, minimal styling
 */
function NormalizedEntryView({ entry, showTimestamp }: { entry: StreamNormalizedEntry; showTimestamp?: boolean }) {
  const config = ENTRY_CONFIG[entry.entry_type] || ENTRY_CONFIG.system_message;
  const Icon = entry.action_type ? (ACTION_ICONS[entry.action_type] || config.icon) : config.icon;
  
  const isThinking = entry.entry_type === "thinking";
  const isError = entry.entry_type === "error_message";
  const isCollapsed = entry.metadata?.collapsed && isThinking;
  const [expanded, setExpanded] = useState(!isCollapsed);
  
  return (
    <div className={cn(
      "py-2 px-3 rounded border-l-2 mb-2",
      isThinking ? "border-l-gray-300 bg-gray-50" : "",
      entry.entry_type === "assistant_message" ? "border-l-blue-400 bg-white" : "",
      entry.entry_type === "tool_use" ? "border-l-gray-400 bg-gray-50" : "",
      isError ? "border-l-red-400 bg-red-50" : "",
      entry.entry_type === "system_message" ? "border-l-gray-300 bg-gray-50" : "",
    )}>
      <div 
        className={cn(
          "flex items-start gap-2",
          isThinking ? "cursor-pointer select-none" : ""
        )}
        onClick={() => isThinking && setExpanded(!expanded)}
      >
        <Icon className="h-4 w-4 mt-0.5 flex-shrink-0 text-gray-400" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
            {showTimestamp && entry.timestamp && (
              <span className="text-[10px] text-gray-400 font-mono tabular-nums">
                {new Date(entry.timestamp).toLocaleTimeString()}
              </span>
            )}
            <span className="font-medium">{config.label}</span>
            {entry.tool_name && (
              <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded font-mono">
                {entry.tool_name}
              </span>
            )}
            {entry.tool_status === "completed" && (
              <Check className="h-3 w-3 text-green-500" />
            )}
            {isThinking && (
              <span className="text-gray-400">
                {expanded ? "▼" : "▶"}
              </span>
            )}
          </div>
          {(expanded || !isThinking) && (
            <div className={cn(
              "text-sm whitespace-pre-wrap break-words text-gray-700",
              isThinking && "text-gray-500 italic text-xs",
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

export function LiveAgentLogs({
  jobId,
  jobStatus,
  jobKind,
  className,
  defaultExpanded = false,
}: LiveAgentLogsProps) {
  const [logs, setLogs] = useState<string>("");
  const [normalizedEntries, setNormalizedEntries] = useState<Map<number, StreamNormalizedEntry>>(new Map());
  const [viewMode, setViewMode] = useState<"normalized" | "raw">("normalized");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [autoScroll, setAutoScroll] = useState(true);
  const [copied, setCopied] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [progress, setProgress] = useState<ProgressState | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const [levelFilter, setLevelFilter] = useState<Set<string>>(new Set());
  const [showTimestamps, setShowTimestamps] = useState(false);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const isRunning = jobStatus === JobStatus.RUNNING || jobStatus === JobStatus.QUEUED;
  const hasNormalizedEntries = normalizedEntries.size > 0;

  // Fetch initial logs
  const loadLogs = useCallback(async () => {
    try {
      const content = await fetchJobLogs(jobId);
      setLogs(content);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load logs";
      // Don't show error if logs just don't exist yet for queued jobs
      if (jobStatus !== JobStatus.QUEUED) {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  }, [jobId, jobStatus]);

  // Set up SSE streaming for running jobs
  useEffect(() => {
    if (!isRunning || !expanded) {
      return;
    }

    // First load existing logs
    loadLogs();

    // Then start streaming
    setIsStreaming(true);
    const eventSource = streamAgentLogs(
      jobId,
      (data) => {
        if (data.content) {
          setLogs((prev) => prev + data.content);
        }
        if (data.normalized) {
          // Update normalized entries map (keyed by sequence for updates)
          setNormalizedEntries((prev) => {
            const updated = new Map(prev);
            updated.set(data.normalized!.sequence, data.normalized!);
            return updated;
          });
        }
        if (data.error) {
          setError(data.error);
        }
        if (data.progress !== undefined && data.stage) {
          setProgress({ pct: data.progress, stage: data.stage });
        }
        if (data.status === "completed") {
          setIsStreaming(false);
          setProgress(null);
          eventSource.close();
        }
      },
      () => {
        setIsStreaming(false);
      }
    );

    eventSourceRef.current = eventSource;

    return () => {
      eventSource.close();
      eventSourceRef.current = null;
      setIsStreaming(false);
      setProgress(null);
    };
  }, [jobId, isRunning, expanded, loadLogs]);

  // Load logs once when expanded for completed jobs
  useEffect(() => {
    if (!isRunning && expanded) {
      loadLogs();
    }
  }, [expanded, isRunning, loadLogs]);

  // Memoize sorted + filtered normalized entries for Virtuoso
  const sortedEntries = useMemo(() => {
    let entries = Array.from(normalizedEntries.values()).sort((a, b) => a.sequence - b.sequence);
    if (levelFilter.size > 0) {
      entries = entries.filter((e) => levelFilter.has(e.entry_type));
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      entries = entries.filter(
        (e) =>
          e.content?.toLowerCase().includes(q) ||
          e.tool_name?.toLowerCase().includes(q)
      );
    }
    return entries;
  }, [normalizedEntries, levelFilter, searchQuery]);

  // Memoize filtered raw log lines for Virtuoso
  const rawLogLines = useMemo(() => {
    if (!logs) return [];
    const lines = logs.split("\n");
    if (!searchQuery) return lines;
    const q = searchQuery.toLowerCase();
    return lines.filter((line) => line.toLowerCase().includes(q));
  }, [logs, searchQuery]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(logs);
      setCopied(true);
      toast.success("Logs copied to clipboard");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Failed to copy logs");
    }
  };

  const lineCount = rawLogLines.length;

  // Status badge colors - clean and minimal
  const getStatusDisplay = () => {
    switch (jobStatus) {
      case JobStatus.RUNNING:
        return {
          color: "text-amber-600 bg-amber-50",
          text: "Running",
          icon: <Radio className="h-3 w-3" />,
        };
      case JobStatus.QUEUED:
        return {
          color: "text-blue-600 bg-blue-50",
          text: "Queued",
          icon: <Loader2 className="h-3 w-3 animate-spin" />,
        };
      case JobStatus.SUCCEEDED:
        return {
          color: "text-green-600 bg-green-50",
          text: "Done",
          icon: <Check className="h-3 w-3" />,
        };
      case JobStatus.FAILED:
        return {
          color: "text-red-600 bg-red-50",
          text: "Failed",
          icon: <AlertCircle className="h-3 w-3" />,
        };
      case JobStatus.CANCELED:
        return {
          color: "text-gray-500 bg-gray-100",
          text: "Canceled",
          icon: <Square className="h-3 w-3" />,
        };
      default:
        return {
          color: "text-gray-500 bg-gray-100",
          text: jobStatus,
          icon: null,
        };
    }
  };

  const statusDisplay = getStatusDisplay();

  return (
    <div
      className={cn(
        "rounded-lg border border-gray-200 overflow-hidden bg-white",
        className
      )}
    >
      {/* Header */}
      <div
        className={cn(
          "flex items-center justify-between px-3 py-2 cursor-pointer transition-colors",
          "bg-gray-50 hover:bg-gray-100 border-b border-gray-200"
        )}
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-gray-400" />
          <span className="text-sm font-medium text-gray-700 capitalize">
            {jobKind}
          </span>
          <span
            className={cn(
              "flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium",
              statusDisplay.color
            )}
          >
            {statusDisplay.icon}
            {statusDisplay.text}
          </span>
          {isStreaming && (
            <span className="flex items-center gap-1 text-[10px] text-green-600 font-medium">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-500 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-500"></span>
              </span>
              Live
            </span>
          )}
          {progress && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-gray-500 capitalize">{progress.stage}</span>
              <div className="w-16 h-1 bg-gray-200 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-green-500 transition-all duration-300"
                  style={{ width: `${progress.pct}%` }}
                />
              </div>
              <span className="text-[10px] text-gray-400">{progress.pct}%</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {logs && (
            <span className="text-[10px] text-gray-400">{lineCount} lines</span>
          )}
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronDown className="h-4 w-4 text-gray-400" />
          )}
        </div>
      </div>

      {/* Logs content */}
      {expanded && (
        <div className="relative">
          {/* View mode toggle */}
          {hasNormalizedEntries && (
            <div className="absolute top-2 left-2 z-10 flex gap-0.5 bg-white border border-gray-200 rounded-md p-0.5 shadow-sm">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setViewMode("normalized");
                }}
                className={cn(
                  "px-2 py-1 text-[10px] font-medium rounded transition-colors",
                  viewMode === "normalized" 
                    ? "bg-gray-100 text-gray-900" 
                    : "text-gray-500 hover:text-gray-700"
                )}
              >
                Formatted
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setViewMode("raw");
                }}
                className={cn(
                  "px-2 py-1 text-[10px] font-medium rounded transition-colors",
                  viewMode === "raw" 
                    ? "bg-gray-100 text-gray-900" 
                    : "text-gray-500 hover:text-gray-700"
                )}
              >
                Raw
              </button>
            </div>
          )}

          {/* Search & filter toolbar */}
          {(showSearch || levelFilter.size > 0) && (
            <div className="flex items-center gap-2 px-3 py-1.5 border-b border-gray-200 bg-white">
              <Search className="h-3.5 w-3.5 text-gray-400 flex-shrink-0" />
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search logs..."
                className="flex-1 text-xs bg-transparent outline-none text-gray-700 placeholder:text-gray-400"
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setSearchQuery("");
                    setShowSearch(false);
                  }
                }}
              />
              {searchQuery && (
                <span className="text-[10px] text-gray-400">
                  {viewMode === "normalized" ? sortedEntries.length : rawLogLines.length} matches
                </span>
              )}
              <button
                onClick={() => {
                  setSearchQuery("");
                  setShowSearch(false);
                }}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {/* Level filter pills (normalized view only) */}
          {viewMode === "normalized" && hasNormalizedEntries && levelFilter.size > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-gray-200 bg-white">
              <Filter className="h-3 w-3 text-gray-400" />
              {Array.from(levelFilter).map((level) => (
                <button
                  key={level}
                  onClick={() =>
                    setLevelFilter((prev) => {
                      const next = new Set(prev);
                      next.delete(level);
                      return next;
                    })
                  }
                  className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 hover:bg-gray-200"
                >
                  {ENTRY_CONFIG[level]?.label || level}
                  <X className="h-2.5 w-2.5" />
                </button>
              ))}
              <button
                onClick={() => setLevelFilter(new Set())}
                className="text-[10px] text-gray-400 hover:text-gray-600 ml-1"
              >
                Clear all
              </button>
            </div>
          )}

          {loading && !logs && !hasNormalizedEntries ? (
            <div className="flex items-center justify-center py-8 bg-zinc-950">
              <Loader2 className="h-5 w-5 animate-spin text-zinc-500" />
            </div>
          ) : error && !logs && !hasNormalizedEntries ? (
            <div className="flex items-center justify-center py-8 bg-zinc-950">
              <p className="text-sm text-zinc-500">{error}</p>
            </div>
          ) : (
            <>
              {/* Toolbar buttons */}
              <div className="absolute top-2 right-2 z-10 flex items-center gap-1">
                {/* Search toggle */}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    setShowSearch((v) => !v);
                    if (!showSearch) {
                      setTimeout(() => searchInputRef.current?.focus(), 50);
                    }
                  }}
                  className={cn(
                    "h-7 w-7 p-0",
                    viewMode === "normalized"
                      ? "bg-white border border-gray-200 hover:bg-gray-50 text-gray-500"
                      : "bg-zinc-800/80 hover:bg-zinc-700 text-zinc-400",
                    showSearch && "ring-1 ring-blue-400"
                  )}
                >
                  <Search className="h-3.5 w-3.5" />
                </Button>

                {/* Level filter (normalized view only) */}
                {viewMode === "normalized" && hasNormalizedEntries && (
                  <div className="relative group">
                    <Button
                      variant="ghost"
                      size="sm"
                      className={cn(
                        "h-7 w-7 p-0",
                        "bg-white border border-gray-200 hover:bg-gray-50 text-gray-500",
                        levelFilter.size > 0 && "ring-1 ring-blue-400"
                      )}
                    >
                      <Filter className="h-3.5 w-3.5" />
                    </Button>
                    <div className="hidden group-hover:block absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg p-1 min-w-[140px]">
                      {Object.entries(ENTRY_CONFIG).map(([key, cfg]) => (
                        <button
                          key={key}
                          onClick={(e) => {
                            e.stopPropagation();
                            setLevelFilter((prev) => {
                              const next = new Set(prev);
                              if (next.has(key)) next.delete(key);
                              else next.add(key);
                              return next;
                            });
                          }}
                          className={cn(
                            "flex items-center gap-2 w-full px-2 py-1 text-xs rounded hover:bg-gray-50",
                            levelFilter.has(key) ? "text-blue-600 font-medium" : "text-gray-600"
                          )}
                        >
                          <cfg.icon className="h-3 w-3" />
                          {cfg.label}
                          {levelFilter.has(key) && <Check className="h-3 w-3 ml-auto" />}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Timestamp toggle (normalized view only) */}
                {viewMode === "normalized" && hasNormalizedEntries && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowTimestamps((v) => !v);
                    }}
                    className={cn(
                      "h-7 w-7 p-0",
                      "bg-white border border-gray-200 hover:bg-gray-50 text-gray-500",
                      showTimestamps && "ring-1 ring-blue-400"
                    )}
                    title="Toggle timestamps"
                  >
                    <Clock className="h-3.5 w-3.5" />
                  </Button>
                )}

                {/* Copy button */}
                {logs && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCopy();
                    }}
                    className={cn(
                      "h-7 w-7 p-0",
                      viewMode === "normalized"
                        ? "bg-white border border-gray-200 hover:bg-gray-50 text-gray-500"
                        : "bg-zinc-800/80 hover:bg-zinc-700 text-zinc-400"
                    )}
                  >
                    {copied ? (
                      <Check className={cn("h-3.5 w-3.5", viewMode === "normalized" ? "text-green-600" : "text-emerald-400")} />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </Button>
                )}
              </div>

              <div
                className={cn(
                  "max-h-[400px] min-h-[120px]",
                  viewMode === "normalized" ? "bg-gray-50" : "bg-zinc-900",
                  viewMode === "raw" && "font-mono text-xs"
                )}
              >
                {viewMode === "normalized" && hasNormalizedEntries ? (
                  // Normalized view - virtualized
                  sortedEntries.length > 0 ? (
                    <Virtuoso
                      ref={virtuosoRef}
                      data={sortedEntries}
                      style={{ height: "400px" }}
                      followOutput={autoScroll ? "smooth" : false}
                      atBottomStateChange={(atBottom) => setAutoScroll(atBottom)}
                      itemContent={(_index, entry) => (
                        <div className="px-3 first:pt-3 last:pb-3">
                          <NormalizedEntryView entry={entry} showTimestamp={showTimestamps} />
                        </div>
                      )}
                    />
                  ) : (
                    <div className="p-3">
                      <span className="text-gray-400 italic text-sm">
                        {isRunning
                          ? "Waiting for agent output..."
                          : "No entries available"}
                      </span>
                    </div>
                  )
                ) : (
                  // Raw view - virtualized terminal style
                  rawLogLines.length > 0 ? (
                    <Virtuoso
                      ref={virtuosoRef}
                      data={rawLogLines}
                      style={{ height: "400px" }}
                      followOutput={autoScroll ? "smooth" : false}
                      atBottomStateChange={(atBottom) => setAutoScroll(atBottom)}
                      itemContent={(_index, line) => (
                        <pre className="px-3 text-zinc-300 whitespace-pre-wrap break-words leading-relaxed">
                          {line}
                        </pre>
                      )}
                    />
                  ) : (
                    <pre className="p-3 text-zinc-300 whitespace-pre-wrap break-words leading-relaxed">
                      <span className="text-zinc-500 italic">
                        {isRunning
                          ? "Waiting for logs..."
                          : "No logs available"}
                      </span>
                    </pre>
                  )
                )}
              </div>

              {/* Auto-scroll indicator for streaming */}
              {isStreaming && !autoScroll && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setAutoScroll(true);
                    virtuosoRef.current?.scrollToIndex({
                      index: "LAST",
                      behavior: "smooth",
                    });
                  }}
                  className={cn(
                    "absolute bottom-2 right-2 px-2 py-1 rounded text-[10px] transition-colors shadow-sm",
                    viewMode === "normalized"
                      ? "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
                      : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                  )}
                >
                  ↓ Resume auto-scroll
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
