import { useState, useEffect, useRef, useCallback } from "react";
import { fetchJobLogs } from "@/services/api";
import { cn } from "@/lib/utils";
import { Loader2, Terminal, ChevronDown, ChevronUp, Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

interface JobLogsViewerProps {
  jobId: string;
  ticketTitle: string;
  isRunning?: boolean;
  className?: string;
}

export function JobLogsViewer({
  jobId,
  ticketTitle,
  isRunning = false,
  className,
}: JobLogsViewerProps) {
  const [logs, setLogs] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const [copied, setCopied] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const logsContainerRef = useRef<HTMLDivElement>(null);

  const loadLogs = useCallback(async () => {
    try {
      const content = await fetchJobLogs(jobId);
      setLogs(content);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load logs";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  // Initial load
  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  // Auto-refresh for running jobs
  useEffect(() => {
    if (!isRunning) return;

    const interval = setInterval(() => {
      loadLogs();
    }, 2000);

    return () => clearInterval(interval);
  }, [isRunning, loadLogs]);

  // Auto-scroll to bottom when logs update
  useEffect(() => {
    if (autoScroll && logsEndRef.current && expanded) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, autoScroll, expanded]);

  // Detect manual scroll to disable auto-scroll
  const handleScroll = useCallback(() => {
    if (!logsContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = logsContainerRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    setAutoScroll(isAtBottom);
  }, []);

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

  const logLines = logs.split("\n");
  const lineCount = logLines.length;

  return (
    <div className={cn("rounded-lg border border-border overflow-hidden", className)}>
      {/* Header */}
      <div
        className={cn(
          "flex items-center justify-between px-3 py-2 cursor-pointer transition-colors",
          "bg-zinc-900 hover:bg-zinc-800",
          isRunning && "border-l-2 border-l-emerald-500"
        )}
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-zinc-400" />
          <span className="text-sm font-medium text-zinc-200 truncate max-w-[250px]">
            {ticketTitle}
          </span>
          {isRunning && (
            <span className="flex items-center gap-1 text-[10px] text-emerald-400 font-medium uppercase tracking-wide">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
              </span>
              Live
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-zinc-500">{lineCount} lines</span>
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-zinc-500" />
          ) : (
            <ChevronDown className="h-4 w-4 text-zinc-500" />
          )}
        </div>
      </div>

      {/* Logs content */}
      {expanded && (
        <div className="relative">
          {loading && !logs ? (
            <div className="flex items-center justify-center py-8 bg-zinc-950">
              <Loader2 className="h-5 w-5 animate-spin text-zinc-500" />
            </div>
          ) : error && !logs ? (
            <div className="flex items-center justify-center py-8 bg-zinc-950">
              <p className="text-sm text-zinc-500">{error}</p>
            </div>
          ) : (
            <>
              {/* Copy button */}
              <Button
                variant="ghost"
                size="sm"
                onClick={handleCopy}
                className="absolute top-2 right-2 h-7 px-2 bg-zinc-800/80 hover:bg-zinc-700 text-zinc-400 z-10"
              >
                {copied ? (
                  <Check className="h-3.5 w-3.5 text-emerald-400" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </Button>

              <div
                ref={logsContainerRef}
                onScroll={handleScroll}
                className={cn(
                  "bg-zinc-950 overflow-auto font-mono text-xs",
                  "max-h-[300px] min-h-[100px]"
                )}
              >
                <pre className="p-3 text-zinc-300 whitespace-pre-wrap break-words">
                  {logs || "No logs available yet..."}
                  <div ref={logsEndRef} />
                </pre>
              </div>

              {/* Auto-scroll indicator */}
              {isRunning && !autoScroll && (
                <button
                  onClick={() => {
                    setAutoScroll(true);
                    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
                  }}
                  className="absolute bottom-2 right-2 px-2 py-1 rounded bg-zinc-800 text-zinc-400 text-[10px] hover:bg-zinc-700 transition-colors"
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


