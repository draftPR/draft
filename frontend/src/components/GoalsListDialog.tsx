import { useState, useEffect, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { GoalDetailDialog } from "@/components/GoalDetailDialog";
import { fetchGoals } from "@/services/api";
import type { Goal } from "@/types/api";
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
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedGoalId, setSelectedGoalId] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const loadGoals = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchGoals();
      setGoals(response.goals);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load goals";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

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
    // Optionally close the goals list too
    // onOpenChange(false);
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
      />
    </>
  );
}

