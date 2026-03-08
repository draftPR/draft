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
import { GoalDetailDialog } from "@/components/GoalDetailDialog";
import { fetchGoals, deleteGoal } from "@/services/api";
import type { Goal } from "@/types/api";
import { useBoard } from "@/contexts/BoardContext";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  Loader2,
  AlertCircle,
  Target,
  Calendar,
  ChevronRight,
  Sparkles,
  Zap,
  Trash2,
} from "lucide-react";

interface GoalsListDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onBoardRefresh?: () => void;
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export function GoalsListDialog({
  open,
  onOpenChange,
  onBoardRefresh,
}: GoalsListDialogProps) {
  const { currentBoard } = useBoard();
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedGoalId, setSelectedGoalId] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [goalToDelete, setGoalToDelete] = useState<Goal | null>(null);
  const [deletingGoalId, setDeletingGoalId] = useState<string | null>(null);

  const loadGoals = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchGoals(currentBoard?.id);
      setGoals(response.goals);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load goals";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [currentBoard?.id]);

  useEffect(() => {
    if (open) {
      loadGoals();
    }
  }, [open, loadGoals]);

  const handleGoalClick = (goalId: string) => {
    setSelectedGoalId(goalId);
    setDetailOpen(true);
  };

  const handleTicketsAccepted = () => {
    setDetailOpen(false);
    setSelectedGoalId(null);
    onBoardRefresh?.();
    // Close the goals list dialog too — user goes straight to the board
    onOpenChange(false);
  };

  const handleGoalDeleted = () => {
    setDetailOpen(false);
    setSelectedGoalId(null);
    loadGoals();
    onBoardRefresh?.();
  };

  const handleInlineDelete = async () => {
    if (!goalToDelete) return;
    setDeletingGoalId(goalToDelete.id);
    try {
      await deleteGoal(goalToDelete.id);
      toast.success("Goal deleted successfully");
      setGoalToDelete(null);
      loadGoals();
      onBoardRefresh?.();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete goal";
      toast.error(message);
    } finally {
      setDeletingGoalId(null);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[600px] max-h-[80vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Target className="h-5 w-5" />
              Goals
            </DialogTitle>
            <DialogDescription>
              Select a goal to view details and generate AI-powered tickets.
            </DialogDescription>
          </DialogHeader>

          <div className="mt-2">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : error ? (
              <div className="flex flex-col items-center gap-3 py-8 text-center">
                <AlertCircle className="h-8 w-8 text-destructive" />
                <p className="text-sm text-destructive">{error}</p>
                <Button variant="outline" size="sm" onClick={loadGoals}>
                  Try Again
                </Button>
              </div>
            ) : goals.length === 0 ? (
              <div className="flex flex-col items-center gap-3 py-8 text-center">
                <Target className="h-10 w-10 text-muted-foreground/50" />
                <div>
                  <p className="text-sm font-medium">No goals yet</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Create a goal to start generating tickets with AI
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-2 max-h-[400px] overflow-y-auto pr-4">
                {goals.map((goal) => (
                  <button
                    key={goal.id}
                    onClick={() => handleGoalClick(goal.id)}
                    className={cn(
                      "w-full text-left p-4 rounded-lg border transition-colors",
                      "hover:bg-muted/50 hover:border-primary/30",
                      "focus:outline-none focus:ring-2 focus:ring-primary/20"
                    )}
                  >
                    <div className="flex items-start gap-4">
                      <div className="flex-1 min-w-0 overflow-hidden">
                        <h3 className="text-sm font-medium truncate pr-4">
                          {goal.title}
                        </h3>
                        {goal.description && (
                          <p className="text-xs text-muted-foreground mt-1 line-clamp-2 pr-4">
                            {goal.description}
                          </p>
                        )}
                        <div className="flex items-center gap-1.5 mt-2 text-xs text-muted-foreground">
                          <Calendar className="h-3 w-3 flex-shrink-0" />
                          <span>{formatDate(goal.created_at)}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0 pr-1">
                        {goal.autonomy_enabled && (
                          <div className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400" title="Autonomy enabled">
                            <Zap className="h-3.5 w-3.5" />
                            <span>Auto</span>
                          </div>
                        )}
                        <div className="flex items-center gap-1 text-xs text-primary">
                          <Sparkles className="h-3.5 w-3.5" />
                          <span>AI</span>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setGoalToDelete(goal);
                          }}
                          disabled={deletingGoalId === goal.id}
                          className="p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                          title="Delete goal"
                        >
                          {deletingGoalId === goal.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5" />
                          )}
                        </button>
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Goal Detail Dialog */}
      <GoalDetailDialog
        goalId={selectedGoalId}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        onTicketsAccepted={handleTicketsAccepted}
        onGoalDeleted={handleGoalDeleted}
      />

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!goalToDelete} onOpenChange={(open) => !open && setGoalToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete goal</AlertDialogTitle>
            <AlertDialogDescription>
              Delete &quot;{goalToDelete?.title}&quot;? This will also delete all tickets,
              jobs, and data associated with this goal. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleInlineDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deletingGoalId ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

