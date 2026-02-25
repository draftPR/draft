import { describe, it, expect, beforeEach } from "vitest";
import { useUIStore } from "../uiStore";

describe("uiStore", () => {
  beforeEach(() => {
    useUIStore.setState({
      goalDialogOpen: false,
      ticketDialogOpen: false,
      goalsListOpen: false,
      queueStatusOpen: false,
      debugPanelOpen: false,
      dashboardOpen: false,
      shortcutsHelpOpen: false,
      repoDiscoveryOpen: false,
    });
  });

  it("all dialogs default to false", () => {
    const state = useUIStore.getState();
    expect(state.goalDialogOpen).toBe(false);
    expect(state.ticketDialogOpen).toBe(false);
    expect(state.goalsListOpen).toBe(false);
    expect(state.queueStatusOpen).toBe(false);
    expect(state.debugPanelOpen).toBe(false);
    expect(state.dashboardOpen).toBe(false);
    expect(state.shortcutsHelpOpen).toBe(false);
    expect(state.repoDiscoveryOpen).toBe(false);
  });

  it.each([
    ["goalDialogOpen", "setGoalDialogOpen"],
    ["ticketDialogOpen", "setTicketDialogOpen"],
    ["goalsListOpen", "setGoalsListOpen"],
    ["queueStatusOpen", "setQueueStatusOpen"],
    ["debugPanelOpen", "setDebugPanelOpen"],
    ["dashboardOpen", "setDashboardOpen"],
    ["shortcutsHelpOpen", "setShortcutsHelpOpen"],
    ["repoDiscoveryOpen", "setRepoDiscoveryOpen"],
  ] as const)("setter %s toggles %s", (key, setter) => {
    const store = useUIStore.getState();
    (store[setter] as (v: boolean) => void)(true);
    expect(useUIStore.getState()[key]).toBe(true);

    (useUIStore.getState()[setter] as (v: boolean) => void)(false);
    expect(useUIStore.getState()[key]).toBe(false);
  });

  it("toggleDebugPanel flips state", () => {
    expect(useUIStore.getState().debugPanelOpen).toBe(false);
    useUIStore.getState().toggleDebugPanel();
    expect(useUIStore.getState().debugPanelOpen).toBe(true);
    useUIStore.getState().toggleDebugPanel();
    expect(useUIStore.getState().debugPanelOpen).toBe(false);
  });
});
