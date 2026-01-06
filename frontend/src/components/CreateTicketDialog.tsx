import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { createTicket, fetchGoals } from "@/services/api";
import { ActorType, type Goal } from "@/types/api";
import { toast } from "sonner";
import { Loader2, AlertCircle } from "lucide-react";

interface CreateTicketDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

export function CreateTicketDialog({
  open,
  onOpenChange,
  onSuccess,
}: CreateTicketDialogProps) {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [goalsLoading, setGoalsLoading] = useState(false);
  const [goalsError, setGoalsError] = useState<string | null>(null);

  const [goalId, setGoalId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("");
  const [loading, setLoading] = useState(false);

  // Fetch goals when dialog opens
  useEffect(() => {
    if (open) {
      setGoalsLoading(true);
      setGoalsError(null);
      fetchGoals()
        .then((response) => {
          setGoals(response.goals);
          // Auto-select if only one goal
          if (response.goals.length === 1) {
            setGoalId(response.goals[0].id);
          }
        })
        .catch((err) => {
          setGoalsError(err.message || "Failed to load goals");
        })
        .finally(() => {
          setGoalsLoading(false);
        });
    }
  }, [open]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (!goalId) {
      toast.error("Please select a goal");
      return;
    }

    if (!title.trim()) {
      toast.error("Title is required");
      return;
    }

    setLoading(true);
    try {
      await createTicket({
        goal_id: goalId,
        title: title.trim(),
        description: description.trim() || null,
        priority: priority ? parseInt(priority, 10) : null,
        actor_type: ActorType.HUMAN,
      });
      toast.success("Ticket created successfully");
      resetForm();
      onOpenChange(false);
      onSuccess?.();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create ticket";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setGoalId("");
    setTitle("");
    setDescription("");
    setPriority("");
  };

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      resetForm();
    }
    onOpenChange(isOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Create New Ticket</DialogTitle>
            <DialogDescription>
              Create a ticket to track a specific task. Tickets are linked to
              goals and follow a workflow through different states.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            {/* Goal Selection */}
            <div className="grid gap-2">
              <Label htmlFor="ticket-goal">Goal</Label>
              {goalsLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading goals...
                </div>
              ) : goalsError ? (
                <div className="flex items-center gap-2 text-sm text-destructive py-2">
                  <AlertCircle className="h-4 w-4" />
                  {goalsError}
                </div>
              ) : goals.length === 0 ? (
                <div className="text-sm text-muted-foreground py-2">
                  No goals found. Please create a goal first.
                </div>
              ) : (
                <Select value={goalId} onValueChange={setGoalId} disabled={loading}>
                  <SelectTrigger id="ticket-goal">
                    <SelectValue placeholder="Select a goal..." />
                  </SelectTrigger>
                  <SelectContent>
                    {goals.map((goal) => (
                      <SelectItem key={goal.id} value={goal.id}>
                        {goal.title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            {/* Title */}
            <div className="grid gap-2">
              <Label htmlFor="ticket-title">Title</Label>
              <Input
                id="ticket-title"
                placeholder="Enter ticket title..."
                value={title}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTitle(e.target.value)}
                disabled={loading}
              />
            </div>

            {/* Description */}
            <div className="grid gap-2">
              <Label htmlFor="ticket-description">Description</Label>
              <Textarea
                id="ticket-description"
                placeholder="Describe the ticket... (optional)"
                value={description}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setDescription(e.target.value)}
                disabled={loading}
                rows={3}
              />
            </div>

            {/* Priority */}
            <div className="grid gap-2">
              <Label htmlFor="ticket-priority">Priority (0-100)</Label>
              <Input
                id="ticket-priority"
                type="number"
                min={0}
                max={100}
                placeholder="50 (optional)"
                value={priority}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPriority(e.target.value)}
                disabled={loading}
              />
              <p className="text-xs text-muted-foreground">
                Higher values = higher priority. 75+ = High, 50-74 = Medium, 25-49 = Low
              </p>
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
            <Button
              type="submit"
              disabled={loading || goalsLoading || goals.length === 0}
            >
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create Ticket
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

