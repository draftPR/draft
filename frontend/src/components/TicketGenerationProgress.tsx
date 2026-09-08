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
  Eye,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { config } from "@/config";

// ── Types ──

interface TicketGenerationProgressProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  goalId: string;
  onComplete: () => void;
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

interface PhaseInfo {
  id: string;
  label: string;
  progress?: { current: number; total: number };
  detail?: string;
  state?: string;
}

interface ReasoningLine {
  id: number;
  text: string;
  type: "thinking" | "tool" | "info";
}

interface ReviewInfo {
  source: string;
  title: string;
  accepted?: boolean;
  result?: string | null;
  confidence?: string | null;
  reasoning?: string | null;
}

interface StreamEvent {
  type:
    | "status"
    | "phase"
    | "agent_output"
    | "agent_normalized"
    | "review"
    | "ticket"
    | "complete"
    | "error";
  message?: string;
  entry?: NormalizedEntry;
  ticket?: TicketInfo;
  count?: number;
  // review fields
  source?: string;
  title?: string;
  accepted?: boolean;
  result?: string | null;
  confidence?: string | null;
  reasoning?: string | null;
  // phase fields
  id?: string;
  label?: string;
  progress?: { current: number; total: number };
  detail?: string;
  state?: string;
  phase?: string;
}

// ── Helpers ──

const MAX_REASONING_LINES = 6;
let reasoningIdCounter = 0;

/** Extract a clean, human-readable line from a thinking block. */
function extractThinkingSummary(content: string): string | null {
  const lines = content.split("\n").filter((l) => l.trim().length > 10);
  if (lines.length === 0) return null;
  // Take the first substantive line, clean up filler
  let line = lines[0].trim();
  // Strip common LLM filler prefixes
  line = line.replace(
    /^(I'll |I will |I need to |I should |Let me |Now I'll |Now let me |OK,? |Okay,? |Alright,? |So,? )/i,
    ""
  );
  // Capitalize first letter
  line = line.charAt(0).toUpperCase() + line.slice(1);
  // Truncate
  if (line.length > 100) line = line.slice(0, 97) + "...";
  return line;
}

/** Extract a compact description from a tool_use entry. */
function extractToolSummary(entry: NormalizedEntry): string | null {
  const action = entry.action_type;
  const content = entry.content.trim();
  if (!content) return null;

  // Extract filename from content (first path-like token)
  const pathMatch = content.match(
    /(?:^|\s)([\w./-]+\.[\w]+|src\/[^\s]+|app\/[^\s]+|[\w/-]+\/[\w.]+)/
  );
  const filename = pathMatch?.[1];

  switch (action) {
    case "read_file":
      return filename ? `Reading \`${filename}\`` : "Reading file";
    case "write_file":
    case "edit_file":
      return filename ? `Editing \`${filename}\`` : "Editing file";
    case "list_dir":
      return filename ? `Exploring \`${filename}\`` : "Exploring directory";
    case "search":
      return `Searching codebase`;
    case "shell":
      return `Running command`;
    default:
      return entry.tool_name ? `Using ${entry.tool_name}` : "Working...";
  }
}

