import { useState, useEffect, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ProposedTicketsReview } from "@/components/ProposedTicketsReview";
import { ReflectionDialog } from "@/components/ReflectionDialog";
import { TicketGenerationProgress } from "@/components/TicketGenerationProgress";
import { fetchGoal } from "@/services/api";
import type { Goal, ProposedTicket } from "@/types/api";
import { toast } from "sonner";
import { Loader2, Sparkles, AlertCircle, Calendar, Lightbulb } from "lucide-react";

interface GoalDetailDialogProps {
  goalId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onTicketsAccepted?: () => void;
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
}: GoalDetailDialogProps) {
  const [goal, setGoal] = useState<Goal | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposedTickets, setProposedTickets] = useState<ProposedTicket[]>([]);
  const [showReview, setShowReview] = useState(false);
  const [showReflection, setShowReflection] = useState(false);
  const [showProgress, setShowProgress] = useState(false);

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

  useEffect(() => {
    if (goalId && open) {
      loadGoal(goalId);
      // Reset state when opening
      setProposedTickets([]);
      setShowReview(false);
    }
  }, [goalId, open, loadGoal]);

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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-lg">
            {loading ? "Loading..." : goal?.title || "Goal Details"}
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
              {goal.description && (
                <div className="space-y-2">
                  <h3 className="text-sm font-medium text-muted-foreground">
                    Description
                  </h3>
                  <p className="text-sm leading-relaxed">{goal.description}</p>
                </div>
              )}

              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Calendar className="h-3.5 w-3.5" />
                <span>Created {formatDate(goal.created_at)}</span>
              </div>
            </div>

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
              />
            )}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

