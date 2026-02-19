/**
 * BoardLayout -- wraps KanbanBoard and TicketDetailPanel side by side.
 *
 * When a ticket is selected, the detail panel appears on the right
 * and the board shrinks to make room.
 */

import { KanbanBoard } from "@/components/KanbanBoard";
import { TicketDetailPanel } from "@/components/TicketDetailPanel";
import { useTicketSelectionStore } from "@/stores/ticketStore";

export function BoardLayout() {
  const { selectedTicketId, detailDrawerOpen } = useTicketSelectionStore();
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