// ── Raw Detail Components (for collapsible section) ──

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
          </div>
          {!isLong || expanded ? (
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

// ── Ticket Summary Components ──

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
  const pCfg = PRIORITY_CONFIG[priority] || PRIORITY_CONFIG[2];
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

// ── Phase Indicator ──

function ReviewCard({ review }: { review: ReviewInfo }) {
  const [expanded, setExpanded] = useState(false);
  const isValidator = review.source === "validator";
  const dropped = isValidator && review.accepted === false;
  const Icon = dropped ? XCircle : isValidator ? CheckCircle : Search;
  const iconColor = dropped
    ? "text-amber-500"
    : isValidator
      ? "text-green-500"
      : "text-blue-500";
  const reasoning = review.reasoning?.trim() || "";
  const long = reasoning.length > 160;

  return (
    <div className="px-1 animate-in fade-in slide-in-from-bottom-1 duration-300">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-start gap-2 w-full text-left"
      >
        <Icon className={cn("h-3.5 w-3.5 mt-0.5 flex-shrink-0", iconColor)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] uppercase tracking-wide text-gray-400 font-medium flex-shrink-0">
              {review.source.replace(/_/g, " ")}
            </span>
            <p className="text-xs text-gray-700 font-medium truncate">
              {review.title}
            </p>
            {dropped && (
              <span className="text-[10px] text-amber-600 flex-shrink-0">
                dropped
              </span>
            )}
          </div>
          {reasoning && (
            <p
              className={cn(
                "text-[11px] text-gray-500 whitespace-pre-wrap break-words",
                !expanded && "line-clamp-2"
              )}
            >
              {reasoning}
            </p>
          )}
        </div>
        {long &&
          (expanded ? (
            <ChevronDown className="h-3 w-3 mt-0.5 text-gray-400 flex-shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 mt-0.5 text-gray-400 flex-shrink-0" />
          ))}
      </button>
    </div>
  );
}

function ReviewsFeed({ reviews }: { reviews: ReviewInfo[] }) {
  if (reviews.length === 0) return null;
  return (
    <div className="space-y-1.5 pt-1">
      <p className="px-1 text-[10px] uppercase tracking-wide text-gray-400 font-medium">
        Reviews
      </p>
      {reviews.map((r, i) => (
        <ReviewCard key={i} review={r} />
      ))}
    </div>
  );
}

function PhaseIndicator({ phase }: { phase: PhaseInfo | null }) {
  if (!phase) return null;

  const isDone = phase.state === "done" || phase.id === "done";
  const hasProgress = phase.progress && phase.progress.total > 0;

  return (
    <div className="flex items-center gap-3 px-1 py-2">
      {isDone ? (
        <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
      ) : (
        <Loader2 className="h-4 w-4 animate-spin text-blue-500 flex-shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <p
          className={cn(
            "text-sm font-medium",
            isDone ? "text-green-700" : "text-gray-800"
          )}
        >
          {phase.label}
        </p>
        {hasProgress && !isDone && (
          <div className="mt-1.5">
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all duration-500 ease-out"
                  style={{
                    width: `${Math.round((phase.progress!.current / phase.progress!.total) * 100)}%`,
                  }}
                />
              </div>
              <span className="text-[11px] text-gray-500 tabular-nums flex-shrink-0">
                {phase.progress!.current}/{phase.progress!.total}
              </span>
            </div>
            {phase.detail && (
              <p className="text-[11px] text-gray-500 mt-1">{phase.detail}</p>
            )}
          </div>
        )}
        {phase.detail && !hasProgress && !isDone && (
          <p className="text-[11px] text-gray-500 mt-0.5">{phase.detail}</p>
        )}
      </div>
    </div>
  );
}

// ── Reasoning Feed ──

function ReasoningFeed({ lines }: { lines: ReasoningLine[] }) {
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [lines]);

  if (lines.length === 0) return null;

  return (
    <div ref={feedRef} className="space-y-1 max-h-[200px] overflow-y-auto">
      {lines.map((line) => (
        <div
          key={line.id}
          className="flex items-start gap-2 px-1 animate-in fade-in slide-in-from-bottom-1 duration-300"
        >
          {line.type === "thinking" ? (
            <Brain className="h-3 w-3 mt-0.5 flex-shrink-0 text-violet-400" />
          ) : line.type === "tool" ? (
            <FileCode className="h-3 w-3 mt-0.5 flex-shrink-0 text-gray-400" />
          ) : (
            <Bot className="h-3 w-3 mt-0.5 flex-shrink-0 text-blue-400" />
          )}
          <p
            className={cn(
              "text-xs leading-relaxed",
              line.type === "thinking"
                ? "text-violet-600/80 italic"
                : line.type === "tool"
                  ? "text-gray-600 font-mono"
                  : "text-blue-600"
            )}
          >
            {line.text}
          </p>
        </div>
      ))}
    </div>
  );
}

// ── Main Component ──

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
  const [currentPhase, setCurrentPhase] = useState<PhaseInfo | null>(null);
  const [reasoningLines, setReasoningLines] = useState<ReasoningLine[]>([]);
  const [tickets, setTickets] = useState<TicketInfo[]>([]);
  const [reviews, setReviews] = useState<ReviewInfo[]>([]);
  const [isComplete, setIsComplete] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [ticketCount, setTicketCount] = useState(0);
  const [showSummary, setShowSummary] = useState(false);
  const [showRawDetails, setShowRawDetails] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const onCompleteRef = useRef(onComplete);
  const onOpenChangeRef = useRef(onOpenChange);
  const onShowTicketsRef = useRef(onShowTickets);
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);
  useEffect(() => {
    onOpenChangeRef.current = onOpenChange;
  }, [onOpenChange]);
  useEffect(() => {
    onShowTicketsRef.current = onShowTickets;
  }, [onShowTickets]);

  // Auto-scroll (only when not in summary view)
  useEffect(() => {
    if (scrollRef.current && !showSummary) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [reasoningLines, tickets, showSummary]);

  // Auto-transition to summary when generation completes with tickets
  useEffect(() => {
    if (isComplete && ticketCount > 0 && tickets.length > 0) {
      const timer = setTimeout(() => setShowSummary(true), 600);
      return () => clearTimeout(timer);
    }
  }, [isComplete, ticketCount, tickets.length]);

  // Add a reasoning line (keeps max N recent lines)
  const addReasoningLine = (text: string, type: ReasoningLine["type"]) => {
    setReasoningLines((prev) => {
      const next = [...prev, { id: ++reasoningIdCounter, text, type }];
      return next.length > MAX_REASONING_LINES
        ? next.slice(-MAX_REASONING_LINES)
        : next;
    });
  };

  useEffect(() => {
    if (!open) return;

    // Reset state
    setNormalizedEntries(new Map());
    setRawLines([]);
    setCurrentPhase(null);
    setReasoningLines([]);
    setTickets([]);
    setReviews([]);
    setIsComplete(false);
    setHasError(false);
    setErrorMessage(null);
    setTicketCount(0);
    setShowSummary(false);
    setShowRawDetails(false);

    const eventSource = new EventSource(
      `${config.backendBaseUrl}/goals/${goalId}/generate-tickets/stream`
    );

    eventSource.onmessage = (event) => {
      let data: StreamEvent;
      try {
        data = JSON.parse(event.data);
      } catch {
        console.warn("SSE: ignoring non-JSON frame", event.data);
        return;
      }

      switch (data.type) {
        case "phase":
          setCurrentPhase({
            id: data.id || data.phase || "unknown",
            label: data.label || "",
            progress: data.progress,
            detail: data.detail,
            state: data.state,
          });
          // Add detail as reasoning line if present
          if (data.detail) {
            addReasoningLine(data.detail, "info");
          }
          break;

        case "agent_normalized":
          if (data.entry) {
            setNormalizedEntries((prev) => {
              const updated = new Map(prev);
              updated.set(data.entry!.sequence, data.entry!);
              return updated;
            });
            // Extract reasoning from normalized entries
            const entry = data.entry;
            if (entry.entry_type === "thinking") {
              const summary = extractThinkingSummary(entry.content);
              if (summary) addReasoningLine(summary, "thinking");
            } else if (entry.entry_type === "tool_use") {
              const summary = extractToolSummary(entry);
              if (summary) addReasoningLine(summary, "tool");
            }
          }
          break;

        case "agent_output":
          if (data.message) {
            setRawLines((prev) => [...prev, data.message!]);
          }
          break;

        case "review":
          setReviews((prev) => [
            ...prev,
            {
              source: data.source || "review",
              title: data.title || "",
              accepted: data.accepted,
              result: data.result,
              confidence: data.confidence,
              reasoning: data.reasoning,
            },
          ]);
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

        // Legacy: handle any remaining status events
        case "status":
          if (data.message) {
            addReasoningLine(data.message, "info");
          }
          break;

        default:
          break;
      }
    };

    eventSource.onerror = (error) => {
      console.error("SSE error:", error);
      eventSource.close();
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
  const hasRawContent = hasNormalized || rawLines.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-[580px] max-h-[85vh] flex flex-col"
        onInteractOutside={(e) => {
          if (!isComplete && !hasError) e.preventDefault();
        }}
        onEscapeKeyDown={(e) => {
          if (!isComplete && !hasError) e.preventDefault();
        }}
      >
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="flex items-center gap-2">
            {!isComplete && !hasError && (
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-500 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500" />
              </span>
            )}
            {isComplete && !showSummary && (
              <CheckCircle className="h-5 w-5 text-green-600" />
            )}
            {hasError && <XCircle className="h-5 w-5 text-red-600" />}
            {showSummary
              ? `${ticketCount} Ticket${ticketCount !== 1 ? "s" : ""} Generated`
              : isComplete
                ? "Tickets Generated"
                : hasError
                  ? "Generation Failed"
                  : "Generating Tickets"}
          </DialogTitle>
          <DialogDescription>
            {showSummary
              ? "Ready for your review"
              : isComplete
                ? `Created ${ticketCount} ticket(s) successfully`
                : hasError
                  ? errorMessage
                  : "AI is analyzing your codebase and planning work"}
          </DialogDescription>
        </DialogHeader>

        {showSummary ? (
          /* ── Summary / Approval View ── */
          <div className="flex-1 min-h-0 max-h-[500px] overflow-y-auto py-2">
            {(() => {
              const highCount = tickets.filter((t) => t.priority <= 1).length;
              const depCount = tickets.filter((t) => t.blocked_by_title).length;
              const stats: string[] = [];
              if (highCount > 0) stats.push(`${highCount} high priority`);
              if (depCount > 0) stats.push(`${depCount} with dependencies`);
              if (stats.length === 0) return null;
              return (
                <div className="mb-3 px-1">
                  <p className="text-xs text-gray-500">{stats.join(" · ")}</p>
                </div>
              );
            })()}
            <div className="space-y-2 px-1">
              {tickets.map((ticket) => (
                <TicketSummaryCard key={ticket.id} ticket={ticket} />
              ))}
            </div>
          </div>
        ) : (
          /* ── Progress Stream View ── */
          <div
            ref={scrollRef}
            className="flex-1 min-h-0 max-h-[500px] overflow-y-auto py-2 space-y-3"
          >
            {/* Phase indicator — single animated line */}
            <PhaseIndicator phase={currentPhase} />

            {/* AI reasoning feed */}
            <ReasoningFeed lines={reasoningLines} />

            {/* Research findings + per-ticket validation verdicts */}
            <ReviewsFeed reviews={reviews} />

            {/* Created tickets (shown inline during generation) */}
            {tickets.length > 0 && (
              <div className="space-y-1.5 pt-1">
                {tickets.map((ticket) => (
                  <div
                    key={ticket.id}
                    className="flex items-start gap-2 px-1 animate-in fade-in slide-in-from-bottom-1 duration-300"
                  >
                    <CheckCircle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0 text-green-500" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] text-green-500/70 font-medium">
                          P{ticket.priority}
                        </span>
                        <p className="text-xs text-gray-700 font-medium truncate">
                          {ticket.title}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Completion */}
            {isComplete && (
              <div className="flex items-center gap-2 px-1 pt-1">
                <CheckCircle className="h-4 w-4 text-green-600" />
                <p className="text-sm font-medium text-green-700">
                  Done — {ticketCount} ticket{ticketCount !== 1 ? "s" : ""}{" "}
                  created
                </p>
              </div>
            )}

            {/* Error */}
            {hasError && (
              <div className="flex items-start gap-2 px-1 pt-1">
                <XCircle className="h-4 w-4 mt-0.5 text-red-500" />
                <p className="text-sm text-red-700">{errorMessage}</p>
              </div>
            )}

            {/* Empty state */}
            {!currentPhase &&
              reasoningLines.length === 0 &&
              !isComplete &&
              !hasError && (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-3">
                  <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
                  <span className="text-sm text-gray-500">Starting...</span>
                </div>
              )}

            {/* Collapsible raw agent output */}
            {hasRawContent && (
              <div className="pt-2 border-t border-gray-100">
                <button
                  onClick={() => setShowRawDetails(!showRawDetails)}
                  className="flex items-center gap-1.5 text-[11px] text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <Eye className="h-3 w-3" />
                  {showRawDetails ? "Hide raw output" : "Show raw output"}
                  {showRawDetails ? (
                    <ChevronDown className="h-3 w-3" />
                  ) : (
                    <ChevronRight className="h-3 w-3" />
                  )}
                </button>
                {showRawDetails && (
                  <div className="mt-2 space-y-1.5 max-h-[300px] overflow-y-auto">
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
                    {!hasNormalized &&
                      rawLines.map((line, idx) => (
                        <div
                          key={idx}
                          className="py-1 px-2.5 text-xs font-mono text-gray-600 whitespace-pre-wrap break-words"
                        >
                          {line}
                        </div>
                      ))}
                  </div>
                )}
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
