import { useState, useEffect, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { ProposedTicketsReview } from "@/components/ProposedTicketsReview";
import { ReflectionDialog } from "@/components/ReflectionDialog";
import { TicketGenerationProgress } from "@/components/TicketGenerationProgress";
import { fetchGoal, deleteGoal, updateGoal, fetchDashboard } from "@/services/api";
import type { Goal, ProposedTicket, DashboardResponse } from "@/types/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Loader2, Sparkles, AlertCircle, Calendar, Lightbulb, Zap, Trash2, DollarSign, Pencil, Save, X } from "lucide-react";

interface GoalDetailDialogProps {
  goalId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onTicketsAccepted?: () => void;
  onGoalDeleted?: () => void;
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function GoalDetailDialog({
  goalId,
  open,
  onOpenChange,
  onTicketsAccepted,
  onGoalDeleted,
}: GoalDetailDialogProps) {
  const [goal, setGoal] = useState<Goal | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposedTickets, setProposedTickets] = useState<ProposedTicket[]>([]);
  const [showReview, setShowReview] = useState(false);
  const [showReflection, setShowReflection] = useState(false);
  const [showProgress, setShowProgress] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [costData, setCostData] = useState<DashboardResponse | null>(null);
  const [costLoading, setCostLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [saving, setSaving] = useState(false);

  const loadGoal = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchGoal(id);
      setGoal(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load goal";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCostData = useCallback(async (id: string) => {
    setCostLoading(true);
    try {
      const data = await fetchDashboard(id);
      setCostData(data);
    } catch {
      // Cost data is optional; silently ignore errors
      setCostData(null);
    } finally {
      setCostLoading(false);
    }
  }, []);

  useEffect(() => {
    if (goalId && open) {
      loadGoal(goalId);
      loadCostData(goalId);
      // Reset state when opening
      setProposedTickets([]);
      setShowReview(false);
    }
  }, [goalId, open, loadGoal, loadCostData]);

  const handleDeleteGoal = async () => {
    if (!goalId) return;
    setDeleting(true);
    try {
      await deleteGoal(goalId);
      toast.success("Goal deleted successfully");
      setShowDeleteConfirm(false);
      onOpenChange(false);
      onGoalDeleted?.();
      onTicketsAccepted?.();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete goal";
      toast.error(message);
    } finally {
      setDeleting(false);
    }
  };

  const handleStartEdit = () => {
    if (!goal) return;
    setEditTitle(goal.title);
    setEditDescription(goal.description || "");
    setEditing(true);
  };

  const handleCancelEdit = () => {
    setEditing(false);
  };

  const handleSaveEdit = async () => {
    if (!goalId || !editTitle.trim()) return;
    setSaving(true);
    try {
      await updateGoal(goalId, {
        title: editTitle.trim(),
        description: editDescription.trim() || null,
      });
      await loadGoal(goalId);
      setEditing(false);
      toast.success("Goal updated");
      onTicketsAccepted?.(); // refresh board in case title changed
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update goal";
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateTickets = () => {
    if (!goalId) return;
    // Show the streaming progress dialog
    setShowProgress(true);
  };

  const handleGenerationComplete = () => {
    // Refresh the board to show new tickets
    onTicketsAccepted?.();
    loadGoal(goalId!);
  };

  const handleShowTickets = () => {
    // Close progress dialog, goal detail dialog, and signal parent to close goals list
    setShowProgress(false);
    onOpenChange(false);
    onTicketsAccepted?.();
  };

  const handleReviewClose = () => {
    setShowReview(false);
    setProposedTickets([]);
  };

  const handleTicketsAccepted = () => {
    setShowReview(false);
    setProposedTickets([]);
    onTicketsAccepted?.();
    onOpenChange(false);
  };

  const handlePrioritiesUpdated = () => {
    // Refresh the board after priorities are updated
    onTicketsAccepted?.();
  };

  if (!goalId) return null;

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-lg flex items-center gap-2">
            {loading ? "Loading..." : editing ? (
              <Input
                value={editTitle}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEditTitle(e.target.value)}
                className="text-lg font-semibold h-auto py-1"
                autoFocus
              />
            ) : (
              <>
                {goal?.title || "Goal Details"}
                {goal && (
                  <button
                    onClick={handleStartEdit}
                    className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                    title="Edit goal"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                )}
              </>
            )}
          </DialogTitle>
          <DialogDescription className="sr-only">
            Goal details and ticket generation
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : error && !goal ? (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <AlertCircle className="h-8 w-8 text-destructive" />
            <p className="text-sm text-destructive">{error}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => goalId && loadGoal(goalId)}
            >
              Try Again
            </Button>
          </div>
        ) : goal ? (
          <div className="space-y-6">
            {/* Goal Info */}
            <div className="space-y-4">
              {editing ? (
                <div className="space-y-3">
                  <div className="space-y-2">
                    <h3 className="text-sm font-medium text-muted-foreground">
                      Description
                    </h3>
                    <Textarea
                      value={editDescription}
                      onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setEditDescription(e.target.value)}
                      placeholder="Describe the goal... (optional)"
                      rows={3}
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <Button size="sm" onClick={handleSaveEdit} disabled={saving || !editTitle.trim()}>
                      {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Save className="h-3.5 w-3.5 mr-1" />}
                      Save
                    </Button>
                    <Button size="sm" variant="ghost" onClick={handleCancelEdit} disabled={saving}>
                      <X className="h-3.5 w-3.5 mr-1" />
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  {goal.description && (
                    <div className="space-y-2">
                      <h3 className="text-sm font-medium text-muted-foreground">
                        Description
                      </h3>
                      <p className="text-sm leading-relaxed whitespace-pre-line">{goal.description}</p>
                    </div>
                  )}
                </>
              )}

              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Calendar className="h-3.5 w-3.5" />
                <span>Created {formatDate(goal.created_at)}</span>
              </div>
            </div>

            {/* Autonomy Settings */}
            <div className="border rounded-lg p-3 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Zap className={cn("h-4 w-4", goal.autonomy_enabled ? "text-amber-500" : "text-muted-foreground")} />
                  <span className="text-sm font-medium">Autonomy</span>
                </div>
                <div className="flex items-center gap-2">
                  {goal.autonomy_enabled && (
                    <span className="text-xs text-muted-foreground">
                      {goal.auto_approval_count} auto-actions
                      {goal.max_auto_approvals ? ` / ${goal.max_auto_approvals} max` : ""}
                    </span>
                  )}
                  <Switch
                    checked={goal.autonomy_enabled}
                    onCheckedChange={async (checked) => {
                      try {
                        const updates = checked
                          ? { autonomy_enabled: true, auto_approve_tickets: true, auto_approve_revisions: true, auto_merge: true, auto_approve_followups: true }
                          : { autonomy_enabled: false, auto_approve_tickets: false, auto_approve_revisions: false, auto_merge: false, auto_approve_followups: false };
                        await updateGoal(goalId!, updates);
                        await loadGoal(goalId!);
                        toast.success(checked ? "Autonomy enabled" : "Autonomy disabled");
                      } catch (err) {
                        toast.error(err instanceof Error ? err.message : "Failed to update");
                      }
                    }}
                  />
                </div>
              </div>

              {goal.autonomy_enabled && (
                <div className="space-y-2.5 pl-3 border-l-2 border-amber-500/30">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">Auto-approve tickets</Label>
                    <Switch
                      checked={goal.auto_approve_tickets}
                      onCheckedChange={async (checked) => {
                        try {
                          await updateGoal(goalId!, { auto_approve_tickets: checked });
                          await loadGoal(goalId!);
                        } catch (err) {
                          toast.error(err instanceof Error ? err.message : "Failed to update");
                        }
                      }}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">Auto-approve revisions</Label>
                    <Switch
                      checked={goal.auto_approve_revisions}
                      onCheckedChange={async (checked) => {
                        try {
                          await updateGoal(goalId!, { auto_approve_revisions: checked });
                          await loadGoal(goalId!);
                        } catch (err) {
                          toast.error(err instanceof Error ? err.message : "Failed to update");
                        }
                      }}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">Auto-merge on completion</Label>
                    <Switch
                      checked={goal.auto_merge}
                      onCheckedChange={async (checked) => {
                        try {
                          await updateGoal(goalId!, { auto_merge: checked });
                          await loadGoal(goalId!);
                        } catch (err) {
                          toast.error(err instanceof Error ? err.message : "Failed to update");
                        }
                      }}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">Auto-approve follow-ups</Label>
                    <Switch
                      checked={goal.auto_approve_followups}
                      onCheckedChange={async (checked) => {
                        try {
                          await updateGoal(goalId!, { auto_approve_followups: checked });
                          await loadGoal(goalId!);
                        } catch (err) {
                          toast.error(err instanceof Error ? err.message : "Failed to update");
                        }
                      }}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Cost Tracking */}
            {costLoading ? (
              <div className="border rounded-lg p-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Loading cost data...</span>
                </div>
              </div>
            ) : costData && costData.agent.total_cost_usd > 0 ? (
              <div className="border rounded-lg p-3 space-y-3">
                <div className="flex items-center gap-2">
                  <DollarSign className="h-4 w-4 text-blue-500" />
                  <span className="text-sm font-medium">Cost Tracking</span>
                  <span className="text-xs text-muted-foreground ml-auto">
                    {costData.agent.total_sessions} session{costData.agent.total_sessions !== 1 ? "s" : ""}
                  </span>
                </div>

                {/* Daily spend */}
                <div className="space-y-1.5">
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Today</span>
                    <span className="font-medium">
                      ${costData.budget.daily_spent.toFixed(2)}
                      {costData.budget.daily_budget ? ` / $${costData.budget.daily_budget}` : ""}
                    </span>
                  </div>
                  {costData.budget.daily_budget ? (
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <div
                        className={cn(
                          "h-full transition-all rounded-full",
                          (costData.budget.daily_spent / costData.budget.daily_budget) > 0.8
                            ? "bg-red-500"
                            : (costData.budget.daily_spent / costData.budget.daily_budget) > 0.6
                              ? "bg-amber-500"
                              : "bg-emerald-500"
                        )}
                        style={{
                          width: `${Math.min(100, (costData.budget.daily_spent / costData.budget.daily_budget) * 100)}%`,
                        }}
                      />
                    </div>
                  ) : null}
                </div>

                {/* Weekly spend */}
                <div className="space-y-1.5">
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">This Week</span>
                    <span className="font-medium">
                      ${costData.budget.weekly_spent.toFixed(2)}
                      {costData.budget.weekly_budget ? ` / $${costData.budget.weekly_budget}` : ""}
                    </span>
                  </div>
                  {costData.budget.weekly_budget ? (
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <div
                        className={cn(
                          "h-full transition-all rounded-full",
                          (costData.budget.weekly_spent / costData.budget.weekly_budget) > 0.8
                            ? "bg-red-500"
                            : (costData.budget.weekly_spent / costData.budget.weekly_budget) > 0.6
                              ? "bg-amber-500"
                              : "bg-emerald-500"
                        )}
                        style={{
                          width: `${Math.min(100, (costData.budget.weekly_spent / costData.budget.weekly_budget) * 100)}%`,
                        }}
                      />
                    </div>
                  ) : null}
                </div>

                {/* Total cost */}
                <div className="pt-2 border-t flex justify-between text-xs">
                  <span className="text-muted-foreground">Total Agent Cost</span>
                  <span className="font-semibold">
                    ${costData.agent.total_cost_usd.toFixed(4)}
                  </span>
                </div>

                {costData.budget.warning_threshold_reached && (
                  <div className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
                    <AlertCircle className="h-3.5 w-3.5" />
                    <span>Approaching budget limit</span>
                  </div>
                )}
              </div>
            ) : null}

            {/* Show review UI if we have proposed tickets */}
            {showReview && proposedTickets.length > 0 ? (
              <ProposedTicketsReview
                tickets={proposedTickets}
                goalId={goalId}
                onClose={handleReviewClose}
                onAccepted={handleTicketsAccepted}
              />
            ) : (
              <>
                {/* Generate Tickets Section */}
                <div className="border-t pt-6">
                  <div className="space-y-3">
                    <h3 className="text-sm font-medium">AI Ticket Generation</h3>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      Use AI to analyze this goal and generate proposed tickets with
                      verification commands. The AI will examine the repository structure
                      and create actionable work items.
                    </p>

                    {error && (
                      <div className="flex items-start gap-2 p-3 rounded-md bg-destructive/10 text-destructive text-xs">
                        <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                        <span>{error}</span>
                      </div>
                    )}

                    <div className="flex gap-2">
                      <Button
                        onClick={handleGenerateTickets}
                        disabled={generating}
                        className="flex-1"
                      >
                        {generating ? (
                          <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            Generating...
                          </>
                        ) : (
                          <>
                            <Sparkles className="mr-2 h-4 w-4" />
                            Generate Tickets
                          </>
                        )}
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => setShowReflection(true)}
                        disabled={generating}
                        title="Reflect on existing proposed tickets"
                      >
                        <Lightbulb className="mr-2 h-4 w-4" />
                        Reflect
                      </Button>
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* Reflection Dialog */}
            <ReflectionDialog
              open={showReflection}
              onOpenChange={setShowReflection}
              goalId={goalId}
              goalTitle={goal?.title || ""}
              onPrioritiesUpdated={handlePrioritiesUpdated}
            />

            {/* Ticket Generation Progress Dialog */}
            {goalId && (
              <TicketGenerationProgress
                open={showProgress}
                onOpenChange={setShowProgress}
                goalId={goalId}
                onComplete={handleGenerationComplete}
                onShowTickets={handleShowTickets}
              />
            )}

            {/* Delete Goal */}
            <div className="border-t pt-4">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowDeleteConfirm(true)}
                className="text-destructive hover:text-destructive hover:bg-destructive/10 gap-2"
              >
                <Trash2 className="h-4 w-4" />
                Delete Goal
              </Button>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>

    <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete goal</AlertDialogTitle>
          <AlertDialogDescription>
            Delete &quot;{goal?.title}&quot;? This will also delete all tickets,
            jobs, and data associated with this goal. This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleDeleteGoal}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {deleting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    </>
  );
}

