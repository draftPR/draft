import { useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Loader2,
  CheckCircle,
  XCircle,
  Brain,
  MessageSquare,
  FileCode,
  FolderOpen,
  Search,
  TerminalSquare,
  Bot,
  AlertCircle,
  Check,
  ChevronDown,
  ChevronRight,
  Link,
  ArrowRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { config } from "@/config";

interface TicketGenerationProgressProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  goalId: string;
  onComplete: () => void;
  /** Called when user clicks "Show me tickets" — should close all dialogs */
  onShowTickets?: () => void;
}

interface NormalizedEntry {
  entry_type: string;
  content: string;
  sequence: number;
  tool_name?: string | null;
  action_type?: string | null;
  tool_status?: string | null;
  metadata?: Record<string, unknown>;
}

interface TicketInfo {
  id: string;
  title: string;
  priority: number;
  description?: string;
  blocked_by_title?: string | null;
}

interface StreamEvent {
  type:
    | "status"
    | "agent_output"
    | "agent_normalized"
    | "ticket"
    | "complete"
    | "error";
  message?: string;
  entry?: NormalizedEntry;
  ticket?: TicketInfo;
  count?: number;
}

const ENTRY_ICONS: Record<string, typeof Brain> = {
  thinking: Brain,
  assistant_message: MessageSquare,
  system_message: Bot,
  tool_use: FileCode,
  error_message: AlertCircle,
};

const ACTION_ICONS: Record<string, typeof FileCode> = {
  read_file: FileCode,
  write_file: FileCode,
  edit_file: FileCode,
  list_dir: FolderOpen,
  search: Search,
  shell: TerminalSquare,
};

const ENTRY_LABELS: Record<string, string> = {
  thinking: "Thinking",
  assistant_message: "Response",
  system_message: "System",
  tool_use: "Tool",
  error_message: "Error",
};

function ThinkingEntry({ entry }: { entry: NormalizedEntry }) {
  const [expanded, setExpanded] = useState(false);
  const lines = entry.content.split("\n");
  const preview = lines[0]?.slice(0, 120) || "...";

  return (
    <div className="py-1.5 px-2.5 rounded border-l-2 border-l-violet-300 bg-violet-50/50">
      <button
        className="flex items-start gap-2 w-full text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <Brain className="h-3.5 w-3.5 mt-0.5 flex-shrink-0 text-violet-400" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-medium text-violet-500 uppercase tracking-wider">
              Thinking
            </span>
            {expanded ? (
              <ChevronDown className="h-3 w-3 text-violet-400" />
            ) : (
              <ChevronRight className="h-3 w-3 text-violet-400" />
            )}
          </div>
          {!expanded && (
            <p className="text-xs text-violet-600/70 italic truncate mt-0.5">
              {preview}
            </p>
          )}
        </div>
      </button>
      {expanded && (
        <div className="mt-1.5 ml-5.5 text-xs text-violet-700/80 italic whitespace-pre-wrap leading-relaxed max-h-[200px] overflow-y-auto">
          {entry.content}
        </div>
      )}
    </div>
  );
}

function ToolEntry({ entry }: { entry: NormalizedEntry }) {
  const Icon =
    (entry.action_type && ACTION_ICONS[entry.action_type]) || FileCode;
  const isCompleted = entry.tool_status === "completed";

  return (
    <div className="py-1.5 px-2.5 rounded border-l-2 border-l-gray-300 bg-gray-50/50">
      <div className="flex items-start gap-2">
        <Icon className="h-3.5 w-3.5 mt-0.5 flex-shrink-0 text-gray-400" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-medium text-gray-500 uppercase tracking-wider">
              {entry.tool_name || "Tool"}
            </span>
            {isCompleted && <Check className="h-3 w-3 text-green-500" />}
          </div>
          <p className="text-xs text-gray-600 font-mono whitespace-pre-wrap break-words mt-0.5">
            {entry.content}
          </p>
        </div>
      </div>
    </div>
  );
}

