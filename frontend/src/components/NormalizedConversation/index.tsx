/**
 * Main component for displaying normalized conversation logs
 */

import { useState, useEffect } from "react";
import { ChevronDown, ChevronUp, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { NormalizedLogEntry } from "@/types/logs";
import { getNormalizedLogs, normalizeJobLogs } from "@/services/api";
import { JobStatus } from "@/types/api";
import { DisplayConversationEntry } from "./DisplayConversationEntry";
import { toast } from "sonner";

interface Props {
  jobId: string;
  jobStatus: JobStatus;
  defaultExpanded?: boolean;
  className?: string;
}

export function NormalizedConversation({ 
  jobId, 
  jobStatus,
  defaultExpanded = false,
  className 
}: Props) {
  const [entries, setEntries] = useState<NormalizedLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [normalizing, setNormalizing] = useState(false);

  const statusBadge = {
    queued: { color: "bg-slate-500", label: "Queued" },
    running: { color: "bg-blue-500", label: "Running" },
    succeeded: { color: "bg-emerald-500", label: "Succeeded" },
    failed: { color: "bg-red-500", label: "Failed" },
    canceled: { color: "bg-orange-500", label: "Canceled" },
  };

  const badge = statusBadge[jobStatus] || statusBadge.queued;

  useEffect(() => {
    loadLogs();
  }, [jobId]);

  async function loadLogs() {
    try {
      setLoading(true);
      const logs = await getNormalizedLogs(jobId);
      setEntries(logs);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load logs");
    } finally {
      setLoading(false);
    }
  }

  async function handleNormalize() {
    setNormalizing(true);
    try {
      await normalizeJobLogs(jobId, "claude");
      toast.success("Logs normalized successfully");
      await loadLogs();
    } catch (err) {
      toast.error("Failed to normalize logs: " + (err instanceof Error ? err.message : "Unknown error"));
    } finally {
      setNormalizing(false);
    }
  }

  return (
    <div className={cn("border rounded-lg overflow-hidden bg-card", className)}>
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-2 flex items-center justify-between hover:bg-accent/50 transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <div className={cn("w-2 h-2 rounded-full", badge.color)} />
          <span className="text-sm font-medium text-foreground">
            {badge.label}
          </span>
          <span className="text-xs text-muted-foreground font-mono">
            {jobId.slice(0, 8)}
          </span>
          {entries.length > 0 && (
            <span className="text-xs text-muted-foreground">
              • {entries.length} entries
            </span>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          {entries.length === 0 && !loading && (
            <Button
              size="sm"
              variant="outline"
              onClick={(e) => {
                e.stopPropagation();
                handleNormalize();
              }}
              disabled={normalizing}
              className="h-6 text-xs"
            >
              {normalizing ? (
                <>
                  <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                  Normalizing...
                </>
              ) : (
                <>
                  <Sparkles className="w-3 h-3 mr-1" />
                  Normalize
                </>
              )}
            </Button>
          )}
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </button>

      {/* Content */}
      {expanded && (
        <div className="border-t bg-background">
          {loading ? (
            <div className="p-6 flex items-center justify-center text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              Loading normalized logs...
            </div>
          ) : error ? (
            <div className="p-6 text-center">
              <p className="text-destructive mb-2">Error loading logs</p>
              <p className="text-sm text-muted-foreground">{error}</p>
            </div>
          ) : entries.length === 0 ? (
            <div className="p-6 text-center">
              <p className="text-muted-foreground mb-3">
                No normalized logs available yet
              </p>
              <Button
                size="sm"
                onClick={handleNormalize}
                disabled={normalizing}
              >
                {normalizing ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Normalizing...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4 mr-2" />
                    Normalize Logs
                  </>
                )}
              </Button>
            </div>
          ) : (
            <div className="divide-y">
              {entries.map((entry) => (
                <DisplayConversationEntry
                  key={entry.id}
                  entry={entry}
                  expansionKey={`${jobId}-${entry.id}`}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
