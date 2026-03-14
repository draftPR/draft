/**
 * TicketDetailPanel -- standalone ticket detail view for resizable panel layout.
 *
 * Fetches the full ticket and renders the same content as the Sheet drawer,
 * but without the Sheet wrapper.
 */

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { EvidenceList } from "@/components/EvidenceList";
import { EmptyState } from "@/components/EmptyState";
import { TicketDetailSkeleton } from "@/components/skeletons/TicketDetailSkeleton";
import { AgentActivityLog } from "@/components/AgentActivityLog";
import { BlockingIndicator } from "@/components/BlockingIndicator";
import { RevisionViewer } from "@/components/RevisionViewer";
import { ConflictBanner } from "@/components/ConflictBanner";
import {
  fetchTicketEvents,
  fetchTicketEvidence,
  fetchTicketRevisions,
  fetchMergeStatus,
  mergeTicket,
  fetchTicketJobs,
  fetchTicketDependents,
  fetchTicket,
  executeTicket,
  transitionTicket,
  updateTicket,
  queueFollowupMessage,
  getQueuedMessage,
  cancelQueuedMessage,
  fetchExecutorProfiles,
  fetchConflictStatus,
  type ExecutorProfile,
} from "@/services/api";
import type {
  Ticket,
  TicketEvent,
  Evidence,
  Revision,
  MergeStatusResponse,
  ConflictStatusResponse,
  Job,
  QueuedMessageStatus,
} from "@/types/api";
import {
  STATE_DISPLAY_NAMES,
  ActorType,
  EventType,
  TicketState,
  MergeStrategy,
  JobStatus,
  PriorityBucket,
  PRIORITY_BUCKET_LABELS,
  PRIORITY_BUCKET_VALUES,
} from "@/types/api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
  ArrowRight,
  AlertCircle,
  ExternalLink,
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
  Play,
  MessageSquarePlus,
  Send,
  ChevronDown,
  Ban,
  Pencil,
} from "lucide-react";
import { CreatePRButton } from "@/components/PullRequest/CreatePRButton";
import { PRStatusBadge } from "@/components/PullRequest/PRStatusBadge";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { useTicketSelectionStore } from "@/stores/ticketStore";
import { useBoard } from "@/contexts/BoardContext";
import { useBoardViewQuery } from "@/hooks/useQueries";

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

