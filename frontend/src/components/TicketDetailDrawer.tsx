import { useEffect, useState, useCallback } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EvidenceList } from "@/components/EvidenceList";
import { RevisionViewer } from "@/components/RevisionViewer";
import { TicketDAGView } from "@/components/TicketDAGView";
import { Button } from "@/components/ui/button";
import {
  fetchTicketEvents,
  fetchTicketEvidence,
  fetchTicketRevisions,
  fetchMergeStatus,
  mergeTicket,
  fetchTicketJobs,
  retryJob,
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
  Loader2,
  AlertCircle,
  AlertTriangle,
  FlaskConical,
  GitPullRequest,
  ExternalLink,
  GitMerge,
  FolderGit,
  RefreshCw,
  Check,
  X,
  Activity,
  GitBranch,
  Lock,
} from "lucide-react";
import { CreatePRButton } from "@/components/PullRequest/CreatePRButton";
import { PRStatusBadge } from "@/components/PullRequest/PRStatusBadge";
import { AgentActivityLog } from "@/components/AgentActivityLog";
import { BlockingIndicator } from "@/components/BlockingIndicator";
import { EmptyState } from "@/components/EmptyState";
import { TicketDetailSkeleton } from "@/components/skeletons/TicketDetailSkeleton";

interface TicketDetailDrawerProps {
  ticket: Ticket | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onNavigateToTicket?: (ticketId: string) => void;
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

function getPriorityDisplay(priority: number | null): { label: string; color: string } {
  if (priority === null) return { label: "Not set", color: "text-muted-foreground" };
  if (priority >= 75) return { label: `${priority} (High)`, color: "text-red-500" };
  if (priority >= 50) return { label: `${priority} (Medium)`, color: "text-amber-500" };
  if (priority >= 25) return { label: `${priority} (Low)`, color: "text-yellow-600" };
  return { label: `${priority} (Lowest)`, color: "text-emerald-500" };
}

export function TicketDetailDrawer({
  ticket,
  open,
  onOpenChange,
  onNavigateToTicket,
}: TicketDetailDrawerProps) {
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [dependents, setDependents] = useState<Ticket[]>([]);
  const [mergeStatus, setMergeStatus] = useState<MergeStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [revisionsLoading, setRevisionsLoading] = useState(false);
  const [mergeLoading, setMergeLoading] = useState(false);
  const [dependentsLoading, setDependentsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showRevisionViewer, setShowRevisionViewer] = useState(false);
  const [showDAGView, setShowDAGView] = useState(false);

  const loadEvents = useCallback(async (ticketId: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchTicketEvents(ticketId);
      setEvents(response.events);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load events");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadEvidence = useCallback(async (ticketId: string) => {
    setEvidenceLoading(true);
    try {
      const response = await fetchTicketEvidence(ticketId);
      setEvidence(response.evidence);
    } catch (err) {
      console.error("Failed to load evidence:", err);
      setEvidence([]);
    } finally {
      setEvidenceLoading(false);
    }
  }, []);

  const loadRevisions = useCallback(async (ticketId: string) => {
    setRevisionsLoading(true);
    try {
      const response = await fetchTicketRevisions(ticketId);
      setRevisions(response.revisions);
    } catch (err) {
      console.error("Failed to load revisions:", err);
      setRevisions([]);
    } finally {
      setRevisionsLoading(false);
    }
  }, []);

  const loadMergeStatus = useCallback(async (ticketId: string) => {
    try {
      const status = await fetchMergeStatus(ticketId);
      setMergeStatus(status);
    } catch (err) {
      console.error("Failed to load merge status:", err);
      setMergeStatus(null);
    }
  }, []);

  const loadJobs = useCallback(async (ticketId: string) => {
    try {
      const response = await fetchTicketJobs(ticketId);
      setJobs(response.jobs);
    } catch (err) {
      console.error("Failed to load jobs:", err);
      setJobs([]);
    }
  }, []);

  const loadDependents = useCallback(async (ticketId: string) => {
    setDependentsLoading(true);
    try {
      const tickets = await fetchTicketDependents(ticketId);
      setDependents(tickets);
    } catch (err) {
      console.error("Failed to load dependents:", err);
      setDependents([]);
      // Only show toast for non-404 errors (404 means no dependents, which is fine)
      if (err instanceof Error && !err.message.includes('404')) {
        toast.error("Failed to load dependent tickets", {
          description: err.message || "Unable to fetch tickets that depend on this one",
        });
      }
    } finally {
      setDependentsLoading(false);
    }
  }, []);

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
        // Show success with warning if local-only merge
        if (result.pull_warning) {
          toast.warning("Merge successful (with warning)", {
            description: result.pull_warning,
          });
        } else {
          toast.success("Merge successful!", {
            description: result.message,
          });
        }
        // Reload merge status
        loadMergeStatus(ticket.id);
        loadEvents(ticket.id);
      } else {
        toast.error("Merge failed", {
          description: result.message,
        });
      }
    } catch (err) {
      toast.error("Merge failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setMergeLoading(false);
    }
  }, [ticket, loadMergeStatus, loadEvents]);

  const handleRetryJob = useCallback(async (jobId: string) => {
    try {
      const newJob = await retryJob(jobId);
      toast.success("Job retry queued", {
        description: `New job ${newJob.id} created`,
      });
      if (ticket) {
        loadJobs(ticket.id);
      }
    } catch (err) {
      toast.error("Failed to retry job", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }, [ticket, loadJobs]);

  const handleRevisionUpdated = useCallback(() => {
    if (ticket) {
      loadRevisions(ticket.id);
      loadEvidence(ticket.id);
      loadEvents(ticket.id);
    }
  }, [ticket, loadRevisions, loadEvidence, loadEvents]);

  const handleRefresh = useCallback(() => {
    if (ticket) {
      loadEvents(ticket.id);
      loadMergeStatus(ticket.id);
    }
  }, [ticket, loadEvents, loadMergeStatus]);

  const handleNavigateToTicket = useCallback(async (ticketId: string) => {
    try {
      const targetTicket = await fetchTicket(ticketId);
      // This will trigger the useEffect to reload all data for the new ticket
      // We need to update the parent component's selectedTicket state
      // For now, we'll reload the current drawer content
      // Note: Ideally, the parent (KanbanBoard) should handle this via a callback
      // But we can fake it by reloading everything for the new ticket
      if (open) {
        loadEvents(targetTicket.id);
        loadEvidence(targetTicket.id);
        loadRevisions(targetTicket.id);
        loadMergeStatus(targetTicket.id);
        loadJobs(targetTicket.id);
        loadDependents(targetTicket.id);
      }
    } catch (err) {
      toast.error("Failed to load ticket", {
        description: err instanceof Error ? err.message : "Unknown error"
      });
    }
  }, [open, loadEvents, loadEvidence, loadRevisions, loadMergeStatus, loadJobs, loadDependents]);

  useEffect(() => {
    if (ticket && open) {
      loadEvents(ticket.id);
      loadEvidence(ticket.id);
      loadRevisions(ticket.id);
      loadMergeStatus(ticket.id);
      loadJobs(ticket.id);
      loadDependents(ticket.id);
      setShowRevisionViewer(false); // Reset when opening a new ticket
    }
    // Only re-fetch when ticket ID changes or drawer opens, not on ticket object reference changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticket?.id, open, loadEvents, loadEvidence, loadRevisions, loadMergeStatus, loadJobs, loadDependents]);

  // Auto-refresh jobs when there's a running job (to update status)
  const hasRunningJob = jobs.some(j => j.status === JobStatus.RUNNING || j.status === JobStatus.QUEUED);
  useEffect(() => {
    if (!hasRunningJob || !ticket || !open) return;

    const interval = setInterval(() => {
      loadJobs(ticket.id);
    }, 5000); // Refresh every 5 seconds

    return () => clearInterval(interval);
  }, [hasRunningJob, ticket, open, loadJobs]);

  // Check if ticket can show revision viewer
  const canShowRevisions = ticket && (
    ticket.state === TicketState.NEEDS_HUMAN ||
    ticket.state === TicketState.DONE ||
    ticket.state === TicketState.VERIFYING
  );

  if (!ticket) return null;

  const priority = getPriorityDisplay(ticket.priority);

  // If showing revision viewer, render it in full screen mode
  if (showRevisionViewer && revisions.length > 0) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent className="w-[95vw] max-w-none p-0 overflow-hidden bg-background sm:max-w-none">
          <SheetDescription className="sr-only">
            Review changes for this ticket
          </SheetDescription>
          <RevisionViewer
            ticketId={ticket.id}
            ticketTitle={ticket.title}
            revisions={revisions}
            onRevisionUpdated={handleRevisionUpdated}
            onClose={() => setShowRevisionViewer(false)}
          />
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <>
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[25%] min-w-[500px] overflow-y-auto bg-background pl-8">
        <SheetHeader className="pb-8 border-b border-border/40">
          <SheetTitle className="text-[15px] leading-relaxed pr-8 font-semibold text-foreground">
            {ticket.title}
          </SheetTitle>
          <SheetDescription className="sr-only">
            Ticket details and event history
          </SheetDescription>
          
          {/* GitHub PR Actions */}
          <div className="flex items-center gap-3 pt-4">
            <PRStatusBadge ticket={ticket} onRefresh={handleRefresh} />
            <CreatePRButton ticket={ticket} onPRCreated={handleRefresh} />
          </div>
        </SheetHeader>

        <div className="mt-8 space-y-10">
          {/* Description Section */}
          <div className="space-y-3">
            <h3 className="section-label">
              Description
            </h3>
            <p className="text-[13px] leading-relaxed text-foreground">
              {ticket.description || (
                <span className="text-muted-foreground italic">
                  No description provided
                </span>
              )}
            </p>
          </div>

          {/* State and Priority Section */}
          <div className="grid grid-cols-2 gap-8">
            <div className="space-y-3">
              <h3 className="section-label">
                State
              </h3>
              <p className="text-[13px] text-foreground">
                {STATE_DISPLAY_NAMES[ticket.state]}
              </p>
            </div>
            <div className="space-y-3">
              <h3 className="section-label">
                Priority
              </h3>
              <p className={cn("text-[13px] font-medium", priority.color)}>
                {priority.label}
              </p>
            </div>
          </div>

          {/* Dependencies Section */}
          {(ticket.blocked_by_ticket_id || dependents.length > 0) && (
            <div className="space-y-4">
              <h3 className="section-label flex items-center gap-2">
                <GitBranch className="h-3.5 w-3.5" />
                Dependencies
              </h3>

              {/* Upstream blocker */}
              {ticket.blocked_by_ticket_id && (
                <div className="space-y-2">
                  <p className="text-[11px] text-muted-foreground/80 tracking-wide uppercase">
                    ⬆️ Blocked by
                  </p>
                  <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-3 space-y-2">
                    <BlockingIndicator
                      blockedByTicketId={ticket.blocked_by_ticket_id}
                      blockedByTicketTitle={ticket.blocked_by_ticket_title}
                      onNavigateToBlocker={onNavigateToTicket}
                    />
                    <p className="text-[10px] text-amber-700 dark:text-amber-400/80 leading-relaxed">
                      ⚠️ This ticket cannot be executed until the blocker is marked as DONE.
                    </p>
                  </div>
                </div>
              )}

              {/* Downstream dependents */}
              {dependents.length > 0 && (
                <div className="space-y-2">
                  <p className="text-[11px] text-muted-foreground/80 tracking-wide uppercase">
                    ⬇️ Blocking {dependents.length} ticket{dependents.length !== 1 ? "s" : ""}
                  </p>
                  <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3">
                    {dependentsLoading ? (
                      <div className="flex items-center justify-center py-4">
                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                      </div>
                    ) : (
                      <div className="space-y-1.5">
                        {dependents.map((dep) => (
                          <button
                            key={dep.id}
                            className="w-full text-left text-[12px] flex items-center gap-2 p-2 rounded hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
                            onClick={() => onNavigateToTicket?.(dep.id)}
                            aria-label={`Navigate to dependent ticket: ${dep.title}`}
                            title={`Click to view: ${dep.title}`}
                          >
                            <Lock className="h-3 w-3 flex-shrink-0 text-blue-600 dark:text-blue-400" />
                            <span className="flex-1 truncate text-foreground">{dep.title}</span>
                            <span className="text-[10px] text-muted-foreground">
                              {STATE_DISPLAY_NAMES[dep.state]}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* View DAG button */}
              <Button
                variant="outline"
                size="sm"
                className="w-full gap-2 text-[12px]"
                onClick={() => setShowDAGView(true)}
                aria-label="Open dependency graph"
                title="Open full dependency graph visualization"
              >
                <GitBranch className="h-3.5 w-3.5" />
                View Full Dependency Graph
              </Button>
            </div>
          )}

          {/* Review Changes Section - shown for reviewable states */}
          {canShowRevisions && (
            <div className="space-y-4">
              <h3 className="section-label flex items-center gap-2">
                <GitPullRequest className="h-3.5 w-3.5" />
                Code Changes
              </h3>

              {revisionsLoading ? (
                <TicketDetailSkeleton />
              ) : revisions.length > 0 ? (
                <div className="space-y-3">
                  <p className="text-[13px] text-muted-foreground">
                    {revisions.length} revision{revisions.length !== 1 ? "s" : ""} available for review.
                    {revisions[0] && revisions[0].unresolved_comment_count > 0 && (
                      <span className="text-orange-500 ml-1">
                        ({revisions[0].unresolved_comment_count} unresolved comment{revisions[0].unresolved_comment_count !== 1 ? "s" : ""})
                      </span>
                    )}
                  </p>
                  <Button
                    onClick={() => setShowRevisionViewer(true)}
                    className="w-full"
                    variant="outline"
                  >
                    <ExternalLink className="h-4 w-4 mr-2" />
                    Review Changes
                  </Button>
                </div>
              ) : (
                <EmptyState icon={GitPullRequest} title="No revisions yet" description="Revisions are created when the agent executes changes" />
              )}
            </div>
          )}

          {/* Worktree & Merge Section */}
          {mergeStatus && (
            <div className="space-y-4">
              <h3 className="section-label flex items-center gap-2">
                <FolderGit className="h-3.5 w-3.5" />
                Worktree & Merge
              </h3>

              {mergeStatus.is_merged ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-emerald-500">
                    <Check className="h-4 w-4" />
                    <span className="text-[13px] font-medium">Merged to main</span>
                  </div>
                  {/* Warning if merge was done without pulling latest */}
                  {mergeStatus.last_merge_attempt?.payload?.pull_warning && (
                    <div className="flex items-start gap-2 text-amber-500 bg-amber-500/10 rounded-lg p-2.5">
                      <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                      <span className="text-[12px]">
                        {mergeStatus.last_merge_attempt.payload.pull_warning}
                      </span>
                    </div>
                  )}
                </div>
              ) : mergeStatus.workspace ? (
                <div className="space-y-3">
                  <div className="bg-muted/50 rounded-lg p-3 space-y-2">
                    <div className="flex items-start gap-2">
                      <span className="text-[11px] text-muted-foreground min-w-[60px]">Branch:</span>
                      <code className="text-[12px] text-foreground font-mono">
                        {mergeStatus.workspace.branch_name}
                      </code>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-[11px] text-muted-foreground min-w-[60px]">Path:</span>
                      <code className="text-[11px] text-muted-foreground font-mono break-all">
                        {mergeStatus.workspace.worktree_path}
                      </code>
                    </div>
                  </div>

                  {mergeStatus.can_merge && (
                    <Button
                      onClick={handleMerge}
                      disabled={mergeLoading}
                      className="w-full"
                      variant="default"
                    >
                      {mergeLoading ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <GitMerge className="h-4 w-4 mr-2" />
                      )}
                      Merge to Main
                    </Button>
                  )}

                  {!mergeStatus.can_merge && !mergeStatus.has_approved_revision && (
                    <p className="text-[12px] text-muted-foreground">
                      Revision must be approved before merging
                    </p>
                  )}

                  {mergeStatus.last_merge_attempt && mergeStatus.last_merge_attempt.event_type === "merge_failed" && (
                    <div className="flex items-center gap-2 text-destructive text-[12px]">
                      <X className="h-3.5 w-3.5" />
                      <span>Last merge failed: {mergeStatus.last_merge_attempt.reason}</span>
                    </div>
                  )}
                </div>
              ) : (
                <EmptyState icon={FolderGit} title="No active worktree" description="A worktree is created when execution starts" compact />
              )}
            </div>
          )}

          {/* Agent Activity - shows live streaming and persisted logs */}
          <div className="space-y-4">
            <h3 className="section-label flex items-center gap-2">
              <Activity className="h-3.5 w-3.5" />
              Agent Activity
              {jobs.some(j => j.status === JobStatus.RUNNING) && (
                <span className="flex items-center gap-1 text-[10px] text-emerald-400 font-medium uppercase tracking-wide">
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
                  </span>
                  Live
                </span>
              )}
            </h3>
            <AgentActivityLog ticketId={ticket.id} />
          </div>

          {/* Verification Evidence Section */}
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

          {/* Event Timeline Section */}
          <div className="space-y-4">
            <h3 className="section-label">
              Event History
            </h3>

            {loading ? (
              <TicketDetailSkeleton />
            ) : error ? (
              <div className="flex items-center gap-2 text-destructive py-6">
                <AlertCircle className="h-4 w-4" />
                <span className="text-[13px]">{error}</span>
              </div>
            ) : events.length === 0 ? (
              <EmptyState icon={Activity} title="No events recorded" description="Events are logged as the ticket moves through states" />
            ) : (
              <div className="space-y-4">
                {events.map((event) => (
                  <div 
                    key={event.id} 
                    className="border-l-2 border-border/50 pl-4 py-2 space-y-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[13px] font-medium capitalize text-foreground">
                        {event.event_type}
                      </span>
                      <span className="text-[12px] text-muted-foreground">
                        {formatDate(event.created_at)}
                      </span>
                    </div>

                    {event.event_type === EventType.TRANSITIONED &&
                      event.from_state &&
                      event.to_state && (
                        <div className="flex items-center gap-2 text-[13px]">
                          <span className="text-muted-foreground">
                            {STATE_DISPLAY_NAMES[event.from_state]}
                          </span>
                          <ArrowRight className="h-3 w-3 text-muted-foreground/60" />
                          <span className="text-foreground font-medium">
                            {STATE_DISPLAY_NAMES[event.to_state]}
                          </span>
                        </div>
                      )}

                    {event.reason && (
                      <p className="text-[13px] text-muted-foreground leading-relaxed">
                        {event.reason}
                      </p>
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
      </SheetContent>
    </Sheet>

    {/* DAG View Dialog */}
    <Dialog open={showDAGView} onOpenChange={setShowDAGView}>
      <DialogContent className="max-w-[95vw] h-[95vh] p-0">
        <DialogHeader className="px-6 py-4 border-b">
          <DialogTitle>Dependency Graph</DialogTitle>
        </DialogHeader>
        <div className="flex-1 overflow-hidden">
          <TicketDAGView highlightedTicketId={ticket?.id || null} />
        </div>
      </DialogContent>
    </Dialog>
  </>
  );
}
