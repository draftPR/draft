import { useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { config } from "@/config";

interface TicketGenerationProgressProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  goalId: string;
  onComplete: () => void;
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

function AssistantEntry({ entry }: { entry: NormalizedEntry }) {
  return (
    <div className="py-1.5 px-2.5 rounded border-l-2 border-l-blue-400 bg-blue-50/30">
      <div className="flex items-start gap-2">
        <MessageSquare className="h-3.5 w-3.5 mt-0.5 flex-shrink-0 text-blue-400" />
        <div className="flex-1 min-w-0">
          <span className="text-[10px] font-medium text-blue-500 uppercase tracking-wider">
            Response
          </span>
          <p className="text-xs text-gray-700 whitespace-pre-wrap break-words mt-0.5 leading-relaxed">
            {entry.content}
          </p>
        </div>
      </div>
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

function NormalizedEntryView({ entry }: { entry: NormalizedEntry }) {
  switch (entry.entry_type) {
    case "thinking":
      return <ThinkingEntry entry={entry} />;
    case "tool_use":
      return <ToolEntry entry={entry} />;
    case "assistant_message":
      return <AssistantEntry entry={entry} />;
    default:
      return <SystemEntry entry={entry} />;
  }
}

export function TicketGenerationProgress({
  open,
  onOpenChange,
  goalId,
  onComplete,
}: TicketGenerationProgressProps) {
  const [normalizedEntries, setNormalizedEntries] = useState<
    Map<number, NormalizedEntry>
  >(new Map());
  const [rawLines, setRawLines] = useState<string[]>([]);
  const [tickets, setTickets] = useState<TicketInfo[]>([]);
  const [isComplete, setIsComplete] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [ticketCount, setTicketCount] = useState(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [normalizedEntries, rawLines, tickets]);

  // eslint-disable-next-line react-hooks/set-state-in-effect -- Reset is intentional on open transition
  useEffect(() => {
    if (!open) return;

    // Reset state at the start of a new stream
    setNormalizedEntries(new Map());
    setRawLines([]);
    setTickets([]);
    setIsComplete(false);
    setHasError(false);
    setErrorMessage(null);
    setTicketCount(0);

    const eventSource = new EventSource(
      `${config.backendBaseUrl}/goals/${goalId}/generate-tickets/stream`
    );

    eventSource.onmessage = (event) => {
      const data: StreamEvent = JSON.parse(event.data);

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
          timeoutRef.current = setTimeout(() => {
            onComplete();
            onOpenChange(false);
          }, 2500);
          break;

        case "error":
          setHasError(true);
          setErrorMessage(data.message || "An error occurred");
          timeoutRef.current = setTimeout(() => {
            onOpenChange(false);
          }, 4000);
          break;

        // "status" events are no longer shown as static steps
        default:
          break;
      }
    };

    eventSource.onerror = (error) => {
      console.error("SSE error:", error);
      setHasError(true);
      setErrorMessage("Connection lost. Please try again.");
      eventSource.close();
    };

    return () => {
      eventSource.close();
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [open, goalId, onComplete, onOpenChange]);

  const sortedEntries = Array.from(normalizedEntries.values()).sort(
    (a, b) => a.sequence - b.sequence
  );
  const hasNormalized = sortedEntries.length > 0;
  const hasContent = hasNormalized || rawLines.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[680px] max-h-[85vh] flex flex-col">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="flex items-center gap-2">
            {!isComplete && !hasError && (
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-500 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500"></span>
              </span>
            )}
            {isComplete && <CheckCircle className="h-5 w-5 text-green-600" />}
            {hasError && <XCircle className="h-5 w-5 text-red-600" />}
            {isComplete
              ? "Tickets Generated"
              : hasError
                ? "Generation Failed"
                : "Agent Generating Tickets"}
          </DialogTitle>
          <DialogDescription>
            {isComplete
              ? `Created ${ticketCount} ticket(s) successfully`
              : hasError
                ? errorMessage
                : "Watching the AI agent analyze your codebase and plan tickets..."}
          </DialogDescription>
        </DialogHeader>

        {/* Chain-of-thought stream */}
        <div
          ref={scrollRef}
          className="flex-1 min-h-0 max-h-[500px] overflow-y-auto space-y-1.5 py-2"
        >
          {/* Normalized entries (structured agent output) */}
          {hasNormalized &&
            sortedEntries.map((entry) => (
              <NormalizedEntryView key={entry.sequence} entry={entry} />
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
                  Generation complete — {ticketCount} ticket(s) created
                </p>
              </div>
            </div>
          )}

          {/* Error message */}
          {hasError && (
            <div className="py-2 px-2.5 rounded border-l-2 border-l-red-400 bg-red-50/70">
              <div className="flex items-start gap-2">
                <XCircle className="h-4 w-4 mt-0.5 text-red-500" />
                <p className="text-sm text-red-700">{errorMessage}</p>
              </div>
            </div>
          )}

          {/* Empty state */}
          {!hasContent && !isComplete && !hasError && (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-3">
              <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
              <span className="text-sm text-gray-500">
                Starting agent...
              </span>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
