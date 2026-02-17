import { useEffect } from "react";
import { useBoardUpdates } from "./useBoardUpdates";
import { useNotificationStore } from "@/stores/notificationStore";

/**
 * Bridges WebSocket board updates to the notification store.
 * Call this in AppLayout to capture real-time events.
 */
export function useNotificationBridge(boardId: string | null | undefined) {
  const { subscribe } = useBoardUpdates(boardId);
  const addNotification = useNotificationStore((s) => s.addNotification);

  useEffect(() => {
    if (!boardId) return;

    const unsubscribe = subscribe((message) => {
      if (message.type === "job_completed") {
        const success = message.data?.status === "SUCCEEDED";
        addNotification({
          type: success ? "success" : "error",
          title: success ? "Job completed" : "Job failed",
          description: message.ticket_id
            ? `Ticket ${message.ticket_id.slice(0, 8)}...`
            : undefined,
          ticketId: message.ticket_id,
        });
      }

      if (message.type === "ticket_update" && message.data) {
        const state = message.data.state as string | undefined;
        if (state === "NEEDS_HUMAN") {
          addNotification({
            type: "warning",
            title: "Ticket needs review",
            description: (message.data.title as string) || `Ticket ${message.ticket_id?.slice(0, 8)}...`,
            ticketId: message.ticket_id,
          });
        } else if (state === "BLOCKED") {
          addNotification({
            type: "error",
            title: "Ticket blocked",
            description: (message.data.title as string) || `Ticket ${message.ticket_id?.slice(0, 8)}...`,
            ticketId: message.ticket_id,
          });
        } else if (state === "DONE") {
          addNotification({
            type: "success",
            title: "Ticket completed",
            description: (message.data.title as string) || `Ticket ${message.ticket_id?.slice(0, 8)}...`,
            ticketId: message.ticket_id,
          });
        }
      }
    });

    return unsubscribe;
  }, [boardId, subscribe, addNotification]);
}
