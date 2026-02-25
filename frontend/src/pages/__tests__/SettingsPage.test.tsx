import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { SettingsPage } from "@/pages/SettingsPage";

vi.mock("@/contexts/BoardContext", () => ({
  useBoard: () => ({
    currentBoard: {
      id: "board-1",
      name: "Test",
      repo_root: "/tmp",
      description: null,
      default_branch: "main",
      created_at: "",
      updated_at: "",
    },
    boards: [],
    isLoading: false,
    error: null,
    setCurrentBoard: vi.fn(),
    refreshBoards: vi.fn(),
  }),
}));

vi.mock("@/services/editorIntegration", () => ({
  getPreferredEditor: () => "vscode",
  setPreferredEditor: vi.fn(),
  getAvailableEditors: () => [
    { type: "vscode", name: "VS Code" },
    { type: "cursor", name: "Cursor" },
    { type: "system", name: "System Default" },
  ],
}));

vi.mock("@/components/AgentSelector", () => ({
  AgentSelector: ({ value }: { value: string }) => (
    <div data-testid="agent-selector">Agent: {value}</div>
  ),
}));

vi.mock("@/hooks/useWalkthrough", () => ({
  useWalkthrough: () => ({
    openWalkthrough: vi.fn(),
    resetWalkthrough: vi.fn(),
  }),
}));

vi.mock("@/services/soundNotifications", () => ({
  playSound: vi.fn(),
}));

vi.mock("@/services/api", () => ({
  fetchPlannerConfig: vi.fn().mockResolvedValue({
    model: "cli/claude",
    agent_path: "",
  }),
  updatePlannerConfig: vi.fn().mockResolvedValue({
    model: "cli/claude",
    agent_path: "",
  }),
  checkPlannerHealth: vi.fn().mockResolvedValue({
    status: "online",
    model: "cli/claude",
  }),
  getBoardConfig: vi.fn().mockResolvedValue({
    config: { verify_config: { commands: [] } },
  }),
  updateBoardConfig: vi.fn().mockResolvedValue({}),
  fetchExecutorProfiles: vi.fn().mockResolvedValue([]),
  saveExecutorProfiles: vi.fn().mockResolvedValue([]),
}));

describe("SettingsPage", () => {
  it("renders the Settings heading", () => {
    render(<SettingsPage />);
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("renders the description text", () => {
    render(<SettingsPage />);
    expect(
      screen.getByText("Configure Alma Kanban to match your workflow"),
    ).toBeInTheDocument();
  });

  it("renders tab triggers", () => {
    render(<SettingsPage />);
    expect(screen.getByText("General")).toBeInTheDocument();
    expect(screen.getByText("Executors")).toBeInTheDocument();
    expect(screen.getByText("Budget")).toBeInTheDocument();
  });

  it("renders editor settings card in general tab (default)", () => {
    render(<SettingsPage />);
    expect(screen.getByText("Editor Integration")).toBeInTheDocument();
  });

  it("renders keyboard shortcuts card in general tab", () => {
    render(<SettingsPage />);
    expect(
      screen.getByText("Keyboard Shortcuts"),
    ).toBeInTheDocument();
  });

  it("renders welcome tutorial card in general tab", () => {
    render(<SettingsPage />);
    expect(screen.getByText("Welcome Tutorial")).toBeInTheDocument();
  });
});
