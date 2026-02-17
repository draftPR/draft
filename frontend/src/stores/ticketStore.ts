/**
 * Ticket selection store -- manages selected ticket and detail drawer state.
 */

import { create } from "zustand";

interface TicketSelectionState {
  selectedTicketId: string | null;
  detailDrawerOpen: boolean;

  selectTicket: (ticketId: string) => void;
  clearSelection: () => void;
  setDetailDrawerOpen: (open: boolean) => void;
}

export const useTicketSelectionStore = create<TicketSelectionState>((set) => ({
  selectedTicketId: null,
  detailDrawerOpen: false,

  selectTicket: (ticketId: string) =>
    set({ selectedTicketId: ticketId, detailDrawerOpen: true }),

  clearSelection: () =>
    set({ selectedTicketId: null, detailDrawerOpen: false }),

  setDetailDrawerOpen: (open: boolean) =>
    set((state) => ({
      detailDrawerOpen: open,
      selectedTicketId: open ? state.selectedTicketId : null,
    })),
}));
