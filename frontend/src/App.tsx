import { useState, useCallback } from "react";
import { config } from "@/config";
import { KanbanBoard } from "@/components/KanbanBoard";
import { BoardSelector } from "@/components/BoardSelector";
import { RepoDiscoveryDialog } from "@/components/RepoDiscoveryDialog";
import { CreateGoalDialog } from "@/components/CreateGoalDialog";
import { CreateTicketDialog } from "@/components/CreateTicketDialog";
import { GoalsListDialog } from "@/components/GoalsListDialog";
import { QueueStatusDialog } from "@/components/QueueStatusDialog";
import { DebugPanel } from "@/components/DebugPanel";
import { SprintDashboard } from "@/components/SprintDashboard";
import { SettingsPanel } from "@/components/SettingsPanel";
import { KeyboardShortcutsHelp } from "@/components/KeyboardShortcutsHelp";
import { WelcomeWalkthrough } from "@/components/WelcomeWalkthrough";
import { Toaster } from "@/components/ui/sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
} from "@/components/ui/dialog";
import { Target, Plus, Bug, FlaskConical, Loader2, Settings, Keyboard, FolderGit2 } from "lucide-react";
import { createGoal, createTicket } from "@/services/api";
import { toast } from "sonner";
import { useAppShortcuts } from "@/hooks/useKeyboardShortcuts";
import { BoardProvider } from "@/contexts/BoardContext";

// Test data for quick generation
const TEST_GOAL = {
  title: "Generate Multiplication and Division",
  description: "Enable the calculator to perform accurate multiplication and division operations, allowing users to input numbers and receive correct results efficiently. The goal is to support basic arithmetic functionality with proper handling of decimals and edge cases such as division by zero.",
};

const TEST_TICKETS = [
  {
    title: "Implement multiply and divide functions in calculator module",
    description: "Create app/utils/calculator.py with multiply() and divide() functions that handle integer and floating point numbers. Include proper type hints and docstrings.",
    priority: 90, // P0
  },
  {
    title: "Add comprehensive test coverage for multiply and divide functions",
    description: "Create tests/test_calculator.py with unit tests covering normal cases, edge cases (zero, negative numbers), floating point precision, and error handling for division by zero.",
    priority: 70, // P1
  },
  {
    title: "Create API endpoint for calculator operations",
    description: "Create app/routers/calculator.py with POST /calculate endpoint that accepts operation type and operands, returning the result. Support multiply and divide operations.",
    priority: 70, // P1
  },
  {
    title: "Enhance divide function with robust decimal precision handling",
    description: "Enhance the divide function in app/utils/calculator.py to use Python's Decimal module for precise decimal arithmetic. Add configurable precision and rounding modes.",
    priority: 50, // P2
  },
];

function App() {
  const [goalDialogOpen, setGoalDialogOpen] = useState(false);
  const [ticketDialogOpen, setTicketDialogOpen] = useState(false);
  const [goalsListOpen, setGoalsListOpen] = useState(false);
  const [queueStatusOpen, setQueueStatusOpen] = useState(false);
  const [debugPanelOpen, setDebugPanelOpen] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [shortcutsHelpOpen, setShortcutsHelpOpen] = useState(false);
  const [repoDiscoveryOpen, setRepoDiscoveryOpen] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [generatingTestData, setGeneratingTestData] = useState(false);

  const refreshBoard = useCallback(() => {
    setRefreshTrigger((prev) => prev + 1);
  }, []);

  // Keyboard shortcuts
  useAppShortcuts({
    onNewTicket: () => setTicketDialogOpen(true),
    onRefresh: refreshBoard,
    onGoToBoard: () => {
      setDashboardOpen(false);
      setSettingsOpen(false);
    },
    onHelp: () => setShortcutsHelpOpen(true),
  });

  const generateTestData = async () => {
    setGeneratingTestData(true);
    try {
      // Create the goal first
      const goal = await createGoal(TEST_GOAL);
      
      // Create all tickets for the goal
      for (const ticket of TEST_TICKETS) {
        await createTicket({
          goal_id: goal.id,
          title: ticket.title,
          description: ticket.description,
          priority: ticket.priority,
        });
      }
      
      toast.success(`Created goal "${goal.title}" with ${TEST_TICKETS.length} tickets`);
      refreshBoard();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to generate test data";
      toast.error(message);
    } finally {
      setGeneratingTestData(false);
    }
  };

  return (
    <BoardProvider>
      <div className="min-h-screen bg-background">
        {/* Header */}
        <header className="border-b border-border bg-card sticky top-0 z-40 shadow-sm">
          <div className="container mx-auto px-6 py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <h1 className="text-base font-bold text-foreground uppercase tracking-wider">
                  {config.appName}
                </h1>
                <BoardSelector />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setRepoDiscoveryOpen(true)}
                  className="h-8"
                  title="Discover and add projects"
                >
                  <FolderGit2 className="h-4 w-4 mr-1.5" />
                  Add Projects
                </Button>
              </div>
              <nav className="flex items-center gap-2">
              {import.meta.env.DEV && (
              <Button
                variant="ghost"
                size="sm"
                onClick={generateTestData}
                disabled={generatingTestData}
                className="h-8 text-amber-600 hover:text-amber-700 hover:bg-amber-50"
                title="Generate test goal with multiplication/division tickets"
              >
                {generatingTestData ? (
                  <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                ) : (
                  <FlaskConical className="h-4 w-4 mr-1.5" />
                )}
                Test Data
              </Button>
              )}
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
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSettingsOpen(true)}
                className="h-8"
                title="Settings"
              >
                <Settings className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShortcutsHelpOpen(true)}
                className="h-8"
                title="Keyboard Shortcuts (?)"
              >
                <Keyboard className="h-4 w-4" />
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
      <RepoDiscoveryDialog
        open={repoDiscoveryOpen}
        onOpenChange={setRepoDiscoveryOpen}
        onReposAdded={refreshBoard}
      />

      {/* Debug Panel */}
      <DebugPanel
        isOpen={debugPanelOpen}
        onClose={() => setDebugPanelOpen(false)}
      />

      {/* Dashboard Dialog */}
      <Dialog open={dashboardOpen} onOpenChange={setDashboardOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <SprintDashboard />
        </DialogContent>
      </Dialog>

      {/* Settings Dialog */}
      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto p-0">
          <SettingsPanel />
        </DialogContent>
      </Dialog>

      {/* Keyboard Shortcuts Help */}
      <KeyboardShortcutsHelp
        open={shortcutsHelpOpen}
        onOpenChange={setShortcutsHelpOpen}
      />

      {/* Welcome Walkthrough (auto-opens on first run) */}
      <WelcomeWalkthrough />

      {/* Toast notifications */}
      <Toaster richColors position="bottom-right" />
      </div>
    </BoardProvider>
  );
}

export default App;
