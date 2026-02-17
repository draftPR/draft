import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { createGoal } from "@/services/api";
import { useBoard } from "@/contexts/BoardContext";
import { toast } from "sonner";
import { Loader2, ChevronDown, ChevronRight, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

interface CreateGoalDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

export function CreateGoalDialog({
  open,
  onOpenChange,
  onSuccess,
}: CreateGoalDialogProps) {
  const { currentBoard } = useBoard();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [showAutonomy, setShowAutonomy] = useState(false);

  // Autonomy settings
  const [autonomyEnabled, setAutonomyEnabled] = useState(false);
  const [autoApproveTickets, setAutoApproveTickets] = useState(false);
  const [autoApproveRevisions, setAutoApproveRevisions] = useState(false);
  const [autoMerge, setAutoMerge] = useState(false);
  const [autoApproveFollowups, setAutoApproveFollowups] = useState(false);
  const [maxAutoApprovals, setMaxAutoApprovals] = useState<string>("");

  const handleMasterToggle = (enabled: boolean) => {
    setAutonomyEnabled(enabled);
    if (enabled) {
      setAutoApproveTickets(true);
      setAutoApproveRevisions(true);
      setAutoMerge(true);
      setAutoApproveFollowups(true);
    } else {
      setAutoApproveTickets(false);
      setAutoApproveRevisions(false);
      setAutoMerge(false);
      setAutoApproveFollowups(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (!title.trim()) {
      setErrors({ title: "Title is required" });
      return;
    }

    setLoading(true);
    try {
      await createGoal({
        title: title.trim(),
        description: description.trim() || null,
        board_id: currentBoard?.id ?? null,
        autonomy_enabled: autonomyEnabled,
        auto_approve_tickets: autoApproveTickets,
        auto_approve_revisions: autoApproveRevisions,
        auto_merge: autoMerge,
        auto_approve_followups: autoApproveFollowups,
        max_auto_approvals: maxAutoApprovals ? parseInt(maxAutoApprovals, 10) : null,
      });
      toast.success(
        autonomyEnabled ? "Goal created with full autonomy" : "Goal created successfully"
      );
      resetForm();
      onOpenChange(false);
      onSuccess?.();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create goal";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setTitle("");
    setDescription("");
    setErrors({});
    setShowAutonomy(false);
    setAutonomyEnabled(false);
    setAutoApproveTickets(false);
    setAutoApproveRevisions(false);
    setAutoMerge(false);
    setAutoApproveFollowups(false);
    setMaxAutoApprovals("");
  };

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      resetForm();
    }
    onOpenChange(isOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Create New Goal</DialogTitle>
            <DialogDescription>
              Goals help organize related tickets together. Create a goal to
              start tracking work items.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="goal-title">Title</Label>
              <Input
                id="goal-title"
                placeholder="Enter goal title..."
                value={title}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => { setTitle(e.target.value); setErrors((prev) => { const next = { ...prev }; delete next.title; return next; }); }}
                disabled={loading}
                autoFocus
                className={cn(errors.title && "border-destructive")}
              />
              {errors.title && <p className="text-xs text-destructive mt-1">{errors.title}</p>}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="goal-description">Description</Label>
              <Textarea
                id="goal-description"
                placeholder="Describe the goal... (optional)"
                value={description}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setDescription(e.target.value)}
                disabled={loading}
                rows={3}
              />
            </div>

            {/* Autonomy Section */}
            <div className="border rounded-lg">
              <button
                type="button"
                className="flex items-center justify-between w-full p-3 text-sm font-medium text-left hover:bg-muted/50 rounded-lg"
                onClick={() => setShowAutonomy(!showAutonomy)}
              >
                <span className="flex items-center gap-2">
                  <Zap className="h-4 w-4 text-amber-500" />
                  Full Autonomy Mode
                </span>
                {showAutonomy ? (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                )}
              </button>

              {showAutonomy && (
                <div className="px-3 pb-3 space-y-3">
                  <p className="text-xs text-muted-foreground">
                    Enable autonomous execution. The system will decompose, execute, verify,
                    approve, and merge changes automatically with safety rails.
                  </p>

                  <div className="flex items-center justify-between">
                    <Label htmlFor="autonomy-master" className="text-sm font-medium">
                      Enable Autonomy
                    </Label>
                    <Switch
                      id="autonomy-master"
                      checked={autonomyEnabled}
                      onCheckedChange={handleMasterToggle}
                      disabled={loading}
                    />
                  </div>

                  {autonomyEnabled && (
                    <div className="space-y-2.5 pl-3 border-l-2 border-amber-500/30">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="auto-tickets" className="text-xs">
                          Auto-approve tickets
                        </Label>
                        <Switch
                          id="auto-tickets"
                          checked={autoApproveTickets}
                          onCheckedChange={setAutoApproveTickets}
                          disabled={loading}
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <Label htmlFor="auto-revisions" className="text-xs">
                          Auto-approve revisions
                        </Label>
                        <Switch
                          id="auto-revisions"
                          checked={autoApproveRevisions}
                          onCheckedChange={setAutoApproveRevisions}
                          disabled={loading}
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <Label htmlFor="auto-merge" className="text-xs">
                          Auto-merge on completion
                        </Label>
                        <Switch
                          id="auto-merge"
                          checked={autoMerge}
                          onCheckedChange={setAutoMerge}
                          disabled={loading}
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <Label htmlFor="auto-followups" className="text-xs">
                          Auto-approve follow-ups
                        </Label>
                        <Switch
                          id="auto-followups"
                          checked={autoApproveFollowups}
                          onCheckedChange={setAutoApproveFollowups}
                          disabled={loading}
                        />
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <Label htmlFor="max-approvals" className="text-xs whitespace-nowrap">
                          Max auto-approvals
                        </Label>
                        <Input
                          id="max-approvals"
                          type="number"
                          min="1"
                          placeholder="Unlimited"
                          value={maxAutoApprovals}
                          onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                            setMaxAutoApprovals(e.target.value)
                          }
                          disabled={loading}
                          className="w-24 h-7 text-xs"
                        />
                      </div>
                    </div>
                  )}

                  {autonomyEnabled && (
                    <p className="text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 p-2 rounded">
                      Safety rails: Diffs over 500 lines, sensitive files (.env, .pem, secrets),
                      and failed verification will still require human review.
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create Goal
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
