import { useEffect, useState, useCallback } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { EvidenceList } from "@/components/EvidenceList";
import { fetchTicketEvents, fetchTicketEvidence } from "@/services/api";
import type { Ticket, TicketEvent, Evidence } from "@/types/api";
import {
  STATE_DISPLAY_NAMES,
  EventType,
} from "@/types/api";
import { cn } from "@/lib/utils";
import {
  ArrowRight,
  Loader2,
  AlertCircle,
  FlaskConical,
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
  const [loading, setLoading] = useState(false);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  useEffect(() => {
    if (ticket && open) {
      loadEvents(ticket.id);
      loadEvidence(ticket.id);
    }
    // Only re-fetch when ticket ID changes or drawer opens, not on ticket object reference changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticket?.id, open, loadEvents, loadEvidence]);

  if (!ticket) return null;

  const priority = getPriorityDisplay(ticket.priority);

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
