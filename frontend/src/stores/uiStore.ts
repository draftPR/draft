/**
 * UI store -- replaces 9 useState booleans in App.tsx
 *
 * Manages dialog/panel open states.
 */

import { create } from "zustand";

interface UIState {
  goalDialogOpen: boolean;
  ticketDialogOpen: boolean;
  goalsListOpen: boolean;
  queueStatusOpen: boolean;
  debugPanelOpen: boolean;
  dashboardOpen: boolean;
  shortcutsHelpOpen: boolean;
  repoDiscoveryOpen: boolean;
  boardSettingsOpen: boolean;
  boardSettingsTab: string;

  setGoalDialogOpen: (open: boolean) => void;
  setTicketDialogOpen: (open: boolean) => void;
  setGoalsListOpen: (open: boolean) => void;
  setQueueStatusOpen: (open: boolean) => void;
  setDebugPanelOpen: (open: boolean) => void;
  setDashboardOpen: (open: boolean) => void;
  setShortcutsHelpOpen: (open: boolean) => void;
  setRepoDiscoveryOpen: (open: boolean) => void;
  setBoardSettingsOpen: (open: boolean, tab?: string) => void;
  toggleDebugPanel: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  goalDialogOpen: false,
  ticketDialogOpen: false,
  goalsListOpen: false,
  queueStatusOpen: false,
  debugPanelOpen: false,
  dashboardOpen: false,
  shortcutsHelpOpen: false,
  repoDiscoveryOpen: false,
  boardSettingsOpen: false,
  boardSettingsTab: "execution",

  setGoalDialogOpen: (open) => set({ goalDialogOpen: open }),
  setTicketDialogOpen: (open) => set({ ticketDialogOpen: open }),
  setGoalsListOpen: (open) => set({ goalsListOpen: open }),
  setQueueStatusOpen: (open) => set({ queueStatusOpen: open }),
  setDebugPanelOpen: (open) => set({ debugPanelOpen: open }),
  setDashboardOpen: (open) => set({ dashboardOpen: open }),
  setShortcutsHelpOpen: (open) => set({ shortcutsHelpOpen: open }),
  setRepoDiscoveryOpen: (open) => set({ repoDiscoveryOpen: open }),
  setBoardSettingsOpen: (open, tab) =>
    set({ boardSettingsOpen: open, ...(tab ? { boardSettingsTab: tab } : open ? {} : { boardSettingsTab: "execution" }) }),
  toggleDebugPanel: () =>
    set((state) => ({ debugPanelOpen: !state.debugPanelOpen })),
}));
