import { useState, useCallback } from "react";
import { config } from "@/config";
import { KanbanBoard } from "@/components/KanbanBoard";
import { CreateGoalDialog } from "@/components/CreateGoalDialog";
import { CreateTicketDialog } from "@/components/CreateTicketDialog";
import { Toaster } from "@/components/ui/sonner";

function App() {
  const [goalDialogOpen, setGoalDialogOpen] = useState(false);
  const [ticketDialogOpen, setTicketDialogOpen] = useState(false);
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
            <nav className="flex items-center gap-3">
              <button className="text-sm text-muted-foreground hover:text-foreground">
                🔍
              </button>
              <input 
                type="text" 
                placeholder="Search Vibe Kanban Website..." 
                className="text-xs bg-muted/50 border border-border rounded px-3 py-1.5 w-64 focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <button className="text-sm text-muted-foreground hover:text-foreground">⚙️</button>
              <button className="text-sm text-muted-foreground hover:text-foreground">📋</button>
              <button className="text-sm text-muted-foreground hover:text-foreground">✚</button>
              <button className="text-sm text-muted-foreground hover:text-foreground">☰</button>
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

      {/* Toast notifications */}
      <Toaster richColors position="bottom-right" />
    </div>
  );
}

export default App;
