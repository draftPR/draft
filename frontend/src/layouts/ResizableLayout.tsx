/**
 * ResizableLayout -- three-panel layout using react-resizable-panels.
 *
 * Panels:
 *   sidebar  -- goals/navigation (collapsible)
 *   main     -- kanban board (always visible)
 *   detail   -- ticket detail / logs (conditionally visible)
 *
 * This is the main content area layout, used inside AppLayout below the header.
 */

import {
  Group,
  Panel,
  Separator,
} from "react-resizable-panels";
import type { ReactNode } from "react";

interface ResizableLayoutProps {
  sidebar?: ReactNode;
  main: ReactNode;
  detail?: ReactNode;
  showSidebar?: boolean;
  showDetail?: boolean;
}

export function ResizableLayout({
  sidebar,
  main,
  detail,
  showSidebar = false,
  showDetail = false,
}: ResizableLayoutProps) {
  return (
    <Group orientation="horizontal" className="h-[calc(100vh-57px)]">
      {/* Sidebar panel */}
      {showSidebar && sidebar && (
        <>
          <Panel
            defaultSize={20}
            minSize={15}
            maxSize={30}
            collapsible
            className="bg-card border-r border-border"
          >
            <div className="h-full overflow-y-auto p-3">{sidebar}</div>
          </Panel>
          <Separator className="w-1.5 bg-border hover:bg-primary/20 transition-colors" />
        </>
      )}

      {/* Main content panel */}
      <Panel defaultSize={showDetail ? 60 : 100} minSize={40}>
        <div className="h-full overflow-y-auto">{main}</div>
      </Panel>

      {/* Detail panel */}
      {showDetail && detail && (
        <>
          <Separator className="w-1.5 bg-border hover:bg-primary/20 transition-colors" />
          <Panel
            defaultSize={35}
            minSize={25}
            maxSize={50}
            collapsible
            className="bg-card border-l border-border"
          >
            <div className="h-full overflow-y-auto">{detail}</div>
          </Panel>
        </>
      )}
    </Group>
  );
}
