import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { AppLayout } from "@/layouts/AppLayout";

// Mock react-router hooks
vi.mock("react-router", async () => {
  const actual = await vi.importActual("react-router");
  return {
    ...actual,
    useOutlet: () => <div data-testid="outlet" />,
    Outlet: () => <div data-testid="outlet" />,
    useParams: () => ({}),
    useNavigate: () => vi.fn(),
    useLocation: () => ({ pathname: "/" }),
  };
});

// Mock framer-motion
vi.mock("framer-motion", () => ({
  motion: new Proxy(
    {},
    {
      get: (_: object, tag: string) =>
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ({ children, ...props }: Record<string, any>) => {
          const Tag = tag as keyof JSX.IntrinsicElements;
          return <Tag {...props}>{children}</Tag>;
        },
    },
  ),
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
}));

// Mock BoardContext
vi.mock("@/contexts/BoardContext", () => ({
  useBoard: () => ({
    currentBoard: {
      id: "board-1",
      name: "Test Board",
      repo_root: "/tmp",
      description: null,
      default_branch: "main",
      created_at: "",
      updated_at: "",
    },
    boards: [
      {
        id: "board-1",
        name: "Test Board",
        repo_root: "/tmp",
        description: null,
        default_branch: "main",
        created_at: "",
        updated_at: "",
      },
    ],
    isLoading: false,
    error: null,
    setCurrentBoard: vi.fn(),
    refreshBoards: vi.fn(),
  }),
}));

// Mock config
vi.mock("@/config", () => ({
  config: { appName: "Draft", backendBaseUrl: "http://localhost:8000" },
}));

// Mock all heavy child components
vi.mock("@/components/BoardSelector", () => ({
  BoardSelector: () => <div data-testid="board-selector">BoardSelector</div>,
}));

vi.mock("@/components/RepoDiscoveryDialog", () => ({
  RepoDiscoveryDialog: () => null,
}));

vi.mock("@/components/CreateGoalDialog", () => ({
  CreateGoalDialog: () => null,
}));

vi.mock("@/components/CreateTicketDialog", () => ({
  CreateTicketDialog: () => null,
}));

vi.mock("@/components/GoalsListDialog", () => ({
  GoalsListDialog: () => null,
}));

vi.mock("@/components/QueueStatusDialog", () => ({
  QueueStatusDialog: () => null,
}));

vi.mock("@/components/DebugPanel", () => ({
  DebugPanel: () => null,
}));

vi.mock("@/components/SprintDashboard", () => ({
  SprintDashboard: () => null,
}));

vi.mock("@/components/KeyboardShortcutsHelp", () => ({
  KeyboardShortcutsHelp: () => null,
}));

vi.mock("@/components/WelcomeWalkthrough", () => ({
  WelcomeWalkthrough: () => null,
}));

vi.mock("@/components/NotificationCenter", () => ({
  NotificationCenter: () => (
    <div data-testid="notification-center">Notifications</div>
  ),
}));

vi.mock("@/components/BackendOfflineBanner", () => ({
  BackendOfflineBanner: () => null,
}));

vi.mock("@/hooks/useBackendStatus", () => ({
  useBackendStatus: () => "online",
}));

vi.mock("@/hooks/useNotificationBridge", () => ({
  useNotificationBridge: vi.fn(),
}));

vi.mock("@/components/ui/sonner", () => ({
  Toaster: () => null,
}));

vi.mock("@/services/api", () => ({
  createGoal: vi.fn(),
  createTicket: vi.fn(),
}));

vi.mock("@/hooks/useKeyboardShortcuts", () => ({
  useAppShortcuts: vi.fn(),
}));

vi.mock("@/stores/uiStore", () => ({
  useUIStore: () => ({
    goalDialogOpen: false,
    setGoalDialogOpen: vi.fn(),
    ticketDialogOpen: false,
    setTicketDialogOpen: vi.fn(),
    goalsListOpen: false,
    setGoalsListOpen: vi.fn(),
    queueStatusOpen: false,
    setQueueStatusOpen: vi.fn(),
    repoDiscoveryOpen: false,
    setRepoDiscoveryOpen: vi.fn(),
    debugPanelOpen: false,
    setDebugPanelOpen: vi.fn(),
    toggleDebugPanel: vi.fn(),
    dashboardOpen: false,
    setDashboardOpen: vi.fn(),
    shortcutsHelpOpen: false,
    setShortcutsHelpOpen: vi.fn(),
  }),
}));

describe("AppLayout", () => {
  it("renders without crashing", () => {
    render(<AppLayout />);
    // The layout should render a header and main area
    expect(screen.getByText("Draft")).toBeInTheDocument();
  });

  it("renders the app name in the header", () => {
    render(<AppLayout />);
    expect(screen.getByText("Draft")).toBeInTheDocument();
  });

  it("renders the Goals button", () => {
    render(<AppLayout />);
    expect(screen.getByText("Goals")).toBeInTheDocument();
  });

  it("renders the New Goal button", () => {
    render(<AppLayout />);
    expect(screen.getByText("New Goal")).toBeInTheDocument();
  });

  it("renders the New Ticket button", () => {
    render(<AppLayout />);
    expect(screen.getByText("New Ticket")).toBeInTheDocument();
  });

  it("renders the Debug button", () => {
    render(<AppLayout />);
    expect(screen.getByText("Debug")).toBeInTheDocument();
  });

  it("renders Add Projects button", () => {
    render(<AppLayout />);
    expect(screen.getByText("Add Projects")).toBeInTheDocument();
  });

  it("renders the board selector", () => {
    render(<AppLayout />);
    expect(screen.getByTestId("board-selector")).toBeInTheDocument();
  });
});
