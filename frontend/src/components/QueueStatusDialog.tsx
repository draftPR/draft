import { useState, useEffect, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { fetchQueueStatus, cancelJob } from "@/services/api";
import type { QueueStatusResponse, QueuedJob } from "@/types/api";
import { JobLogsViewer } from "@/components/JobLogsViewer";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  Loader2,
  AlertCircle,
  ListOrdered,
  Play,
  Clock,
  RefreshCw,
  Zap,
  Timer,
  Square,
  FileText,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

interface QueueStatusDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);

  if (diffSecs < 60) return `${diffSecs}s ago`;
  const diffMins = Math.floor(diffSecs / 60);
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return date.toLocaleDateString();
}

function JobKindBadge({ kind }: { kind: string }) {
  const colors: Record<string, string> = {
    execute: "bg-blue-500/15 text-blue-600 border-blue-500/30",
    verify: "bg-purple-500/15 text-purple-600 border-purple-500/30",
    resume: "bg-amber-500/15 text-amber-600 border-amber-500/30",
  };

  return (
    <Badge
      variant="outline"
      className={cn("text-[10px] px-1.5 py-0", colors[kind] || "")}
    >
      {kind}
    </Badge>
  );
}

interface JobCardProps {
  job: QueuedJob;
  isRunning: boolean;
  onCancel: (jobId: string) => void;
  cancelingId: string | null;
  showLogs: boolean;
  onToggleLogs: () => void;
}

function JobCard({
  job,
  isRunning,
  onCancel,
  cancelingId,
  showLogs,
  onToggleLogs,
}: JobCardProps) {
  const isCanceling = cancelingId === job.id;

  return (
    <div className="space-y-2">
      <div
        className={cn(
          "p-3 rounded-lg border transition-colors",
          isRunning
            ? "bg-emerald-500/5 border-emerald-500/30"
            : "bg-muted/30 border-border hover:bg-muted/50"
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              {isRunning ? (
                <div className="flex items-center gap-1.5 text-emerald-600">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                  <span className="text-[10px] font-medium uppercase tracking-wide">
                    Running
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  <span className="text-[10px] font-medium uppercase tracking-wide">
                    #{job.queue_position}
                  </span>
                </div>
              )}
              <JobKindBadge kind={job.kind} />
            </div>
            <h4 className="text-sm font-medium truncate" title={job.ticket_title}>
              {job.ticket_title}
            </h4>
            <div className="flex items-center gap-3 mt-1.5 text-[10px] text-muted-foreground">
              <span className="font-mono" title={job.ticket_id}>
                {job.ticket_id.slice(0, 8)}...
              </span>
              <span className="flex items-center gap-1">
                <Timer className="h-3 w-3" />
                {isRunning && job.started_at
                  ? `started ${formatRelativeTime(job.started_at)}`
                  : `queued ${formatRelativeTime(job.created_at)}`}
              </span>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-1.5 flex-shrink-0">
            {isRunning && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onToggleLogs}
                className={cn(
                  "h-7 px-2 text-xs",
                  showLogs && "bg-accent"
                )}
                title="View logs"
              >
                <FileText className="h-3.5 w-3.5 mr-1" />
                Logs
                {showLogs ? (
                  <ChevronUp className="h-3 w-3 ml-1" />
                ) : (
                  <ChevronDown className="h-3 w-3 ml-1" />
                )}
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onCancel(job.id)}
              disabled={isCanceling}
              className={cn(
                "h-7 px-2 text-xs",
                "text-red-600 hover:text-red-700 hover:bg-red-100",
                "dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-900/30"
              )}
              title={isRunning ? "Stop job" : "Cancel job"}
            >
              {isCanceling ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Square className="h-3.5 w-3.5" />
              )}
              <span className="ml-1">{isRunning ? "Stop" : "Cancel"}</span>
            </Button>
          </div>
        </div>
      </div>

      {/* Inline logs viewer for running jobs */}
      {isRunning && showLogs && (
        <JobLogsViewer
          jobId={job.id}
          ticketTitle={job.ticket_title}
          isRunning={true}
          className="ml-2"
        />
      )}
    </div>
  );
}