function priorityToBucket(priority: number | null): PriorityBucket | "" {
  if (priority === null) return "";
  if (priority >= 80) return PriorityBucket.P0;
  if (priority >= 60) return PriorityBucket.P1;
  if (priority >= 40) return PriorityBucket.P2;
  return PriorityBucket.P3;
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
  // Evidence loads as part of loadAll; the outer `loading` flag covers it
  const [mergeLoading, setMergeLoading] = useState(false);
  const [showRevisionViewer, setShowRevisionViewer] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Agent execution state
  const [executeLoading, setExecuteLoading] = useState(false);
  const [executorProfiles, setExecutorProfiles] = useState<ExecutorProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string>("");
  const [showProfileSelector, setShowProfileSelector] = useState(false);

  // Follow-up queue state
  const [followUpText, setFollowUpText] = useState("");
  const [queuedMessage, setQueuedMessage] = useState<QueuedMessageStatus | null>(null);
  const [queueLoading, setQueueLoading] = useState(false);

  // Conflict state
  const [conflictStatus, setConflictStatus] = useState<ConflictStatusResponse | null>(null);

  // Inline editing state
  const [editingTitle, setEditingTitle] = useState(false);
  const [editingDescription, setEditingDescription] = useState(false);
  const [editTitleValue, setEditTitleValue] = useState("");
  const [editDescriptionValue, setEditDescriptionValue] = useState("");
  const [savingTitle, setSavingTitle] = useState(false);
  const [savingDescription, setSavingDescription] = useState(false);
  const titleInputRef = useRef<HTMLInputElement>(null);
  const descriptionTextareaRef = useRef<HTMLTextAreaElement>(null);

  // Load executor profiles once
  useEffect(() => {
    fetchExecutorProfiles()
      .then(setExecutorProfiles)
      .catch(() => {});
  }, []);

  const loadAll = useCallback(async (ticketId: string) => {
    setLoading(true);
    setError(null);
    try {
      const [t, evts, evi, revs, sts, jbs, deps, cst] = await Promise.all([
        fetchTicket(ticketId),
        fetchTicketEvents(ticketId).catch(() => ({ events: [] })),
        fetchTicketEvidence(ticketId).catch(() => ({ evidence: [] })),
        fetchTicketRevisions(ticketId).catch(() => ({ revisions: [] })),
        fetchMergeStatus(ticketId).catch(() => null),
        fetchTicketJobs(ticketId).catch(() => ({ jobs: [] })),
        fetchTicketDependents(ticketId).catch(() => []),
        fetchConflictStatus(ticketId).catch(() => null),
      ]);
      setTicket(t);
      setEvents(evts.events);
      setEvidence(evi.evidence);
      setRevisions(revs.revisions);
      setMergeStatus(sts);
      setJobs(jbs.jobs);
      setDependents(deps);
      setConflictStatus(cst);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load ticket");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedTicketId) {
      setShowRevisionViewer(false);
      setFollowUpText("");
      setQueuedMessage(null);
      loadAll(selectedTicketId);
    }
  }, [selectedTicketId, loadAll]);

  // Auto-refresh jobs when running + poll queue status
  const hasRunningJob = jobs.some(j => j.status === JobStatus.RUNNING || j.status === JobStatus.QUEUED);
  useEffect(() => {
    if (!hasRunningJob || !selectedTicketId) return;
    const interval = setInterval(() => {
      fetchTicketJobs(selectedTicketId).then(r => setJobs(r.jobs)).catch(() => {});
      getQueuedMessage(selectedTicketId).then(setQueuedMessage).catch(() => {});
    }, 5000);
    return () => clearInterval(interval);
  }, [hasRunningJob, selectedTicketId]);

  // Load queue status when ticket changes
  useEffect(() => {
    if (selectedTicketId && hasRunningJob) {
      getQueuedMessage(selectedTicketId).then(setQueuedMessage).catch(() => {});
    }
  }, [selectedTicketId, hasRunningJob]);

  // Keyboard navigation (j/k to navigate between tickets)
  const { currentBoard } = useBoard();
  const { data: boardData, dataUpdatedAt } = useBoardViewQuery(currentBoard?.id, false);
  const allTicketIds = useMemo(() => {
    if (!boardData?.columns) return [];
    return boardData.columns.flatMap((col) => col.tickets.map((t) => t.id));
  }, [boardData]);

  useEffect(() => {
    if (!selectedTicketId || allTicketIds.length === 0) return;
    const handler = (e: KeyboardEvent) => {
      // Don't intercept if user is typing in an input
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      const idx = allTicketIds.indexOf(selectedTicketId);
      if (idx === -1) return;

      if (e.key === "j" && idx < allTicketIds.length - 1) {
        e.preventDefault();
        selectTicket(allTicketIds[idx + 1]);
      } else if (e.key === "k" && idx > 0) {
        e.preventDefault();
        selectTicket(allTicketIds[idx - 1]);
      } else if (e.key === "Escape") {
        e.preventDefault();
        clearSelection();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedTicketId, allTicketIds, selectTicket, clearSelection]);

  // Re-fetch detail when board data updates (e.g. state changed externally)
  const [lastBoardUpdate, setLastBoardUpdate] = useState(0);
  useEffect(() => {
    if (dataUpdatedAt && dataUpdatedAt !== lastBoardUpdate && lastBoardUpdate !== 0 && selectedTicketId) {
      // Board data changed — check if our ticket's state changed
      if (boardData?.columns) {
        for (const col of boardData.columns) {
          const found = col.tickets.find(t => t.id === selectedTicketId);
          if (found && ticket && found.state !== ticket.state) {
            loadAll(selectedTicketId);
            break;
          }
        }
      }
    }
    setLastBoardUpdate(dataUpdatedAt ?? 0);
  }, [dataUpdatedAt, selectedTicketId, boardData, ticket, loadAll, lastBoardUpdate]);

  // Combined activity timeline: merge events + jobs into a single chronological list
  const activityTimeline = useMemo(() => {
    const items: Array<{
      id: string;
      type: "event" | "job";
      timestamp: string;
      data: TicketEvent | Job;
    }> = [];
    events.forEach((evt) =>
      items.push({ id: evt.id, type: "event", timestamp: evt.created_at, data: evt })
    );
    jobs.forEach((job) =>
      items.push({ id: job.id, type: "job", timestamp: job.created_at, data: job })
    );
    items.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
    return items;
  }, [events, jobs]);

  const handleAccept = useCallback(async () => {
    if (!ticket) return;
    try {
      await transitionTicket(ticket.id, { to_state: TicketState.PLANNED, actor_type: ActorType.HUMAN });
      toast.success("Ticket accepted");
      loadAll(ticket.id);
    } catch (err) {
      toast.error("Failed to accept ticket", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }, [ticket, loadAll]);

  const handleUnblock = useCallback(async () => {
    if (!ticket) return;
    try {
      await transitionTicket(ticket.id, { to_state: TicketState.PLANNED, actor_type: ActorType.HUMAN });
      toast.success("Ticket unblocked");
      loadAll(ticket.id);
    } catch (err) {
      toast.error("Failed to unblock ticket", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }, [ticket, loadAll]);

  const handleExecute = useCallback(async () => {
    if (!ticket) return;
    setExecuteLoading(true);
    try {
      await executeTicket(ticket.id, selectedProfile || undefined);
      toast.success("Execution started");
      loadAll(ticket.id);
    } catch (err) {
      toast.error("Failed to start execution", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setExecuteLoading(false);
    }
  }, [ticket, selectedProfile, loadAll]);

  const handleQueueFollowUp = useCallback(async () => {
    if (!ticket || !followUpText.trim()) return;
    setQueueLoading(true);
    try {
      const result = await queueFollowupMessage(ticket.id, followUpText.trim());
      setQueuedMessage(result);
      setFollowUpText("");
      toast.success("Follow-up queued", {
        description: "Will execute after current job completes",
      });
    } catch (err) {
      toast.error("Failed to queue follow-up", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setQueueLoading(false);
    }
  }, [ticket, followUpText]);

  const handleCancelQueued = useCallback(async () => {
    if (!ticket) return;
    try {
      const result = await cancelQueuedMessage(ticket.id);
      setQueuedMessage(result);
      toast.success("Queued message cancelled");
    } catch {
      // ignore
    }
  }, [ticket]);

  const handleAbandon = useCallback(async () => {
    if (!ticket) return;
    try {
      await transitionTicket(ticket.id, {
        to_state: TicketState.ABANDONED,
        actor_type: ActorType.HUMAN,
        reason: "Abandoned by user",
      });
      toast.success("Ticket abandoned");
      loadAll(ticket.id);
    } catch (err) {
      toast.error("Failed to abandon ticket", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }, [ticket, loadAll]);

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

  const handleRevisionUpdated = useCallback(() => {
    if (ticket) {
      loadAll(ticket.id);
    }
  }, [ticket, loadAll]);

  // --- Inline editing handlers ---

  const startEditingTitle = useCallback(() => {
    if (!ticket) return;
    setEditTitleValue(ticket.title);
    setEditingTitle(true);
    // Focus the input after render
    setTimeout(() => titleInputRef.current?.focus(), 0);
  }, [ticket]);

  const cancelEditingTitle = useCallback(() => {
    setEditingTitle(false);
    setEditTitleValue("");
  }, []);

  const saveTitle = useCallback(async () => {
    if (!ticket || !editTitleValue.trim()) return;
    if (editTitleValue.trim() === ticket.title) {
      cancelEditingTitle();
      return;
    }
    setSavingTitle(true);
    try {
      await updateTicket(ticket.id, { title: editTitleValue.trim() });
      toast.success("Title updated");
      setEditingTitle(false);
      loadAll(ticket.id);
    } catch (err) {
      toast.error("Failed to update title", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setSavingTitle(false);
    }
  }, [ticket, editTitleValue, cancelEditingTitle, loadAll]);

  const startEditingDescription = useCallback(() => {
    if (!ticket) return;
    setEditDescriptionValue(ticket.description || "");
    setEditingDescription(true);
    setTimeout(() => descriptionTextareaRef.current?.focus(), 0);
  }, [ticket]);

  const cancelEditingDescription = useCallback(() => {
    setEditingDescription(false);
    setEditDescriptionValue("");
  }, []);

  const saveDescription = useCallback(async () => {
    if (!ticket) return;
    const newDesc = editDescriptionValue.trim() || null;
    if (newDesc === (ticket.description || null)) {
      cancelEditingDescription();
      return;
    }
    setSavingDescription(true);
    try {
      await updateTicket(ticket.id, { description: newDesc });
      toast.success("Description updated");
      setEditingDescription(false);
      loadAll(ticket.id);
    } catch (err) {
      toast.error("Failed to update description", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setSavingDescription(false);
    }
  }, [ticket, editDescriptionValue, cancelEditingDescription, loadAll]);

  const handlePriorityChange = useCallback(async (bucket: string) => {
    if (!ticket) return;
    const newPriority = bucket ? PRIORITY_BUCKET_VALUES[bucket as PriorityBucket] : null;
    if (newPriority === ticket.priority) return;
    try {
      await updateTicket(ticket.id, { priority: newPriority });
      toast.success("Priority updated", {
        description: bucket ? PRIORITY_BUCKET_LABELS[bucket as PriorityBucket] : "Priority cleared",
      });
      loadAll(ticket.id);
    } catch (err) {
      toast.error("Failed to update priority", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }, [ticket, loadAll]);

  // Reset editing state when switching tickets
  useEffect(() => {
    setEditingTitle(false);
    setEditingDescription(false);
  }, [selectedTicketId]);

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
        <div className="flex flex-col items-center gap-3 text-center">
          <AlertCircle className="h-6 w-6 text-destructive" />
          <p className="text-sm text-destructive">{error}</p>
          <Button variant="outline" size="sm" onClick={() => selectedTicketId && loadAll(selectedTicketId)}>
            Retry
          </Button>
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
  // NEEDS_HUMAN is excluded — ticket is awaiting review, not re-execution.
  // Re-running from review is done via "Request Changes" in the revision viewer.
  const canExecute = ([
    TicketState.PLANNED,
    TicketState.BLOCKED,
  ] as string[]).includes(ticket.state);

  const canAbandon = ([
    TicketState.PROPOSED,
    TicketState.PLANNED,
    TicketState.NEEDS_HUMAN,
    TicketState.BLOCKED,
  ] as string[]).includes(ticket.state);

  return (
    <>
    {/* Full-screen revision viewer overlay */}
    {showRevisionViewer && revisions.length > 0 && (
      <div className="fixed inset-0 z-50 bg-background">
        <RevisionViewer
          ticketId={ticket.id}
          ticketTitle={ticket.title}
          revisions={revisions}
          onRevisionUpdated={handleRevisionUpdated}
          onClose={() => setShowRevisionViewer(false)}
        />
      </div>
    )}

    <div className="h-full overflow-y-auto border-l border-border bg-background">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-background border-b border-border/40 px-6 py-4">
        <div className="flex items-start justify-between gap-2">
          {editingTitle ? (
            <div className="flex-1 pr-4 space-y-2">
              <Input
                ref={titleInputRef}
                value={editTitleValue}
                onChange={(e) => setEditTitleValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    saveTitle();
                  } else if (e.key === "Escape") {
                    e.preventDefault();
                    cancelEditingTitle();
                  }
                }}
                disabled={savingTitle}
                className="text-[15px] font-semibold"
                placeholder="Ticket title"
              />
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="default"
                  onClick={saveTitle}
                  disabled={savingTitle || !editTitleValue.trim()}
                  className="h-7 px-2 text-[12px]"
                >
                  {savingTitle ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Check className="h-3 w-3 mr-1" />}
                  Save
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={cancelEditingTitle}
                  disabled={savingTitle}
                  className="h-7 px-2 text-[12px]"
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-1.5 group pr-4">
              <h2 className="text-[15px] leading-relaxed font-semibold text-foreground">
                {ticket.title}
              </h2>
              <button
                onClick={startEditingTitle}
                className="mt-1 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-foreground"
                title="Edit title"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
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
          <div className="flex items-center gap-1.5 group">
            <h3 className="section-label">Description</h3>
            {!editingDescription && (
              <button
                onClick={startEditingDescription}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-foreground"
                title="Edit description"
              >
                <Pencil className="h-3 w-3" />
              </button>
            )}
          </div>
          {editingDescription ? (
            <div className="space-y-2">
              <Textarea
                ref={descriptionTextareaRef}
                value={editDescriptionValue}
                onChange={(e) => setEditDescriptionValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    e.preventDefault();
                    cancelEditingDescription();
                  }
                  // Ctrl/Cmd+Enter to save
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    saveDescription();
                  }
                }}
                disabled={savingDescription}
                className="text-[13px] leading-relaxed min-h-[80px]"
                placeholder="Add a description..."
              />
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="default"
                  onClick={saveDescription}
                  disabled={savingDescription}
                  className="h-7 px-2 text-[12px]"
                >
                  {savingDescription ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Check className="h-3 w-3 mr-1" />}
                  Save
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={cancelEditingDescription}
                  disabled={savingDescription}
                  className="h-7 px-2 text-[12px]"
                >
                  Cancel
                </Button>
                <span className="text-[11px] text-muted-foreground ml-auto">
                  Ctrl+Enter to save
                </span>
              </div>
            </div>
          ) : (
            <p
              className="text-[13px] leading-relaxed text-foreground cursor-pointer hover:bg-muted/50 rounded-md px-2 py-1 -mx-2 -my-1 transition-colors"
              onClick={startEditingDescription}
            >
              {ticket.description || (
                <span className="text-muted-foreground italic">No description provided -- click to add</span>
              )}
            </p>
          )}
        </div>

        {/* State & Priority */}
        <div className="grid grid-cols-2 gap-8">
          <div className="space-y-3">
            <h3 className="section-label">State</h3>
            <p className="text-[13px] text-foreground">{STATE_DISPLAY_NAMES[ticket.state]}</p>
          </div>
          <div className="space-y-3">
            <h3 className="section-label">Priority</h3>
            <Select
              value={priorityToBucket(ticket.priority) || "none"}
              onValueChange={(val) => handlePriorityChange(val === "none" ? "" : val)}
            >
              <SelectTrigger size="sm" className="h-8 text-[13px] w-full">
                <SelectValue>
                  <span className={cn("font-medium", priority.color)}>
                    {priority.label}
                  </span>
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">
                  <span className="text-muted-foreground">Not set</span>
                </SelectItem>
                <SelectItem value={PriorityBucket.P0}>
                  <span className="text-red-500 font-medium">P0 - Critical (90)</span>
                </SelectItem>
                <SelectItem value={PriorityBucket.P1}>
                  <span className="text-orange-500 font-medium">P1 - High (70)</span>
                </SelectItem>
                <SelectItem value={PriorityBucket.P2}>
                  <span className="text-blue-500 font-medium">P2 - Medium (50)</span>
                </SelectItem>
                <SelectItem value={PriorityBucket.P3}>
                  <span className="text-slate-500 font-medium">P3 - Low (30)</span>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* State Transition Actions */}
        {ticket.state === TicketState.PROPOSED && (
          <div className="space-y-3">
            <Button onClick={handleAccept} className="w-full" variant="default">
              <Check className="h-4 w-4 mr-2" />
              Accept
            </Button>
          </div>
        )}

        {ticket.state === TicketState.BLOCKED && (
          <div className="space-y-3">
            {ticket.blocked_by_ticket_id ? (
              <p className="text-xs text-muted-foreground text-center py-2">
                Blocked by another ticket — complete the blocker first
              </p>
            ) : (
              <Button onClick={handleUnblock} className="w-full" variant="outline">
                <Lock className="h-4 w-4 mr-2" />
                Unblock
              </Button>
            )}
          </div>
        )}

        {/* Execute / Follow-Up Actions */}
        {(canExecute || hasRunningJob) && (
          <div className="space-y-4">
            <h3 className="section-label flex items-center gap-2">
              <Play className="h-3.5 w-3.5" />
              Agent Actions
            </h3>

            {/* Execute button (when no job running) */}
            {canExecute && !hasRunningJob && (
              <div className="space-y-3">
                {/* Executor profile selector */}
                {executorProfiles.length > 1 && (
                  <div>
                    <button
                      onClick={() => setShowProfileSelector(!showProfileSelector)}
                      className="flex items-center gap-1.5 text-[12px] text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <ChevronDown className={cn("h-3 w-3 transition-transform", showProfileSelector && "rotate-180")} />
                      {selectedProfile
                        ? `Profile: ${selectedProfile}`
                        : "Default executor profile"}
                    </button>
                    {showProfileSelector && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <button
                          onClick={() => { setSelectedProfile(""); setShowProfileSelector(false); }}
                          className={cn(
                            "px-2.5 py-1 rounded-md text-[12px] border transition-colors",
                            !selectedProfile
                              ? "bg-foreground text-background border-foreground"
                              : "border-border hover:border-foreground/50"
                          )}
                        >
                          Default
                        </button>
                        {executorProfiles.map((p) => (
                          <button
                            key={p.name}
                            onClick={() => { setSelectedProfile(p.name); setShowProfileSelector(false); }}
                            className={cn(
                              "px-2.5 py-1 rounded-md text-[12px] border transition-colors",
                              selectedProfile === p.name
                                ? "bg-foreground text-background border-foreground"
                                : "border-border hover:border-foreground/50"
                            )}
                          >
                            {p.name}
                            <span className="ml-1 text-[10px] opacity-60">{p.executor_type.replace(/_/g, " ")}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <Button
                  onClick={handleExecute}
                  disabled={executeLoading}
                  className="w-full"
                >
                  {executeLoading ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4 mr-2" />
                  )}
                  Execute{selectedProfile ? ` (${selectedProfile})` : ""}
                </Button>
              </div>
            )}

            {/* Follow-up queue (only when agent is actively executing, not awaiting review) */}
            {hasRunningJob && ticket.state === TicketState.EXECUTING && (
              <div className="space-y-3">
                {/* Queued message indicator */}
                {queuedMessage?.status === "queued" && queuedMessage.message && (
                  <div className="bg-violet-50 dark:bg-violet-900/20 rounded-lg p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-medium text-violet-600 dark:text-violet-400 uppercase tracking-wide">
                        Queued follow-up
                      </span>
                      <button
                        onClick={handleCancelQueued}
                        className="text-[11px] text-muted-foreground hover:text-destructive transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                    <p className="text-[12px] text-foreground leading-relaxed">
                      {queuedMessage.message}
                    </p>
                  </div>
                )}

                {/* Follow-up input */}
                <div className="flex gap-2">
                  <div className="flex-1 relative">
                    <MessageSquarePlus className="absolute left-3 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                    <input
                      type="text"
                      placeholder="Queue next instruction..."
                      value={followUpText}
                      onChange={(e) => setFollowUpText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey && followUpText.trim()) {
                          e.preventDefault();
                          handleQueueFollowUp();
                        }
                      }}
                      className="w-full rounded-md border border-border bg-background pl-9 pr-3 py-2 text-[13px] placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                  </div>
                  <Button
                    size="sm"
                    onClick={handleQueueFollowUp}
                    disabled={queueLoading || !followUpText.trim()}
                    className="h-[38px] px-3"
                  >
                    {queueLoading ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Send className="h-3.5 w-3.5" />
                    )}
                  </Button>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Queue the next instruction while the agent is working. It will auto-execute when done.
                </p>
              </div>
            )}
          </div>
        )}

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
              <div className="space-y-3">
                <p className="text-[13px] text-muted-foreground">
                  {revisions.length} revision{revisions.length !== 1 ? "s" : ""} available.
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
                {/* Conflict/divergence banner */}
                {conflictStatus && (conflictStatus.has_conflict || (conflictStatus.divergence && !conflictStatus.divergence.up_to_date)) && (
                  <ConflictBanner
                    ticketId={ticket.id}
                    conflictStatus={conflictStatus}
                    onResolved={() => loadAll(ticket.id)}
                  />
                )}
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

        {/* Abandon Ticket */}
        {canAbandon && (
          <div className="space-y-3">
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" className="w-full" size="sm">
                  <Ban className="h-4 w-4 mr-2" />
                  Abandon Ticket
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Abandon this ticket?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will mark the ticket as abandoned. Any associated worktree will be cleaned up. This action cannot be easily undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={handleAbandon}
                    className={buttonVariants({ variant: "destructive" })}
                  >
                    Abandon
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
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
          <EvidenceList evidence={evidence} />
        </div>

        {/* Activity Timeline */}
        <div className="space-y-4">
          <h3 className="section-label flex items-center gap-2">
            <Activity className="h-3.5 w-3.5" />
            Activity Timeline
            <span className="text-[10px] text-muted-foreground font-normal">
              {activityTimeline.length} event{activityTimeline.length !== 1 ? "s" : ""}
            </span>
          </h3>
          {activityTimeline.length === 0 ? (
            <EmptyState icon={Activity} title="No activity recorded" compact />
          ) : (
            <div className="space-y-1">
              {activityTimeline.map((item) => {
                if (item.type === "event") {
                  const event = item.data as TicketEvent;
                  return (
                    <div key={item.id} className="border-l-2 border-border/50 pl-4 py-2 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-[12px] font-medium capitalize text-foreground">{event.event_type.replace(/_/g, " ")}</span>
                        <span className="text-[11px] text-muted-foreground">{formatDate(event.created_at)}</span>
                      </div>
                      {event.event_type === EventType.TRANSITIONED && event.from_state && event.to_state && (
                        <div className="flex items-center gap-2 text-[12px]">
                          <span className="text-muted-foreground">{STATE_DISPLAY_NAMES[event.from_state]}</span>
                          <ArrowRight className="h-3 w-3 text-muted-foreground/60" />
                          <span className="text-foreground font-medium">{STATE_DISPLAY_NAMES[event.to_state]}</span>
                        </div>
                      )}
                      {event.reason && (
                        <p className="text-[12px] text-muted-foreground leading-relaxed">{event.reason}</p>
                      )}
                    </div>
                  );
                }
                const job = item.data as Job;
                return (
                  <div
                    key={item.id}
                    className={cn(
                      "border-l-2 pl-4 py-2 space-y-1",
                      job.status === JobStatus.SUCCEEDED ? "border-emerald-300" :
                      job.status === JobStatus.FAILED ? "border-red-300" :
                      job.status === JobStatus.RUNNING ? "border-blue-300" :
                      "border-border/50"
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-medium text-foreground capitalize flex items-center gap-1.5">
                        {job.status === JobStatus.RUNNING && <Loader2 className="h-3 w-3 animate-spin text-blue-500" />}
                        {job.status === JobStatus.SUCCEEDED && <Check className="h-3 w-3 text-emerald-500" />}
                        {job.status === JobStatus.FAILED && <AlertCircle className="h-3 w-3 text-red-500" />}
                        {job.kind.replace(/_/g, " ")} job
                      </span>
                      <span className="text-[11px] text-muted-foreground">{formatDate(job.created_at)}</span>
                    </div>
                    {(job as Job & { error_message?: string }).error_message && (
                      <p className="text-[11px] text-red-500 leading-relaxed truncate">{(job as Job & { error_message?: string }).error_message}</p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Keyboard navigation hint */}
        <div className="text-[11px] text-muted-foreground text-center py-2 border-t border-border/30">
          <kbd className="px-1 py-0.5 rounded border bg-muted text-[10px]">j</kbd>
          <span className="mx-1">/</span>
          <kbd className="px-1 py-0.5 rounded border bg-muted text-[10px]">k</kbd>
          <span className="ml-1">navigate tickets</span>
          <span className="mx-2">·</span>
          <kbd className="px-1 py-0.5 rounded border bg-muted text-[10px]">esc</kbd>
          <span className="ml-1">close</span>
        </div>
      </div>
    </div>
    </>
  );
}
