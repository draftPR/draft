/**
 * Application router -- URL-based navigation
 *
 * Routes:
 *   /                              Dashboard / board selection
 *   /boards/:boardId               Kanban board view
 *   /boards/:boardId/tickets/:ticketId  Ticket detail (opens detail panel)
 *   /settings                      Settings page
 */

import { createBrowserRouter, Navigate } from "react-router";
import { AppLayout } from "@/layouts/AppLayout";

// Lazy-load route components for code splitting
import { KanbanBoard } from "@/components/KanbanBoard";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      {
        index: true,
        element: <KanbanBoard />,
      },
      {
        path: "boards/:boardId",
        element: <KanbanBoard />,
      },
      {
        path: "boards/:boardId/tickets/:ticketId",
        element: <KanbanBoard />,
      },
      {
        path: "settings",
        element: <SettingsPage />,
      },
      {
        path: "*",
        element: <Navigate to="/" replace />,
      },
    ],
  },
]);

/**
 * Placeholder settings page -- will be expanded in Phase 6.
 */
function SettingsPage() {
  return (
    <div className="p-8">
      <h2 className="text-2xl font-bold mb-4">Settings</h2>
      <p className="text-muted-foreground">Settings page coming soon.</p>
    </div>
  );
}
