import { useEffect, useState, useCallback } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { EvidenceList } from "@/components/EvidenceList";
import { RevisionViewer } from "@/components/RevisionViewer";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  fetchTicketEvents,
  fetchTicketEvidence,
  fetchTicketRevisions,
  fetchMergeStatus,
  mergeTicket,
  fetchTicketJobs,
  retryJob,
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
} from "lucide-react";

interface TicketDetailDrawerProps {
  ticket: Ticket | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
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
}: TicketDetailDrawerProps) {
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [mergeStatus, setMergeStatus] = useState<MergeStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [revisionsLoading, setRevisionsLoading] = useState(false);
  const [mergeLoading, setMergeLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showRevisionViewer, setShowRevisionViewer] = useState(false);

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

  useEffect(() => {
    if (ticket && open) {
      loadEvents(ticket.id);
      loadEvidence(ticket.id);
      loadRevisions(ticket.id);
      loadMergeStatus(ticket.id);
      loadJobs(ticket.id);
      setShowRevisionViewer(false); // Reset when opening a new ticket
    }
    // Only re-fetch when ticket ID changes or drawer opens, not on ticket object reference changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticket?.id, open, loadEvents, loadEvidence, loadRevisions, loadMergeStatus, loadJobs]);

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
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[25%] min-w-[500px] overflow-y-auto bg-background pl-8">
        <SheetHeader className="pb-8 border-b border-border/40">
          <SheetTitle className="text-[15px] leading-relaxed pr-8 font-semibold text-foreground">
            {ticket.title}
          </SheetTitle>
          <SheetDescription className="sr-only">
            Ticket details and event history
          </SheetDescription>
        </SheetHeader>

        <div className="mt-8 space-y-10">
          {/* Description Section */}
          <div className="space-y-3">
            <h3 className="text-[11px] font-semibold text-muted-foreground/80 tracking-wide uppercase">
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
              <h3 className="text-[11px] font-semibold text-muted-foreground/80 tracking-wide uppercase">
                State
              </h3>
              <p className="text-[13px] text-foreground">
                {STATE_DISPLAY_NAMES[ticket.state]}
                {/* Clarify that Verified doesn't mean merged */}
                {ticket.state === "done" && (
                  <span className="text-muted-foreground text-[11px] ml-1">(unmerged)</span>
                )}
              </p>
            </div>
            <div className="space-y-3">
              <h3 className="text-[11px] font-semibold text-muted-foreground/80 tracking-wide uppercase">
                Priority
              </h3>
              <p className={cn("text-[13px] font-medium", priority.color)}>
                {priority.label}
              </p>
            </div>
          </div>

          {/* Review Changes Section - shown for reviewable states */}
          {canShowRevisions && (
            <div className="space-y-4">
              <h3 className="text-[11px] font-semibold text-muted-foreground/80 tracking-wide uppercase flex items-center gap-2">
                <GitPullRequest className="h-3.5 w-3.5" />
                Code Changes
              </h3>

              {revisionsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
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
                <p className="text-[13px] text-muted-foreground italic">
                  No revisions available yet
                </p>
              )}
            </div>
          )}

          {/* Worktree & Merge Section */}
          {mergeStatus && (
            <div className="space-y-4">
              <h3 className="text-[11px] font-semibold text-muted-foreground/80 tracking-wide uppercase flex items-center gap-2">
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
                <p className="text-[13px] text-muted-foreground italic">
                  No active worktree
                </p>
              )}
            </div>
          )}

          {/* Jobs Section */}
          {jobs.length > 0 && (
            <div className="space-y-4">
              <h3 className="text-[11px] font-semibold text-muted-foreground/80 tracking-wide uppercase flex items-center gap-2">
                <Loader2 className="h-3.5 w-3.5" />
                Jobs
              </h3>

              <div className="space-y-2">
                {jobs.slice(0, 5).map((job) => (
                  <div
                    key={job.id}
                    className="flex items-center justify-between bg-muted/30 rounded-lg p-2"
                  >
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-[10px] px-1.5 py-0",
                          job.status === JobStatus.SUCCEEDED && "border-emerald-500 text-emerald-500",
                          job.status === JobStatus.FAILED && "border-red-500 text-red-500",
                          job.status === JobStatus.RUNNING && "border-amber-500 text-amber-500",
                          job.status === JobStatus.QUEUED && "border-blue-500 text-blue-500",
                          job.status === JobStatus.CANCELED && "border-gray-500 text-gray-500"
                        )}
                      >
                        {job.status}
                      </Badge>
                      <span className="text-[12px] text-muted-foreground capitalize">
                        {job.kind}
                      </span>
                    </div>
                    {(job.status === JobStatus.FAILED || job.status === JobStatus.CANCELED) && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 px-2 text-[11px]"
                        onClick={() => handleRetryJob(job.id)}
                      >
                        <RefreshCw className="h-3 w-3 mr-1" />
                        Retry
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Verification Evidence Section */}
          <div className="space-y-4">
            <h3 className="text-[11px] font-semibold text-muted-foreground/80 tracking-wide uppercase flex items-center gap-2">
              <FlaskConical className="h-3.5 w-3.5" />
              Verification Evidence
            </h3>

            {evidenceLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <EvidenceList evidence={evidence} />
            )}
          </div>

          {/* Event Timeline Section */}
          <div className="space-y-4">
            <h3 className="text-[11px] font-semibold text-muted-foreground/80 tracking-wide uppercase">
              Event History
            </h3>

            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : error ? (
              <div className="flex items-center gap-2 text-destructive py-6">
                <AlertCircle className="h-4 w-4" />
                <span className="text-[13px]">{error}</span>
              </div>
            ) : events.length === 0 ? (
              <p className="text-[13px] text-muted-foreground italic py-6">
                No events recorded
              </p>
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
  );
}
