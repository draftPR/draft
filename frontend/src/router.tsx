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

import { BoardLayout } from "@/components/BoardLayout";
import { SettingsPage } from "@/pages/SettingsPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      {
        index: true,
        element: <BoardLayout />,
      },
      {
        path: "boards/:boardId",
        element: <BoardLayout />,
      },
      {
        path: "boards/:boardId/tickets/:ticketId",
        element: <BoardLayout />,
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
