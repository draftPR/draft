/**
 * AppLayout -- main application shell with header, dialogs, and outlet.
 *
 * Replaces the monolithic App.tsx. Uses Zustand stores for UI state
 * and React Router Outlet for page content.
 */

import { useState, useCallback, useEffect } from "react";
import { Outlet, useParams, useNavigate, useLocation } from "react-router";
import { motion, AnimatePresence } from "framer-motion";
import { config } from "@/config";
import { BoardSelector } from "@/components/BoardSelector";
import { RepoDiscoveryDialog } from "@/components/RepoDiscoveryDialog";
import { CreateGoalDialog } from "@/components/CreateGoalDialog";
import { CreateTicketDialog } from "@/components/CreateTicketDialog";
import { BoardSettingsDialog } from "@/components/BoardSettingsDialog";
import { GoalsListDialog } from "@/components/GoalsListDialog";
import { QueueStatusDialog } from "@/components/QueueStatusDialog";
import { DebugPanel } from "@/components/DebugPanel";
import { SprintDashboard } from "@/components/SprintDashboard";
import { KeyboardShortcutsHelp } from "@/components/KeyboardShortcutsHelp";
import { WelcomeWalkthrough } from "@/components/WelcomeWalkthrough";
import { NotificationCenter } from "@/components/NotificationCenter";
import { CommandPalette } from "@/components/CommandPalette";
import { BackendOfflineBanner } from "@/components/BackendOfflineBanner";
import { useBackendStatus } from "@/hooks/useBackendStatus";
import { useNotificationBridge } from "@/hooks/useNotificationBridge";
import { Toaster } from "@/components/ui/sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import {
  Target,
  Plus,
  Bug,
  FlaskConical,
  Loader2,
  Settings,
  Keyboard,
  FolderGit2,
} from "lucide-react";
import { createGoal, createTicket } from "@/services/api";
import { toast } from "sonner";
import { useAppShortcuts } from "@/hooks/useKeyboardShortcuts";
import { useUIStore } from "@/stores/uiStore";
import { useBoard } from "@/contexts/BoardContext";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/hooks/queryKeys";

// Test data for quick generation
const TEST_GOAL = {
  title: "Generate Multiplication and Division",
  description:
    "Enable the calculator to perform accurate multiplication and division operations, allowing users to input numbers and receive correct results efficiently. The goal is to support basic arithmetic functionality with proper handling of decimals and edge cases such as division by zero.",
};

const TEST_TICKETS = [
  {
    title: "Implement multiply and divide functions in calculator module",
    description:
      "Create app/utils/calculator.py with multiply() and divide() functions that handle integer and floating point numbers. Include proper type hints and docstrings.",
    priority: 90,
  },
  {
    title:
      "Add comprehensive test coverage for multiply and divide functions",
    description:
      "Create tests/test_calculator.py with unit tests covering normal cases, edge cases (zero, negative numbers), floating point precision, and error handling for division by zero.",
    priority: 70,
  },
  {
    title: "Create API endpoint for calculator operations",
    description:
      "Create app/routers/calculator.py with POST /calculate endpoint that accepts operation type and operands, returning the result. Support multiply and divide operations.",
    priority: 70,
  },
  {
    title:
      "Enhance divide function with robust decimal precision handling",
    description:
      "Enhance the divide function in app/utils/calculator.py to use Python's Decimal module for precise decimal arithmetic. Add configurable precision and rounding modes.",
    priority: 50,
  },
];

