import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotificationCenter } from "../NotificationCenter";
import { useNotificationStore } from "@/stores/notificationStore";

describe("NotificationCenter", () => {
  beforeEach(() => {
    // Reset the zustand store between tests
    useNotificationStore.setState({ notifications: [] });
  });

  it("renders the bell button", () => {
    render(<NotificationCenter />);

    expect(screen.getByTitle("Notifications")).toBeInTheDocument();
  });

  it("does not show unread badge when there are no notifications", () => {
    render(<NotificationCenter />);

    // No badge should be visible (the badge shows unreadCount > 0)
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("shows unread badge when there are unread notifications", () => {
    useNotificationStore.getState().addNotification({
      type: "info",
      title: "Test notification",
    });

    render(<NotificationCenter />);

    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("shows 9+ for more than 9 unread notifications", () => {
    const store = useNotificationStore.getState();
    for (let i = 0; i < 10; i++) {
      store.addNotification({
        type: "info",
        title: `Notification ${i}`,
      });
    }

    render(<NotificationCenter />);

    expect(screen.getByText("9+")).toBeInTheDocument();
  });

  it("shows 'No notifications yet' in popover when empty", async () => {
    const user = userEvent.setup();
    render(<NotificationCenter />);

    await user.click(screen.getByTitle("Notifications"));

    expect(screen.getByText("No notifications yet")).toBeInTheDocument();
  });

  it("shows notifications in popover", async () => {
    const user = userEvent.setup();

    useNotificationStore.getState().addNotification({
      type: "success",
      title: "Build passed",
      description: "All tests green",
    });

    render(<NotificationCenter />);

    await user.click(screen.getByTitle("Notifications"));

    expect(screen.getByText("Build passed")).toBeInTheDocument();
    expect(screen.getByText("All tests green")).toBeInTheDocument();
  });

  it("shows 'Mark all read' button when there are unread notifications", async () => {
    const user = userEvent.setup();

    useNotificationStore.getState().addNotification({
      type: "error",
      title: "Deploy failed",
    });

    render(<NotificationCenter />);

    await user.click(screen.getByTitle("Notifications"));

    expect(screen.getByText("Mark all read")).toBeInTheDocument();
  });

  it("shows 'Clear' button when there are notifications", async () => {
    const user = userEvent.setup();

    useNotificationStore.getState().addNotification({
      type: "warning",
      title: "Slow query detected",
    });

    render(<NotificationCenter />);

    await user.click(screen.getByTitle("Notifications"));

    expect(screen.getByText("Clear")).toBeInTheDocument();
  });

  it("marks notification as read on click", async () => {
    const user = userEvent.setup();

    useNotificationStore.getState().addNotification({
      type: "info",
      title: "New ticket created",
    });

    render(<NotificationCenter />);

    // Open popover
    await user.click(screen.getByTitle("Notifications"));

    // Click the notification
    await user.click(screen.getByText("New ticket created"));

    // Verify the notification is now read in the store
    const notifications = useNotificationStore.getState().notifications;
    expect(notifications[0].read).toBe(true);
  });
});