function AssistantEntry({
  entry,
  isStreaming,
}: {
  entry: NormalizedEntry;
  isStreaming: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const contentLength = entry.content.length;
  const isLong = contentLength > 200;
  const preview = entry.content.slice(0, 120).split("\n")[0] || "...";

  return (
    <div className="py-1.5 px-2.5 rounded border-l-2 border-l-emerald-400 bg-emerald-50/30">
      <button
        className="flex items-start gap-2 w-full text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <MessageSquare className="h-3.5 w-3.5 mt-0.5 flex-shrink-0 text-emerald-500" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-medium text-emerald-600 uppercase tracking-wider">
              Agent Response
            </span>
            {isStreaming && (
              <span className="inline-block w-1.5 h-3 bg-emerald-500 animate-pulse rounded-sm" />
            )}
            {isLong && (
              <>
                {expanded ? (
                  <ChevronDown className="h-3 w-3 text-emerald-400" />
                ) : (
                  <ChevronRight className="h-3 w-3 text-emerald-400" />
                )}
              </>
            )}
            <span className="text-[10px] text-emerald-400/70 ml-auto">
              {contentLength > 0 && `${contentLength} chars`}
            </span>
          </div>
          {(!isLong || expanded) ? (
            <pre className="text-xs text-gray-700 whitespace-pre-wrap break-words mt-0.5 leading-relaxed font-mono max-h-[300px] overflow-y-auto">
              {entry.content}
            </pre>
          ) : (
            <p className="text-xs text-emerald-600/70 truncate mt-0.5 font-mono">
              {preview}
            </p>
          )}
        </div>
      </button>
    </div>
  );
}

function SystemEntry({ entry }: { entry: NormalizedEntry }) {
  const Icon = ENTRY_ICONS[entry.entry_type] || Bot;
  const label = ENTRY_LABELS[entry.entry_type] || "System";
  const isError = entry.entry_type === "error_message";

  return (
    <div
      className={cn(
        "py-1.5 px-2.5 rounded border-l-2",
        isError
          ? "border-l-red-400 bg-red-50/50"
          : "border-l-gray-300 bg-gray-50/30"
      )}
    >
      <div className="flex items-start gap-2">
        <Icon
          className={cn(
            "h-3.5 w-3.5 mt-0.5 flex-shrink-0",
            isError ? "text-red-400" : "text-gray-400"
          )}
        />
        <div className="flex-1 min-w-0">
          <span
            className={cn(
              "text-[10px] font-medium uppercase tracking-wider",
              isError ? "text-red-500" : "text-gray-500"
            )}
          >
            {label}
          </span>
          <p
            className={cn(
              "text-xs whitespace-pre-wrap break-words mt-0.5",
              isError ? "text-red-600" : "text-gray-600"
            )}
          >
            {entry.content}
          </p>
        </div>
      </div>
    </div>
  );
}

function NormalizedEntryView({
  entry,
  isStreaming,
}: {
  entry: NormalizedEntry;
  isStreaming: boolean;
}) {
  switch (entry.entry_type) {
    case "thinking":
      return <ThinkingEntry entry={entry} />;
    case "tool_use":
      return <ToolEntry entry={entry} />;
    case "assistant_message":
      return <AssistantEntry entry={entry} isStreaming={isStreaming} />;
    default:
      return <SystemEntry entry={entry} />;
  }
}

const PRIORITY_CONFIG: Record<
  number,
  { label: string; color: string; bg: string; border: string }
> = {
  0: {
    label: "P0",
    color: "text-red-700",
    bg: "bg-red-100",
    border: "border-red-200",
  },
  1: {
    label: "P1",
    color: "text-orange-700",
    bg: "bg-orange-100",
    border: "border-orange-200",
  },
  2: {
    label: "P2",
    color: "text-blue-700",
    bg: "bg-blue-100",
    border: "border-blue-200",
  },
  3: {
    label: "P3",
    color: "text-gray-600",
    bg: "bg-gray-100",
    border: "border-gray-200",
  },
};

function PriorityBadge({ priority }: { priority: number }) {
  const pCfg =
    PRIORITY_CONFIG[priority] || PRIORITY_CONFIG[2];
  return (
    <span
      className={cn(
        "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold border",
        pCfg.bg,
        pCfg.color,
        pCfg.border
      )}
    >
      {pCfg.label}
    </span>
  );
}

function TicketSummaryCard({ ticket }: { ticket: TicketInfo }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3 space-y-1.5">
      <div className="flex items-start gap-2">
        <PriorityBadge priority={ticket.priority} />
        <h4 className="text-sm font-medium text-gray-900 leading-tight flex-1">
          {ticket.title}
        </h4>
      </div>
      {ticket.description && (
        <p className="text-xs text-gray-500 leading-relaxed pl-0.5">
          {ticket.description}
        </p>
      )}
      {ticket.blocked_by_title && (
        <div className="flex items-center gap-1.5 pl-0.5">
          <Link className="h-3 w-3 text-amber-500 flex-shrink-0" />
          <span className="text-[11px] text-amber-600">
            Blocked by: {ticket.blocked_by_title}
          </span>
        </div>
      )}
    </div>
  );
}

