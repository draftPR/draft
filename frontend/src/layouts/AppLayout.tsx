/**
 * AppLayout -- main application shell with header, dialogs, and outlet.
 *
 * Replaces the monolithic App.tsx. Uses Zustand stores for UI state
 * and React Router Outlet for page content.
 */

import { useState, useCallback, useEffect, useMemo } from "react";
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
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { useBackendStatus } from "@/hooks/useBackendStatus";
import { useNotificationBridge } from "@/hooks/useNotificationBridge";
import { Toaster } from "@/components/ui/sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import {
  Target,
  Plus,
  Bug,
  Settings,
  Keyboard,
  FolderGit2,
  Wifi,
  WifiOff,
  Loader2,
} from "lucide-react";
import { useAppShortcuts } from "@/hooks/useKeyboardShortcuts";
import { useUIStore } from "@/stores/uiStore";
import { useTicketSelectionStore } from "@/stores/ticketStore";
import { useBoard } from "@/contexts/BoardContext";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/hooks/queryKeys";
import { useBoardViewQuery } from "@/hooks/useQueries";


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

  // Notification bridge + WS status
  const { wsStatus } = useNotificationBridge(currentBoard?.id);

  // Ticket selection for keyboard nav
  const { selectTicket, selectedTicketId } = useTicketSelectionStore();

  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const refreshBoard = useCallback(() => {
    setRefreshTrigger((prev) => prev + 1);
    queryClient.invalidateQueries({ queryKey: queryKeys.boards.all });
  }, [queryClient]);

  // Board data for keyboard navigation (shares cache with KanbanBoard)
  const { data: boardData } = useBoardViewQuery(currentBoard?.id, false);

  // Build flat ticket list for j/k navigation
  const allTicketIds = useMemo(
    () => boardData?.columns?.flatMap((col) => col.tickets.map((t) => t.id)) ?? [],
    [boardData?.columns],
  );

  const navigateTickets = useCallback(
    (direction: "up" | "down") => {
      if (allTicketIds.length === 0) return;
      const currentIdx = selectedTicketId
        ? allTicketIds.indexOf(selectedTicketId)
        : -1;
      let nextIdx: number;
      if (direction === "down") {
        nextIdx = currentIdx < allTicketIds.length - 1 ? currentIdx + 1 : 0;
      } else {
        nextIdx = currentIdx > 0 ? currentIdx - 1 : allTicketIds.length - 1;
      }
      selectTicket(allTicketIds[nextIdx]);
    },
    [allTicketIds, selectedTicketId, selectTicket],
  );

  // Keyboard shortcuts
  useAppShortcuts({
    onNewTicket: () => ui.setTicketDialogOpen(true),
    onRefresh: refreshBoard,
    onGoToBoard: () => {
      ui.setDashboardOpen(false);
      navigate("/");
    },
    onHelp: () => ui.setShortcutsHelpOpen(true),
    onNavigateDown: () => navigateTickets("down"),
    onNavigateUp: () => navigateTickets("up"),
    onSelect: () => {
      if (selectedTicketId && currentBoard?.id) {
        navigate(`/boards/${currentBoard.id}/tickets/${selectedTicketId}`);
      }
    },
  });

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
            </div>
            <nav className="flex items-center gap-2">
              {/* WebSocket connection status */}
              {currentBoard && (
                <div
                  className="flex items-center gap-1.5 px-2 h-8 text-xs text-muted-foreground"
                  title={`WebSocket: ${wsStatus}`}
                >
                  {wsStatus === "connected" ? (
                    <Wifi className="h-3.5 w-3.5 text-emerald-500" />
                  ) : wsStatus === "connecting" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-500" />
                  ) : (
                    <WifiOff className="h-3.5 w-3.5 text-destructive" />
                  )}
                </div>
              )}
              <ThemeSwitcher variant="buttons" />
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
        <ErrorBoundary>
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
        </ErrorBoundary>
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
