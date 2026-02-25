import { describe, it, expect, beforeEach } from "vitest";
import { useTicketSelectionStore } from "../ticketStore";

describe("ticketStore", () => {
  beforeEach(() => {
    useTicketSelectionStore.setState({
      selectedTicketId: null,
      detailDrawerOpen: false,
    });
  });

  it("initializes with null selection and closed drawer", () => {
    const state = useTicketSelectionStore.getState();
    expect(state.selectedTicketId).toBeNull();
    expect(state.detailDrawerOpen).toBe(false);
  });

  it("selectTicket sets id and opens drawer", () => {
    useTicketSelectionStore.getState().selectTicket("ticket-1");
    const state = useTicketSelectionStore.getState();
    expect(state.selectedTicketId).toBe("ticket-1");
    expect(state.detailDrawerOpen).toBe(true);
  });

  it("clearSelection resets id and closes drawer", () => {
    useTicketSelectionStore.getState().selectTicket("ticket-1");
    useTicketSelectionStore.getState().clearSelection();
    const state = useTicketSelectionStore.getState();
    expect(state.selectedTicketId).toBeNull();
    expect(state.detailDrawerOpen).toBe(false);
  });

  it("setDetailDrawerOpen(false) clears selectedTicketId", () => {
    useTicketSelectionStore.getState().selectTicket("ticket-1");
    useTicketSelectionStore.getState().setDetailDrawerOpen(false);
    const state = useTicketSelectionStore.getState();
    expect(state.detailDrawerOpen).toBe(false);
    expect(state.selectedTicketId).toBeNull();
  });

  it("setDetailDrawerOpen(true) preserves existing selectedTicketId", () => {
    useTicketSelectionStore.getState().selectTicket("ticket-1");
    useTicketSelectionStore.getState().setDetailDrawerOpen(true);
    const state = useTicketSelectionStore.getState();
    expect(state.detailDrawerOpen).toBe(true);
    expect(state.selectedTicketId).toBe("ticket-1");
  });
});
