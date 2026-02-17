import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AppNotification {
  id: string;
  type: "info" | "success" | "warning" | "error";
  title: string;
  description?: string;
  timestamp: number;
  read: boolean;
  ticketId?: string;
}

interface NotificationState {
  notifications: AppNotification[];
  addNotification: (n: Omit<AppNotification, "id" | "timestamp" | "read">) => void;
  markRead: (id: string) => void;
  markAllRead: () => void;
  clearAll: () => void;
  unreadCount: () => number;
}

const MAX_NOTIFICATIONS = 50;

export const useNotificationStore = create<NotificationState>()(
  persist(
    (set, get) => ({
      notifications: [],

      addNotification: (n) =>
        set((state) => {
          const notification: AppNotification = {
            ...n,
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            timestamp: Date.now(),
            read: false,
          };
          const updated = [notification, ...state.notifications].slice(0, MAX_NOTIFICATIONS);
          return { notifications: updated };
        }),

      markRead: (id) =>
        set((state) => ({
          notifications: state.notifications.map((n) =>
            n.id === id ? { ...n, read: true } : n,
          ),
        })),

      markAllRead: () =>
        set((state) => ({
          notifications: state.notifications.map((n) => ({ ...n, read: true })),
        })),

      clearAll: () => set({ notifications: [] }),

      unreadCount: () => get().notifications.filter((n) => !n.read).length,
    }),
    {
      name: "alma-notifications",
    },
  ),
);
