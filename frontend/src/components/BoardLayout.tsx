/**
 * BoardLayout -- wraps KanbanBoard and TicketDetailPanel side by side.
 *
 * When a ticket is selected, the detail panel appears on the right
 * and the board shrinks to make room.
 *
 * Supports deep-linking: /boards/:boardId/tickets/:ticketId will
 * auto-open the ticket detail panel on mount.
 */

import { useEffect } from "react";
import { useParams } from "react-router";
import { KanbanBoard } from "@/components/KanbanBoard";
import { TicketDetailPanel } from "@/components/TicketDetailPanel";
import { useTicketSelectionStore } from "@/stores/ticketStore";
import { useBoardStore } from "@/stores/boardStore";

export function BoardLayout() {
  const { selectedTicketId, detailDrawerOpen, selectTicket } = useTicketSelectionStore();
  const { boardId: urlBoardId, ticketId: urlTicketId } = useParams();
  const { setCurrentBoardId } = useBoardStore();

  // Sync URL params to stores on mount for deep-linking
  useEffect(() => {
    if (urlBoardId) {
      setCurrentBoardId(urlBoardId);
    }
  }, [urlBoardId, setCurrentBoardId]);

  useEffect(() => {
    if (urlTicketId && urlTicketId !== selectedTicketId) {
      selectTicket(urlTicketId);
    }
  }, [urlTicketId, selectedTicketId, selectTicket]);
  const isOpen = detailDrawerOpen && !!selectedTicketId;

  if (!isOpen) {
    return <KanbanBoard />;
  }

  return (
    <div className="flex gap-0 min-h-[calc(100vh-120px)]">
      {/* Board - takes remaining space */}
      <div className="flex-1 min-w-0 overflow-x-auto">
        <KanbanBoard />
      </div>

      {/* Detail panel - fixed width */}
      <div className="w-[420px] flex-shrink-0 border-l border-border">
        <TicketDetailPanel />
      </div>
    </div>
  );
}
