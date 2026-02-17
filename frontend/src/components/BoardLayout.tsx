/**
 * BoardLayout -- wraps KanbanBoard and TicketDetailPanel in resizable panels.
 *
 * When a ticket is selected, the detail panel slides in from the right
 * and the board compresses. Uses react-resizable-panels for the resize handle.
 */

import { Panel, Group, Separator } from "react-resizable-panels";
import { KanbanBoard } from "@/components/KanbanBoard";
import { TicketDetailPanel } from "@/components/TicketDetailPanel";
import { useTicketSelectionStore } from "@/stores/ticketStore";

export function BoardLayout() {
  const { selectedTicketId, detailDrawerOpen } = useTicketSelectionStore();
  const isOpen = detailDrawerOpen && !!selectedTicketId;

  return (
    <Group
      orientation="horizontal"
      id="alma-board-layout"
    >
      {/* Board panel */}
      <Panel defaultSize={isOpen ? 65 : 100} minSize={40} id="board-panel">
        <KanbanBoard />
      </Panel>

      {/* Detail panel */}
      {isOpen && (
        <>
          <Separator className="w-[6px] relative group">
            <div className="absolute inset-y-0 left-1/2 w-[1.5px] -translate-x-1/2 bg-border group-hover:bg-primary/40 group-active:bg-primary/60 transition-colors" />
          </Separator>
          <Panel defaultSize={35} minSize={25} maxSize={60} id="detail-panel">
            <TicketDetailPanel />
          </Panel>
        </>
      )}
    </Group>
  );
}