export function QueueStatusDialog({
  open,
  onOpenChange,
}: QueueStatusDialogProps) {
  const [status, setStatus] = useState<QueueStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cancelingId, setCancelingId] = useState<string | null>(null);
  const [expandedLogs, setExpandedLogs] = useState<Set<string>>(new Set());

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchQueueStatus();
      setStatus(response);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load queue status";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      loadStatus();
    }
  }, [open, loadStatus]);

  // Auto-refresh while dialog is open
  useEffect(() => {
    if (!open) return;

    const interval = setInterval(() => {
      loadStatus();
    }, 3000);

    return () => clearInterval(interval);
  }, [open, loadStatus]);

  const handleCancel = useCallback(async (jobId: string) => {
    setCancelingId(jobId);
    try {
      const result = await cancelJob(jobId);
      toast.success(result.message);
      // Refresh status after cancel
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to cancel job";
      toast.error(message);
    } finally {
      setCancelingId(null);
    }
  }, [loadStatus]);

  const toggleLogs = useCallback((jobId: string) => {
    setExpandedLogs((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) {
        next.delete(jobId);
      } else {
        next.add(jobId);
      }
      return next;
    });
  }, []);

  const isEmpty =
    status && status.total_running === 0 && status.total_queued === 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ListOrdered className="h-5 w-5" />
            Activity Monitor
          </DialogTitle>
          <DialogDescription>
            View running jobs, queue status, and live logs. Stop jobs if needed.
          </DialogDescription>
        </DialogHeader>

        <div className="mt-2 flex-1 min-h-0 overflow-hidden flex flex-col">
          {loading && !status ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <AlertCircle className="h-8 w-8 text-destructive" />
              <p className="text-sm text-destructive">{error}</p>
              <Button variant="outline" size="sm" onClick={loadStatus}>
                Try Again
              </Button>
            </div>
          ) : isEmpty ? (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <Zap className="h-10 w-10 text-muted-foreground/50" />
              <div>
                <p className="text-sm font-medium">Queue is empty</p>
                <p className="text-xs text-muted-foreground mt-1">
                  No jobs are currently running or waiting
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-4 flex-1 overflow-y-auto pr-2">
              {/* Running Jobs */}
              {status && status.running.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Play className="h-4 w-4 text-emerald-600" />
                    <h3 className="text-sm font-medium">
                      Running ({status.total_running})
                    </h3>
                  </div>
                  <div className="space-y-2">
                    {status.running.map((job) => (
                      <JobCard
                        key={job.id}
                        job={job}
                        isRunning
                        onCancel={handleCancel}
                        cancelingId={cancelingId}
                        showLogs={expandedLogs.has(job.id)}
                        onToggleLogs={() => toggleLogs(job.id)}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Queued Jobs */}
              {status && status.queued.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Clock className="h-4 w-4 text-muted-foreground" />
                    <h3 className="text-sm font-medium">
                      Queued ({status.total_queued})
                    </h3>
                  </div>
                  <div className="space-y-2">
                    {status.queued.map((job) => (
                      <JobCard
                        key={job.id}
                        job={job}
                        isRunning={false}
                        onCancel={handleCancel}
                        cancelingId={cancelingId}
                        showLogs={false}
                        onToggleLogs={() => {}}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Footer with refresh button */}
          {status && !isEmpty && (
            <div className="flex items-center justify-between mt-4 pt-3 border-t flex-shrink-0">
              <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
                </span>
                Auto-refreshing every 3s
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={loadStatus}
                disabled={loading}
                className="h-7 text-xs"
              >
                <RefreshCw
                  className={cn("h-3 w-3 mr-1", loading && "animate-spin")}
                />
                Refresh
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
