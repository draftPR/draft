import { useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Loader2, CheckCircle, XCircle, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { config } from "@/config";

interface TicketGenerationProgressProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  goalId: string;
  onComplete: () => void;
}

interface StreamEvent {
  type: "status" | "agent_output" | "ticket" | "complete" | "error";
  message?: string;
  ticket?: {
    id: string;
    title: string;
    priority: number;
  };
  count?: number;
}

export function TicketGenerationProgress({
  open,
  onOpenChange,
  goalId,
  onComplete,
}: TicketGenerationProgressProps) {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [isComplete, setIsComplete] = useState(false);
  const [hasError, setHasError] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!open) {
      // Reset state when dialog closes
      setEvents([]);
      setIsComplete(false);
      setHasError(false);
      return;
    }

    // Connect to SSE endpoint
    const eventSource = new EventSource(
      `${config.backendBaseUrl}/goals/${goalId}/generate-tickets/stream`
    );

    eventSource.onmessage = (event) => {
      const data: StreamEvent = JSON.parse(event.data);
      setEvents((prev) => [...prev, data]);

      if (data.type === "complete") {
        setIsComplete(true);
        timeoutRef.current = setTimeout(() => {
          onComplete();
          onOpenChange(false);
        }, 2000);
      } else if (data.type === "error") {
        setHasError(true);
        timeoutRef.current = setTimeout(() => {
          onOpenChange(false);
        }, 3000);
      }
    };

    eventSource.onerror = (error) => {
      console.error("SSE error:", error);
      setEvents((prev) => [
        ...prev,
        { type: "error", message: "Connection lost. Please try again." },
      ]);
      setHasError(true);
      eventSource.close();
    };

    return () => {
      eventSource.close();
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [open, goalId, onComplete, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {!isComplete && !hasError && (
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
            )}
            {isComplete && <CheckCircle className="h-5 w-5 text-green-600" />}
            {hasError && <XCircle className="h-5 w-5 text-red-600" />}
            Generating Tickets
          </DialogTitle>
          <DialogDescription>
            {isComplete
              ? "Tickets generated successfully!"
              : hasError
              ? "An error occurred during generation"
              : "AI agent is analyzing the codebase and creating tickets..."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 max-h-[400px] overflow-y-auto py-4">
          {events.map((event, idx) => (
            <div
              key={idx}
              className={cn(
                "flex items-start gap-3 p-3 rounded-lg border",
                event.type === "status" && "bg-blue-50 border-blue-200 dark:bg-blue-950/20 dark:border-blue-900",
                event.type === "ticket" && "bg-green-50 border-green-200 dark:bg-green-950/20 dark:border-green-900",
                event.type === "complete" && "bg-green-50 border-green-200 dark:bg-green-950/20 dark:border-green-900",
                event.type === "error" && "bg-red-50 border-red-200 dark:bg-red-950/20 dark:border-red-900",
                event.type === "agent_output" && "bg-gray-50 border-gray-200 dark:bg-gray-900 dark:border-gray-800"
              )}
            >
              <div className="flex-shrink-0 mt-0.5">
                {event.type === "status" && (
                  <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                )}
                {event.type === "ticket" && (
                  <CheckCircle className="h-4 w-4 text-green-600" />
                )}
                {event.type === "complete" && (
                  <CheckCircle className="h-4 w-4 text-green-600" />
                )}
                {event.type === "error" && (
                  <XCircle className="h-4 w-4 text-red-600" />
                )}
                {event.type === "agent_output" && (
                  <AlertCircle className="h-4 w-4 text-gray-600" />
                )}
              </div>

              <div className="flex-1 min-w-0">
                {event.type === "status" && (
                  <p className="text-sm text-blue-900 dark:text-blue-100">
                    {event.message}
                  </p>
                )}
                {event.type === "ticket" && event.ticket && (
                  <div>
                    <p className="text-sm font-medium text-green-900 dark:text-green-100">
                      Created Ticket
                    </p>
                    <p className="text-sm text-green-700 dark:text-green-300 mt-1">
                      {event.ticket.title}
                    </p>
                    <p className="text-xs text-green-600 dark:text-green-400 mt-0.5">
                      Priority: {event.ticket.priority}
                    </p>
                  </div>
                )}
                {event.type === "complete" && (
                  <p className="text-sm font-medium text-green-900 dark:text-green-100">
                    ✓ Generation complete! Created {event.count} ticket(s)
                  </p>
                )}
                {event.type === "error" && (
                  <p className="text-sm text-red-900 dark:text-red-100">
                    {event.message}
                  </p>
                )}
                {event.type === "agent_output" && (
                  <p className="text-xs font-mono text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                    {event.message}
                  </p>
                )}
              </div>
            </div>
          ))}

          {events.length === 0 && (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin" />
              <span className="ml-2 text-sm">Connecting...</span>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
