import { useState } from "react";
import { Button } from "@/components/ui/button";
import { bulkAcceptTickets } from "@/services/api";
import type { ProposedTicket } from "@/types/api";
import { ActorType } from "@/types/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  Check,
  X,
  ChevronDown,
  ChevronRight,
  Loader2,
  Terminal,
  FileText,
  CheckCircle2,
  Sparkles,
  Play,
} from "lucide-react";

interface ProposedTicketsReviewProps {
  tickets: ProposedTicket[];
  goalId: string;
  onClose: () => void;
  onAccepted: () => void;
}

interface TicketSelection {
  [index: number]: boolean;
}

export function ProposedTicketsReview({
  tickets,
  goalId,
  onClose,
  onAccepted,
}: ProposedTicketsReviewProps) {
  const [selected, setSelected] = useState<TicketSelection>(() => {
    // Default all tickets to selected
    const initial: TicketSelection = {};
    tickets.forEach((_, i) => {
      initial[i] = true;
    });
    return initial;
  });
  const [expanded, setExpanded] = useState<{ [index: number]: boolean }>({});
  const [accepting, setAccepting] = useState(false);
  const [queueing, setQueueing] = useState(false);

  const toggleSelect = (index: number) => {
    setSelected((prev) => ({
      ...prev,
      [index]: !prev[index],
    }));
  };

  const toggleExpand = (index: number) => {
    setExpanded((prev) => ({
      ...prev,
      [index]: !prev[index],
    }));
  };

  const selectAll = () => {
    const newSelected: TicketSelection = {};
    tickets.forEach((_, i) => {
      newSelected[i] = true;
    });
    setSelected(newSelected);
  };

  const deselectAll = () => {
    setSelected({});
  };

  const selectedCount = Object.values(selected).filter(Boolean).length;

  const getSelectedTicketIds = () => {
    return Object.entries(selected)
      .filter(([_, isSelected]) => isSelected)
      .map(([index]) => tickets[parseInt(index)].id);
  };

  const handleAccept = async (queueFirst: boolean) => {
    const selectedTicketIds = getSelectedTicketIds();

    if (selectedTicketIds.length === 0) {
      toast.error("No tickets selected");
      return;
    }

    if (queueFirst) {
      setQueueing(true);
    } else {
      setAccepting(true);
    }

    try {
      // Use bulk accept endpoint (single API call)
      const result = await bulkAcceptTickets({
        ticket_ids: selectedTicketIds,
        goal_id: goalId,
        actor_type: ActorType.HUMAN,
        reason: "Accepted from AI-generated proposal",
        queue_first: queueFirst,
      });

      if (result.accepted_count > 0) {
        let message = `Accepted ${result.accepted_count} ticket${result.accepted_count > 1 ? "s" : ""}.`;
        if (result.queued_job_id && result.queued_ticket_id) {
          const queuedTicket = tickets.find(t => t.id === result.queued_ticket_id);
          const ticketTitle = queuedTicket?.title || result.queued_ticket_id;
          message += ` Queued: "${ticketTitle}"`;
        }
        toast.success(message);
      }
      if (result.failed_count > 0) {
        const errors = result.rejected
          .map((r) => r.error)
          .filter(Boolean)
          .join(", ");
        toast.error(
          `Failed to accept ${result.failed_count} ticket${result.failed_count > 1 ? "s" : ""}: ${errors}`
        );
      }

      if (result.accepted_count > 0) {
        onAccepted();
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to accept tickets";
      toast.error(message);
    } finally {
      setAccepting(false);
      setQueueing(false);
    }
  };

  const handleAcceptSelected = () => handleAccept(false);
  const handleAcceptAndQueue = () => handleAccept(true);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          AI-Suggested Tickets ({tickets.length})
        </h3>
        <div className="flex gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={selectAll}
            className="text-xs h-7"
          >
            Select All
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={deselectAll}
            className="text-xs h-7"
          >
            Deselect All
          </Button>
        </div>
      </div>

      {/* Ticket List */}
      <div className="space-y-2 max-h-[400px] overflow-y-auto pr-1">
        {tickets.map((ticket, index) => (
          <div
            key={ticket.id}
            className={cn(
              "border rounded-lg transition-colors",
              selected[index]
                ? "border-primary/50 bg-primary/5"
                : "border-border bg-background"
            )}
          >
            {/* Ticket Header */}
            <div
              className="flex items-start gap-3 p-3 cursor-pointer"
              onClick={() => toggleSelect(index)}
            >
              {/* Checkbox */}
              <div
                className={cn(
                  "mt-0.5 h-5 w-5 rounded border flex items-center justify-center flex-shrink-0 transition-colors",
                  selected[index]
                    ? "bg-primary border-primary text-primary-foreground"
                    : "border-muted-foreground/30"
                )}
              >
                {selected[index] && <Check className="h-3.5 w-3.5" />}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <h4 className="text-sm font-medium leading-snug">
                  {ticket.title}
                </h4>
                <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                  {ticket.description}
                </p>
              </div>

              {/* Expand Button */}
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0 flex-shrink-0"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleExpand(index);
                }}
              >
                {expanded[index] ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
              </Button>
            </div>

            {/* Expanded Details */}
            {expanded[index] && (
              <div className="px-3 pb-3 pt-0 space-y-3 border-t mx-3 mt-1">
                {/* Full Description */}
                <div className="pt-3">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-1.5">
                    <FileText className="h-3.5 w-3.5" />
                    Description
                  </div>
                  <p className="text-xs leading-relaxed whitespace-pre-wrap">
                    {ticket.description}
                  </p>
                </div>

                {/* Verification Commands */}
                {ticket.verification.length > 0 && (
                  <div>
                    <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-1.5">
                      <Terminal className="h-3.5 w-3.5" />
                      Verification Commands
                    </div>
                    <div className="space-y-1">
                      {ticket.verification.map((cmd, i) => (
                        <code
                          key={i}
                          className="block text-xs bg-muted px-2 py-1.5 rounded font-mono"
                        >
                          {cmd}
                        </code>
                      ))}
                    </div>
                  </div>
                )}

                {/* Notes */}
                {ticket.notes && (
                  <div>
                    <div className="text-xs font-medium text-muted-foreground mb-1">
                      Notes
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {ticket.notes}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between pt-2 border-t">
        <div className="text-xs text-muted-foreground">
          {selectedCount} of {tickets.length} selected
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onClose}
            disabled={accepting || queueing}
          >
            <X className="mr-1.5 h-3.5 w-3.5" />
            Cancel
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleAcceptSelected}
            disabled={accepting || queueing || selectedCount === 0}
          >
            {accepting ? (
              <>
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                Accepting...
              </>
            ) : (
              <>
                <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                Accept ({selectedCount})
              </>
            )}
          </Button>
          <Button
            size="sm"
            onClick={handleAcceptAndQueue}
            disabled={accepting || queueing || selectedCount === 0}
            title="Accept tickets and immediately queue the first one for execution"
          >
            {queueing ? (
              <>
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                Queueing...
              </>
            ) : (
              <>
                <Play className="mr-1.5 h-3.5 w-3.5" />
                Accept & Queue
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
