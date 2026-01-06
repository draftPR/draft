import { useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import {
  fetchEvidenceStdout,
  fetchEvidenceStderr,
} from "@/services/api";
import type { Evidence } from "@/types/api";
import {
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronRight,
  Terminal,
  Loader2,
} from "lucide-react";

interface EvidenceItemProps {
  evidence: Evidence;
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function EvidenceItem({ evidence }: EvidenceItemProps) {
  const [expanded, setExpanded] = useState(false);
  const [stdout, setStdout] = useState<string | null>(null);
  const [stderr, setStderr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"stdout" | "stderr">("stdout");

  const loadOutput = useCallback(async () => {
    if (stdout !== null || loading) return;

    setLoading(true);
    try {
      const [stdoutContent, stderrContent] = await Promise.all([
        fetchEvidenceStdout(evidence.id),
        fetchEvidenceStderr(evidence.id),
      ]);
      setStdout(stdoutContent);
      setStderr(stderrContent);
    } catch (err) {
      console.error("Failed to load evidence output:", err);
      setStdout("");
      setStderr("");
    } finally {
      setLoading(false);
    }
  }, [evidence.id, stdout, loading]);

  const handleToggle = () => {
    if (!expanded) {
      loadOutput();
    }
    setExpanded(!expanded);
  };

  return (
    <div
      className={cn(
        "border rounded-md overflow-hidden",
        evidence.succeeded
          ? "border-emerald-500/30 bg-emerald-500/5"
          : "border-red-500/30 bg-red-500/5"
      )}
    >
      {/* Header */}
      <button
        onClick={handleToggle}
        className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-black/5 transition-colors text-left"
      >
        <span className="text-muted-foreground">
          {expanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </span>

        {evidence.succeeded ? (
          <CheckCircle className="h-4 w-4 text-emerald-500 flex-shrink-0" />
        ) : (
          <XCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
        )}

        <code className="text-[12px] font-mono text-foreground truncate flex-1">
          {evidence.command}
        </code>

        <span
          className={cn(
            "text-[11px] font-medium px-1.5 py-0.5 rounded",
            evidence.exit_code === 0
              ? "bg-emerald-500/20 text-emerald-700"
              : "bg-red-500/20 text-red-700"
          )}
        >
          exit {evidence.exit_code}
        </span>

        <span className="text-[11px] text-muted-foreground flex-shrink-0">
          {formatDate(evidence.created_at)}
        </span>
      </button>

      {/* Expanded Content */}
      {expanded && (
        <div className="border-t border-border/50">
          {/* Tabs */}
          <div className="flex border-b border-border/50">
            <button
              onClick={() => setActiveTab("stdout")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium transition-colors",
                activeTab === "stdout"
                  ? "text-foreground bg-muted/50 border-b-2 border-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Terminal className="h-3 w-3" />
              stdout
            </button>
            <button
              onClick={() => setActiveTab("stderr")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium transition-colors",
                activeTab === "stderr"
                  ? "text-foreground bg-muted/50 border-b-2 border-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Terminal className="h-3 w-3" />
              stderr
            </button>
          </div>

          {/* Output Content */}
          <div className="p-3 bg-slate-950 max-h-[300px] overflow-auto">
            {loading ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <pre className="text-[11px] font-mono text-slate-300 whitespace-pre-wrap break-all">
                {activeTab === "stdout"
                  ? stdout || "(empty)"
                  : stderr || "(empty)"}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface EvidenceListProps {
  evidence: Evidence[];
}

export function EvidenceList({ evidence }: EvidenceListProps) {
  if (evidence.length === 0) {
    return (
      <p className="text-[13px] text-muted-foreground italic py-4">
        No verification evidence recorded
      </p>
    );
  }

  const successCount = evidence.filter((e) => e.succeeded).length;
  const failureCount = evidence.length - successCount;

  return (
    <div className="space-y-3">
      {/* Summary */}
      <div className="flex items-center gap-3 text-[12px]">
        <span className="text-muted-foreground">
          {evidence.length} command{evidence.length !== 1 ? "s" : ""} total
        </span>
        {successCount > 0 && (
          <span className="text-emerald-600 flex items-center gap-1">
            <CheckCircle className="h-3 w-3" />
            {successCount} passed
          </span>
        )}
        {failureCount > 0 && (
          <span className="text-red-600 flex items-center gap-1">
            <XCircle className="h-3 w-3" />
            {failureCount} failed
          </span>
        )}
      </div>

      {/* Evidence Items */}
      <div className="space-y-2">
        {evidence.map((e) => (
          <EvidenceItem key={e.id} evidence={e} />
        ))}
      </div>
    </div>
  );
}