export function TicketGenerationProgress({
  open,
  onOpenChange,
  goalId,
  onComplete,
  onShowTickets,
}: TicketGenerationProgressProps) {
  const [normalizedEntries, setNormalizedEntries] = useState<
    Map<number, NormalizedEntry>
  >(new Map());
  const [rawLines, setRawLines] = useState<string[]>([]);
  const [statusMessages, setStatusMessages] = useState<string[]>([]);
  const [tickets, setTickets] = useState<TicketInfo[]>([]);
  const [isComplete, setIsComplete] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [ticketCount, setTicketCount] = useState(0);
  const [showSummary, setShowSummary] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const onCompleteRef = useRef(onComplete);
  const onOpenChangeRef = useRef(onOpenChange);
  const onShowTicketsRef = useRef(onShowTickets);
  useEffect(() => { onCompleteRef.current = onComplete; }, [onComplete]);
  useEffect(() => { onOpenChangeRef.current = onOpenChange; }, [onOpenChange]);
  useEffect(() => { onShowTicketsRef.current = onShowTickets; }, [onShowTickets]);

  // Auto-scroll to bottom (only when not in summary view)
  useEffect(() => {
    if (scrollRef.current && !showSummary) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [normalizedEntries, rawLines, statusMessages, tickets, showSummary]);

  // Auto-transition to summary when generation completes with tickets
  useEffect(() => {
    if (isComplete && ticketCount > 0 && tickets.length > 0) {
      // Short delay so the user sees the completion message briefly
      const timer = setTimeout(() => setShowSummary(true), 600);
      return () => clearTimeout(timer);
    }
  }, [isComplete, ticketCount, tickets.length]);

  useEffect(() => {
    if (!open) return;

    // Reset state at the start of a new stream
    const resetState = () => {
      setNormalizedEntries(new Map());
      setRawLines([]);
      setStatusMessages([]);
      setTickets([]);
      setIsComplete(false);
      setHasError(false);
      setErrorMessage(null);
      setTicketCount(0);
      setShowSummary(false);
    };
    resetState();

    const eventSource = new EventSource(
      `${config.backendBaseUrl}/goals/${goalId}/generate-tickets/stream`
    );

    eventSource.onmessage = (event) => {
      let data: StreamEvent;
      try {
        data = JSON.parse(event.data);
      } catch {
        console.warn('SSE: ignoring non-JSON frame', event.data);
        return;
      }

      switch (data.type) {
        case "agent_normalized":
          if (data.entry) {
            setNormalizedEntries((prev) => {
              const updated = new Map(prev);
              updated.set(data.entry!.sequence, data.entry!);
              return updated;
            });
          }
          break;

        case "agent_output":
          if (data.message) {
            setRawLines((prev) => [...prev, data.message!]);
          }
          break;

        case "ticket":
          if (data.ticket) {
            setTickets((prev) => [...prev, data.ticket!]);
          }
          break;

        case "complete":
          setIsComplete(true);
          setTicketCount(data.count || 0);
          eventSource.close();
          onCompleteRef.current();
          break;

        case "error":
          setHasError(true);
          setErrorMessage(data.message || "An error occurred");
          eventSource.close();
          break;

        case "status":
          if (data.message) {
            setStatusMessages((prev) => [...prev, data.message!]);
          }
          break;

        default:
          break;
      }
    };

    eventSource.onerror = (error) => {
      console.error("SSE error:", error);
      eventSource.close();
      // Only show "Connection lost" if we haven't already received a server error or completion
      setIsComplete((wasComplete) => {
        if (!wasComplete) {
          setHasError((hadError) => {
            if (!hadError) {
              setErrorMessage("Connection lost. Please try again.");
            }
            return true;
          });
        }
        return wasComplete;
      });
    };

    return () => {
      eventSource.close();
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [open, goalId]);

  const sortedEntries = Array.from(normalizedEntries.values()).sort(
    (a, b) => a.sequence - b.sequence
  );
  const hasNormalized = sortedEntries.length > 0;
  const hasContent = hasNormalized || rawLines.length > 0 || statusMessages.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-[680px] max-h-[85vh] flex flex-col"
        onInteractOutside={(e) => {
          // Prevent closing by clicking outside while generating
          if (!isComplete && !hasError) e.preventDefault();
        }}
        onEscapeKeyDown={(e) => {
          // Prevent closing by Escape while generating
          if (!isComplete && !hasError) e.preventDefault();
        }}
      >
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="flex items-center gap-2">
            {!isComplete && !hasError && (
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-500 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500"></span>
              </span>
            )}
            {isComplete && !showSummary && (
              <CheckCircle className="h-5 w-5 text-green-600" />
            )}
            {hasError && <XCircle className="h-5 w-5 text-red-600" />}
            {showSummary
              ? `✅ ${ticketCount} Ticket${ticketCount !== 1 ? "s" : ""} Generated`
              : isComplete
                ? "Tickets Generated"
                : hasError
                  ? "Generation Failed"
                  : "Agent Generating Tickets"}
          </DialogTitle>
          <DialogDescription>
            {showSummary
              ? "Ready for your review"
              : isComplete
                ? `Created ${ticketCount} ticket(s) successfully`
                : hasError
                  ? errorMessage
                  : "Watching the AI agent analyze your codebase and plan tickets..."}
          </DialogDescription>
        </DialogHeader>

        {showSummary ? (
          /* ── Summary / Approval View ── */
          <div className="flex-1 min-h-0 max-h-[500px] overflow-y-auto py-2">
            {/* Summary stats bar */}
            {(() => {
              const highCount = tickets.filter(
                (t) => t.priority <= 1
              ).length;
              const depCount = tickets.filter(
                (t) => t.blocked_by_title
              ).length;
              const stats: string[] = [];
              if (highCount > 0)
                stats.push(
                  `${highCount} high priority`
                );
              if (depCount > 0)
                stats.push(
                  `${depCount} with dependencies`
                );
              if (stats.length === 0) return null;
              return (
                <div className="mb-3 px-1">
                  <p className="text-xs text-gray-500">
                    {stats.join(" · ")}
                  </p>
                </div>
              );
            })()}

            {/* Ticket cards */}
            <div className="space-y-2 px-1">
              {tickets.map((ticket) => (
                <TicketSummaryCard
                  key={ticket.id}
                  ticket={ticket}
                />
              ))}
            </div>
          </div>
        ) : (
          /* ── Chain-of-thought Stream View ── */
          <div
            ref={scrollRef}
            className="flex-1 min-h-0 max-h-[500px] overflow-y-auto space-y-1.5 py-2"
          >
            {/* Status messages (shown before agent output arrives) */}
            {statusMessages.map((msg, idx) => {
              const isLastStatus =
                idx === statusMessages.length - 1;
              const showSpinner =
                isLastStatus &&
                !isComplete &&
                !hasError &&
                !hasNormalized;

              return (
                <div
                  key={`status-${idx}`}
                  className="py-1.5 px-2.5 rounded border-l-2 border-l-blue-300 bg-blue-50/30"
                >
                  <div className="flex items-center gap-2">
                    {showSpinner ? (
                      <Loader2 className="h-3 w-3 animate-spin text-blue-400 flex-shrink-0" />
                    ) : (
                      <Check className="h-3 w-3 text-blue-400 flex-shrink-0" />
                    )}
                    <p className="text-xs text-blue-600">
                      {msg}
                    </p>
                  </div>
                </div>
              );
            })}

            {/* Normalized entries (structured agent output) */}
            {hasNormalized &&
              sortedEntries.map((entry, idx) => (
                <NormalizedEntryView
                  key={entry.sequence}
                  entry={entry}
                  isStreaming={
                    !isComplete &&
                    !hasError &&
                    idx === sortedEntries.length - 1
                  }
                />
              ))}

            {/* Raw fallback lines (if no normalized entries) */}
            {!hasNormalized &&
              rawLines.length > 0 &&
              rawLines.map((line, idx) => (
                <div
                  key={idx}
                  className="py-1 px-2.5 text-xs font-mono text-gray-600 whitespace-pre-wrap break-words"
                >
                  {line}
                </div>
              ))}

            {/* Created tickets */}
            {tickets.map((ticket) => (
              <div
                key={ticket.id}
                className="py-1.5 px-2.5 rounded border-l-2 border-l-green-400 bg-green-50/50"
              >
                <div className="flex items-start gap-2">
                  <CheckCircle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0 text-green-500" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] font-medium text-green-600 uppercase tracking-wider">
                        Created
                      </span>
                      <span className="text-[10px] text-green-500/70">
                        P{ticket.priority}
                      </span>
                    </div>
                    <p className="text-xs text-gray-700 font-medium mt-0.5">
                      {ticket.title}
                    </p>
                  </div>
                </div>
              </div>
            ))}

            {/* Completion message */}
            {isComplete && (
              <div className="py-2 px-2.5 rounded border-l-2 border-l-green-500 bg-green-50/70">
                <div className="flex items-center gap-2">
                  <CheckCircle className="h-4 w-4 text-green-600" />
                  <p className="text-sm font-medium text-green-700">
                    Generation complete — {ticketCount}{" "}
                    ticket(s) created
                  </p>
                </div>
              </div>
            )}

            {/* Error message */}
            {hasError && (
              <div className="py-2 px-2.5 rounded border-l-2 border-l-red-400 bg-red-50/70">
                <div className="flex items-start gap-2">
                  <XCircle className="h-4 w-4 mt-0.5 text-red-500" />
                  <p className="text-sm text-red-700">
                    {errorMessage}
                  </p>
                </div>
              </div>
            )}

            {/* Empty state */}
            {!hasContent &&
              !isComplete &&
              !hasError && (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-3">
                  <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
                  <span className="text-sm text-gray-500">
                    Starting agent...
                  </span>
                </div>
              )}
          </div>
        )}

        {(isComplete || hasError) && (
          <DialogFooter className="flex-shrink-0 pt-2">
            {showSummary && onShowTickets ? (
              <Button
                onClick={() => onShowTicketsRef.current?.()}
                className="gap-2"
              >
                Approve & View Board
                <ArrowRight className="h-4 w-4" />
              </Button>
            ) : isComplete && ticketCount > 0 && onShowTickets ? (
              <Button
                onClick={() => onShowTicketsRef.current?.()}
                className="gap-2"
              >
                <CheckCircle className="h-4 w-4" />
                Show me tickets
              </Button>
            ) : (
              <Button
                variant="outline"
                onClick={() => onOpenChangeRef.current(false)}
              >
                Close
              </Button>
            )}
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
