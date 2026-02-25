import { describe, it, expect, beforeEach } from "vitest";
import { useNotificationStore } from "../notificationStore";

describe("notificationStore", () => {
  beforeEach(() => {
    useNotificationStore.setState({ notifications: [] });
  });

  it("starts with empty notifications", () => {
    expect(useNotificationStore.getState().notifications).toHaveLength(0);
  });

  it("addNotification creates notification with id, timestamp, read=false", () => {
    useNotificationStore
      .getState()
      .addNotification({ type: "info", title: "Hello" });
    const notifs = useNotificationStore.getState().notifications;
    expect(notifs).toHaveLength(1);
    expect(notifs[0].title).toBe("Hello");
    expect(notifs[0].type).toBe("info");
    expect(notifs[0].read).toBe(false);
    expect(notifs[0].id).toBeTruthy();
    expect(notifs[0].timestamp).toBeGreaterThan(0);
  });

  it("new notifications are prepended (newest first)", () => {
    const store = useNotificationStore.getState();
    store.addNotification({ type: "info", title: "First" });
    useNotificationStore
      .getState()
      .addNotification({ type: "info", title: "Second" });
    const notifs = useNotificationStore.getState().notifications;
    expect(notifs[0].title).toBe("Second");
    expect(notifs[1].title).toBe("First");
  });

  it("caps at 50 notifications", () => {
    for (let i = 0; i < 55; i++) {
      useNotificationStore
        .getState()
        .addNotification({ type: "info", title: `N${i}` });
    }
    expect(useNotificationStore.getState().notifications).toHaveLength(50);
  });

  it("markRead marks a single notification as read", () => {
    useNotificationStore
      .getState()
      .addNotification({ type: "info", title: "Test" });
    const id = useNotificationStore.getState().notifications[0].id;
    useNotificationStore.getState().markRead(id);
    expect(useNotificationStore.getState().notifications[0].read).toBe(true);
  });

  it("markAllRead marks all notifications as read", () => {
    const store = useNotificationStore.getState();
    store.addNotification({ type: "info", title: "A" });
    useNotificationStore
      .getState()
      .addNotification({ type: "info", title: "B" });
    useNotificationStore.getState().markAllRead();
    const allRead = useNotificationStore
      .getState()
      .notifications.every((n) => n.read);
    expect(allRead).toBe(true);
  });

  it("clearAll empties the list", () => {
    useNotificationStore
      .getState()
      .addNotification({ type: "info", title: "X" });
    useNotificationStore.getState().clearAll();
    expect(useNotificationStore.getState().notifications).toHaveLength(0);
  });

  it("unreadCount returns count of unread notifications", () => {
    const store = useNotificationStore.getState();
    store.addNotification({ type: "info", title: "A" });
    useNotificationStore
      .getState()
      .addNotification({ type: "info", title: "B" });
    expect(useNotificationStore.getState().unreadCount()).toBe(2);

    const id = useNotificationStore.getState().notifications[0].id;
    useNotificationStore.getState().markRead(id);
    expect(useNotificationStore.getState().unreadCount()).toBe(1);
  });
});
