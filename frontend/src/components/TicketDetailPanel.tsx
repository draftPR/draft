/**
 * TicketDetailPanel -- standalone ticket detail view for resizable panel layout.
 *
 * Fetches the full ticket and renders the same content as the Sheet drawer,
 * but without the Sheet wrapper.
 */

import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { EvidenceList } from "@/components/EvidenceList";
import { EmptyState } from "@/components/EmptyState";
import { TicketDetailSkeleton } from "@/components/skeletons/TicketDetailSkeleton";
import { AgentActivityLog } from "@/components/AgentActivityLog";
import { BlockingIndicator } from "@/components/BlockingIndicator";
import {
  fetchTicketEvents,
  fetchTicketEvidence,
  fetchTicketRevisions,
  fetchMergeStatus,
  mergeTicket,
  fetchTicketJobs,
  fetchTicketDependents,
  fetchTicket,
} from "@/services/api";
import type {
  Ticket,
  TicketEvent,
  Evidence,
  Revision,
  MergeStatusResponse,
  Job,
} from "@/types/api";
import {
  STATE_DISPLAY_NAMES,
  EventType,
  TicketState,
  MergeStrategy,
  JobStatus,
} from "@/types/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
  ArrowRight,
  AlertCircle,
  FlaskConical,
  GitPullRequest,
  GitMerge,
  FolderGit,
  Check,
  X as XIcon,
  Activity,
  GitBranch,
  Lock,
  Loader2,
} from "lucide-react";
import { CreatePRButton } from "@/components/PullRequest/CreatePRButton";
import { PRStatusBadge } from "@/components/PullRequest/PRStatusBadge";
import { useTicketSelectionStore } from "@/stores/ticketStore";

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getPriorityDisplay(priority: number | null): { label: string; color: string } {
  if (priority === null) return { label: "Not set", color: "text-muted-foreground" };
  if (priority >= 75) return { label: `${priority} (High)`, color: "text-red-500" };
  if (priority >= 50) return { label: `${priority} (Medium)`, color: "text-amber-500" };
  if (priority >= 25) return { label: `${priority} (Low)`, color: "text-yellow-600" };
  return { label: `${priority} (Lowest)`, color: "text-emerald-500" };
}