export function AppLayout() {
  const backendStatus = useBackendStatus();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const { boardId } = useParams();

  // Zustand UI state
  const ui = useUIStore();

  // Board state (from BoardProvider above us in the tree)
  const { currentBoard, setCurrentBoard } = useBoard();

  // Sync board from URL param
  useEffect(() => {
    if (boardId && boardId !== currentBoard?.id) {
      setCurrentBoard(boardId);
    }
  }, [boardId, currentBoard?.id, setCurrentBoard]);

  // Notification bridge
  useNotificationBridge(currentBoard?.id);

  const [generatingTestData, setGeneratingTestData] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const refreshBoard = useCallback(() => {
    setRefreshTrigger((prev) => prev + 1);
    queryClient.invalidateQueries({ queryKey: queryKeys.boards.all });
  }, [queryClient]);

  // Keyboard shortcuts
  useAppShortcuts({
    onNewTicket: () => ui.setTicketDialogOpen(true),
    onRefresh: refreshBoard,
    onGoToBoard: () => {
      ui.setDashboardOpen(false);
      navigate("/");
    },
    onHelp: () => ui.setShortcutsHelpOpen(true),
  });

  const generateTestData = async () => {
    setGeneratingTestData(true);
    try {
      const goal = await createGoal(TEST_GOAL);
      for (const ticket of TEST_TICKETS) {
        await createTicket({
          goal_id: goal.id,
          title: ticket.title,
          description: ticket.description,
          priority: ticket.priority,
        });
      }
      toast.success(
        `Created goal "${goal.title}" with ${TEST_TICKETS.length} tickets`,
      );
      refreshBoard();
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to generate test data";
      toast.error(message);
    } finally {
      setGeneratingTestData(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Backend offline banner */}
      <BackendOfflineBanner status={backendStatus} />

      {/* Header */}
      <header className="border-b border-border bg-card sticky top-0 z-40 shadow-sm">
        <div className="container mx-auto px-6 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <h1
                className="text-base font-bold text-foreground uppercase tracking-wider cursor-pointer"
                onClick={() => navigate("/")}
              >
                {config.appName}
              </h1>
              <BoardSelector />
              <Button
                variant="outline"
                size="sm"
                onClick={() => ui.setRepoDiscoveryOpen(true)}
                className="h-8"
                title="Discover and add projects"
              >
                <FolderGit2 className="h-4 w-4 mr-1.5" />
                Add Projects
              </Button>
              {currentBoard && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => ui.setBoardSettingsOpen(true)}
                  className="h-8"
                  title="Board Settings"
                >
                  <Settings className="h-4 w-4" />
                </Button>
              )}
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
                variant={ui.debugPanelOpen ? "secondary" : "ghost"}
                size="sm"
                onClick={() => ui.toggleDebugPanel()}
                className="h-8"
                title="Debug Panel - Live logs and system status"
              >
                <Bug className="h-4 w-4 mr-1.5" />
                Debug
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => ui.setGoalsListOpen(true)}
                className="h-8"
              >
                <Target className="h-4 w-4 mr-1.5" />
                Goals
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => ui.setGoalDialogOpen(true)}
                className="h-8"
              >
                <Plus className="h-4 w-4 mr-1.5" />
                New Goal
              </Button>
              <Button
                variant="default"
                size="sm"
                onClick={() => ui.setTicketDialogOpen(true)}
                className="h-8"
              >
                <Plus className="h-4 w-4 mr-1.5" />
                New Ticket
              </Button>
              <NotificationCenter />
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate("/settings")}
                className="h-8"
                title="Settings"
              >
                <Settings className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => ui.setShortcutsHelpOpen(true)}
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
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
          >
            <Outlet context={{ refreshTrigger, refreshBoard, currentBoard }} />
          </motion.div>
        </AnimatePresence>
      </main>

      {/* Dialogs */}
      <CreateGoalDialog
        open={ui.goalDialogOpen}
        onOpenChange={ui.setGoalDialogOpen}
        onSuccess={refreshBoard}
      />
      <CreateTicketDialog
        open={ui.ticketDialogOpen}
        onOpenChange={ui.setTicketDialogOpen}
        onSuccess={refreshBoard}
      />
      <GoalsListDialog
        open={ui.goalsListOpen}
        onOpenChange={ui.setGoalsListOpen}
        onBoardRefresh={refreshBoard}
      />
      <QueueStatusDialog
        open={ui.queueStatusOpen}
        onOpenChange={ui.setQueueStatusOpen}
      />
      <RepoDiscoveryDialog
        open={ui.repoDiscoveryOpen}
        onOpenChange={ui.setRepoDiscoveryOpen}
        onReposAdded={refreshBoard}
      />
      {currentBoard && (
        <BoardSettingsDialog
          open={ui.boardSettingsOpen}
          onOpenChange={ui.setBoardSettingsOpen}
          boardId={currentBoard.id}
          onTicketsDeleted={refreshBoard}
          onBoardDeleted={() => {
            queryClient.invalidateQueries({ queryKey: queryKeys.boards.all });
            navigate("/");
          }}
        />
      )}

      {/* Debug Panel */}
      <DebugPanel
        isOpen={ui.debugPanelOpen}
        onClose={() => ui.setDebugPanelOpen(false)}
      />

      {/* Dashboard Dialog */}
      <Dialog open={ui.dashboardOpen} onOpenChange={ui.setDashboardOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <SprintDashboard />
        </DialogContent>
      </Dialog>

      {/* Keyboard Shortcuts Help */}
      <KeyboardShortcutsHelp
        open={ui.shortcutsHelpOpen}
        onOpenChange={ui.setShortcutsHelpOpen}
      />

      {/* Welcome Walkthrough (auto-opens on first run) */}
      <WelcomeWalkthrough />

      {/* Command Palette (Cmd+K) */}
      <CommandPalette
        commands={[
          {
            id: "new-ticket",
            label: "Create New Ticket",
            description: "Add a new ticket to the board",
            icon: Plus,
            shortcut: "n",
            category: "Actions",
            onSelect: () => ui.setTicketDialogOpen(true),
            keywords: ["add", "ticket", "task"],
          },
          {
            id: "new-goal",
            label: "Create New Goal",
            description: "Define a new development goal",
            icon: Target,
            category: "Actions",
            onSelect: () => ui.setGoalDialogOpen(true),
            keywords: ["add", "goal", "objective"],
          },
          {
            id: "goals",
            label: "View Goals",
            description: "Browse all goals",
            icon: Target,
            category: "Navigation",
            onSelect: () => ui.setGoalsListOpen(true),
          },
          {
            id: "settings",
            label: "Open Settings",
            icon: Settings,
            category: "Navigation",
            onSelect: () => navigate("/settings"),
          },
          {
            id: "debug",
            label: "Toggle Debug Panel",
            icon: Bug,
            category: "Navigation",
            onSelect: () => ui.toggleDebugPanel(),
          },
          {
            id: "refresh",
            label: "Refresh Board",
            description: "Re-fetch all board data",
            category: "Actions",
            onSelect: refreshBoard,
            keywords: ["reload", "update"],
          },
          {
            id: "shortcuts",
            label: "Keyboard Shortcuts",
            icon: Keyboard,
            category: "Help",
            onSelect: () => ui.setShortcutsHelpOpen(true),
          },
        ]}
      />

      {/* Toast notifications */}
      <Toaster richColors position="bottom-right" />
    </div>
  );
}
