import { useState, useCallback } from "react";
import { config } from "@/config";
import { KanbanBoard } from "@/components/KanbanBoard";
import { CreateGoalDialog } from "@/components/CreateGoalDialog";
import { CreateTicketDialog } from "@/components/CreateTicketDialog";
import { GoalsListDialog } from "@/components/GoalsListDialog";
import { QueueStatusDialog } from "@/components/QueueStatusDialog";
import { DebugPanel } from "@/components/DebugPanel";
import { Toaster } from "@/components/ui/sonner";
import { Button } from "@/components/ui/button";
import { Target, Plus, Activity, Bug } from "lucide-react";

function App() {
  const [goalDialogOpen, setGoalDialogOpen] = useState(false);
  const [ticketDialogOpen, setTicketDialogOpen] = useState(false);
  const [goalsListOpen, setGoalsListOpen] = useState(false);
  const [queueStatusOpen, setQueueStatusOpen] = useState(false);
  const [debugPanelOpen, setDebugPanelOpen] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const refreshBoard = useCallback(() => {
    setRefreshTrigger((prev) => prev + 1);
  }, []);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card sticky top-0 z-40 shadow-sm">
        <div className="container mx-auto px-6 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h1 className="text-base font-bold text-foreground uppercase tracking-wider">
                {config.appName}
              </h1>
            </div>
            <nav className="flex items-center gap-2">
              <Button
                variant={debugPanelOpen ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setDebugPanelOpen(!debugPanelOpen)}
                className="h-8"
                title="Debug Panel - Live logs and system status"
              >
                <Bug className="h-4 w-4 mr-1.5" />
                Debug
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setQueueStatusOpen(true)}
                className="h-8"
              >
                <Activity className="h-4 w-4 mr-1.5" />
                Activity
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setGoalsListOpen(true)}
                className="h-8"
              >
                <Target className="h-4 w-4 mr-1.5" />
                Goals
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setGoalDialogOpen(true)}
                className="h-8"
              >
                <Plus className="h-4 w-4 mr-1.5" />
                New Goal
              </Button>
              <Button
                variant="default"
                size="sm"
                onClick={() => setTicketDialogOpen(true)}
                className="h-8"
              >
                <Plus className="h-4 w-4 mr-1.5" />
                New Ticket
              </Button>
            </nav>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-4">
        <KanbanBoard refreshTrigger={refreshTrigger} />
      </main>

      {/* Dialogs */}
      <CreateGoalDialog
        open={goalDialogOpen}
        onOpenChange={setGoalDialogOpen}
        onSuccess={refreshBoard}
      />
      <CreateTicketDialog
        open={ticketDialogOpen}
        onOpenChange={setTicketDialogOpen}
        onSuccess={refreshBoard}
      />
      <GoalsListDialog
        open={goalsListOpen}
        onOpenChange={setGoalsListOpen}
        onBoardRefresh={refreshBoard}
      />
      <QueueStatusDialog
        open={queueStatusOpen}
        onOpenChange={setQueueStatusOpen}
      />

      {/* Debug Panel */}
      <DebugPanel
        isOpen={debugPanelOpen}
        onClose={() => setDebugPanelOpen(false)}
      />

      {/* Toast notifications */}
      <Toaster richColors position="bottom-right" />
    </div>
  );
}

export default App;