export function TicketDetailPanel() {
  const { selectedTicketId, clearSelection, selectTicket } = useTicketSelectionStore();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [dependents, setDependents] = useState<Ticket[]>([]);
  const [mergeStatus, setMergeStatus] = useState<MergeStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [evidenceLoading] = useState(false);
  const [mergeLoading, setMergeLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async (ticketId: string) => {
    setLoading(true);
    setError(null);
    try {
      const [t, evts, evi, revs, sts, jbs, deps] = await Promise.all([
        fetchTicket(ticketId),
        fetchTicketEvents(ticketId).catch(() => ({ events: [] })),
        fetchTicketEvidence(ticketId).catch(() => ({ evidence: [] })),
        fetchTicketRevisions(ticketId).catch(() => ({ revisions: [] })),
        fetchMergeStatus(ticketId).catch(() => null),
        fetchTicketJobs(ticketId).catch(() => ({ jobs: [] })),
        fetchTicketDependents(ticketId).catch(() => []),
      ]);
      setTicket(t);
      setEvents(evts.events);
      setEvidence(evi.evidence);
      setRevisions(revs.revisions);
      setMergeStatus(sts);
      setJobs(jbs.jobs);
      setDependents(deps);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load ticket");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedTicketId) {
      loadAll(selectedTicketId);
    }
  }, [selectedTicketId, loadAll]);

  // Auto-refresh jobs when running
  const hasRunningJob = jobs.some(j => j.status === JobStatus.RUNNING || j.status === JobStatus.QUEUED);
  useEffect(() => {
    if (!hasRunningJob || !selectedTicketId) return;
    const interval = setInterval(() => {
      fetchTicketJobs(selectedTicketId).then(r => setJobs(r.jobs)).catch(() => {});
    }, 5000);
    return () => clearInterval(interval);
  }, [hasRunningJob, selectedTicketId]);

  const handleMerge = useCallback(async () => {
    if (!ticket) return;
    setMergeLoading(true);
    try {
      const result = await mergeTicket(ticket.id, {
        strategy: MergeStrategy.MERGE,
        delete_worktree: true,
        cleanup_artifacts: true,
      });
      if (result.success) {
        toast.success(result.pull_warning ? "Merge successful (with warning)" : "Merge successful!", {
          description: result.pull_warning || result.message,
        });
        loadAll(ticket.id);
      } else {
        toast.error("Merge failed", { description: result.message });
      }
    } catch (err) {
      toast.error("Merge failed", { description: err instanceof Error ? err.message : "Unknown error" });
    } finally {
      setMergeLoading(false);
    }
  }, [ticket, loadAll]);

  const handleNavigateToTicket = useCallback((ticketId: string) => {
    selectTicket(ticketId);
  }, [selectTicket]);

  if (!selectedTicketId) return null;

  if (loading && !ticket) {
    return (
      <div className="h-full overflow-y-auto p-6">
        <TicketDetailSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center p-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <AlertCircle className="h-6 w-6 text-destructive" />
          <p className="text-sm text-destructive">{error}</p>
        </div>
      </div>
    );
  }

  if (!ticket) return null;

  const priority = getPriorityDisplay(ticket.priority);
  const canShowRevisions = ticket && (
    ticket.state === TicketState.NEEDS_HUMAN ||
    ticket.state === TicketState.DONE ||
    ticket.state === TicketState.VERIFYING
  );

  return (
    <div className="h-full overflow-y-auto border-l border-border bg-background">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-background border-b border-border/40 px-6 py-4">
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-[15px] leading-relaxed font-semibold text-foreground pr-4">
            {ticket.title}
          </h2>
          <Button variant="ghost" size="sm" className="h-7 w-7 p-0 flex-shrink-0" onClick={clearSelection}>
            <XIcon className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex items-center gap-3 mt-3">
          <PRStatusBadge ticket={ticket} onRefresh={() => loadAll(ticket.id)} />
          <CreatePRButton ticket={ticket} onPRCreated={() => loadAll(ticket.id)} />
        </div>
      </div>

      {/* Content */}
      <div className="px-6 py-6 space-y-10">
        {/* Description */}
        <div className="space-y-3">
          <h3 className="section-label">Description</h3>
          <p className="text-[13px] leading-relaxed text-foreground">
            {ticket.description || (
              <span className="text-muted-foreground italic">No description provided</span>
            )}
          </p>
        </div>

        {/* State & Priority */}
        <div className="grid grid-cols-2 gap-8">
          <div className="space-y-3">
            <h3 className="section-label">State</h3>
            <p className="text-[13px] text-foreground">{STATE_DISPLAY_NAMES[ticket.state]}</p>
          </div>
          <div className="space-y-3">
            <h3 className="section-label">Priority</h3>
            <p className={cn("text-[13px] font-medium", priority.color)}>{priority.label}</p>
          </div>
        </div>

        {/* Dependencies */}
        {(ticket.blocked_by_ticket_id || dependents.length > 0) && (
          <div className="space-y-4">
            <h3 className="section-label flex items-center gap-2">
              <GitBranch className="h-3.5 w-3.5" />
              Dependencies
            </h3>
            {ticket.blocked_by_ticket_id && (
              <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-3 space-y-2">
                <BlockingIndicator
                  blockedByTicketId={ticket.blocked_by_ticket_id}
                  blockedByTicketTitle={ticket.blocked_by_ticket_title}
                  onNavigateToBlocker={handleNavigateToTicket}
                />
              </div>
            )}
            {dependents.length > 0 && (
              <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 space-y-1.5">
                {dependents.map((dep) => (
                  <button
                    key={dep.id}
                    className="w-full text-left text-[12px] flex items-center gap-2 p-2 rounded hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
                    onClick={() => handleNavigateToTicket(dep.id)}
                  >
                    <Lock className="h-3 w-3 flex-shrink-0 text-blue-600 dark:text-blue-400" />
                    <span className="flex-1 truncate text-foreground">{dep.title}</span>
                    <span className="text-[10px] text-muted-foreground">{STATE_DISPLAY_NAMES[dep.state]}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Code Changes */}
        {canShowRevisions && (
          <div className="space-y-4">
            <h3 className="section-label flex items-center gap-2">
              <GitPullRequest className="h-3.5 w-3.5" />
              Code Changes
            </h3>
            {revisions.length > 0 ? (
              <p className="text-[13px] text-muted-foreground">
                {revisions.length} revision{revisions.length !== 1 ? "s" : ""} available.
              </p>
            ) : (
              <EmptyState icon={GitPullRequest} title="No revisions yet" compact />
            )}
          </div>
        )}

        {/* Worktree & Merge */}
        {mergeStatus && (
          <div className="space-y-4">
            <h3 className="section-label flex items-center gap-2">
              <FolderGit className="h-3.5 w-3.5" />
              Worktree & Merge
            </h3>
            {mergeStatus.is_merged ? (
              <div className="flex items-center gap-2 text-emerald-500">
                <Check className="h-4 w-4" />
                <span className="text-[13px] font-medium">Merged to main</span>
              </div>
            ) : mergeStatus.workspace ? (
              <div className="space-y-3">
                <div className="bg-muted/50 rounded-lg p-3 space-y-2">
                  <div className="flex items-start gap-2">
                    <span className="text-[11px] text-muted-foreground min-w-[60px]">Branch:</span>
                    <code className="text-[12px] text-foreground font-mono">{String(mergeStatus.workspace.branch_name ?? "")}</code>
                  </div>
                </div>
                {mergeStatus.can_merge && (
                  <Button onClick={handleMerge} disabled={mergeLoading} className="w-full" variant="default">
                    {mergeLoading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <GitMerge className="h-4 w-4 mr-2" />}
                    Merge to Main
                  </Button>
                )}
              </div>
            ) : (
              <EmptyState icon={FolderGit} title="No active worktree" compact />
            )}
          </div>
        )}

        {/* Agent Activity */}
        <div className="space-y-4">
          <h3 className="section-label flex items-center gap-2">
            <Activity className="h-3.5 w-3.5" />
            Agent Activity
            {jobs.some(j => j.status === JobStatus.RUNNING) && (
              <span className="flex items-center gap-1 text-[10px] text-emerald-400 font-medium uppercase tracking-wide">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
                </span>
                Live
              </span>
            )}
          </h3>
          <AgentActivityLog ticketId={ticket.id} />
        </div>

        {/* Evidence */}
        <div className="space-y-4">
          <h3 className="section-label flex items-center gap-2">
            <FlaskConical className="h-3.5 w-3.5" />
            Verification Evidence
          </h3>
          {evidenceLoading ? (
            <TicketDetailSkeleton />
          ) : (
            <EvidenceList evidence={evidence} />
          )}
        </div>

        {/* Event History */}
        <div className="space-y-4">
          <h3 className="section-label">Event History</h3>
          {events.length === 0 ? (
            <EmptyState icon={Activity} title="No events recorded" compact />
          ) : (
            <div className="space-y-4">
              {events.map((event) => (
                <div key={event.id} className="border-l-2 border-border/50 pl-4 py-2 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-medium capitalize text-foreground">{event.event_type}</span>
                    <span className="text-[12px] text-muted-foreground">{formatDate(event.created_at)}</span>
                  </div>
                  {event.event_type === EventType.TRANSITIONED && event.from_state && event.to_state && (
                    <div className="flex items-center gap-2 text-[13px]">
                      <span className="text-muted-foreground">{STATE_DISPLAY_NAMES[event.from_state]}</span>
                      <ArrowRight className="h-3 w-3 text-muted-foreground/60" />
                      <span className="text-foreground font-medium">{STATE_DISPLAY_NAMES[event.to_state]}</span>
                    </div>
                  )}
                  {event.reason && (
                    <p className="text-[13px] text-muted-foreground leading-relaxed">{event.reason}</p>
                  )}
                  <p className="text-[12px] text-muted-foreground/80">
                    by {event.actor_type}
                    {event.actor_id && ` (${event.actor_id})`}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
