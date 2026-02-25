import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import {
  EditorSettingsCard,
  AgentSettingsCard,
  BudgetSettingsCard,
  KeyboardShortcutsCard,
  WelcomeTutorialCard,
  SettingsPanel,
  loadBudgetSettings,
  saveBudgetSettings,
} from "@/components/SettingsPanel";

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
    config: { verify_config: { commands: ["npm test"] } },
  }),
  updateBoardConfig: vi.fn().mockResolvedValue({}),
  fetchExecutorProfiles: vi.fn().mockResolvedValue([]),
  saveExecutorProfiles: vi.fn().mockResolvedValue([]),
}));

describe("EditorSettingsCard", () => {
  it("renders the editor integration card", () => {
    render(
      <EditorSettingsCard editor="vscode" onEditorChange={vi.fn()} />,
    );
    expect(screen.getByText("Editor Integration")).toBeInTheDocument();
  });

  it("shows helpful description text", () => {
    render(
      <EditorSettingsCard editor="vscode" onEditorChange={vi.fn()} />,
    );
    expect(
      screen.getByText(/Choose how files open/),
    ).toBeInTheDocument();
  });
});

describe("AgentSettingsCard", () => {
  it("renders the AI Agent card", () => {
    render(
      <AgentSettingsCard defaultAgent="claude" onAgentChange={vi.fn()} />,
    );
    expect(screen.getByText("AI Agent")).toBeInTheDocument();
  });
});

describe("BudgetSettingsCard", () => {
  it("renders the Cost Budget card", () => {
    const budget = {
      daily: 10,
      weekly: 50,
      monthly: 150,
      warningThreshold: 80,
      pauseOnExceed: false,
    };
    render(
      <BudgetSettingsCard budget={budget} onBudgetChange={vi.fn()} />,
    );
    expect(screen.getByText("Cost Budget")).toBeInTheDocument();
  });

  it("renders budget input labels", () => {
    const budget = {
      daily: 10,
      weekly: 50,
      monthly: 150,
      warningThreshold: 80,
      pauseOnExceed: false,
    };
    render(
      <BudgetSettingsCard budget={budget} onBudgetChange={vi.fn()} />,
    );
    expect(screen.getByText("Daily Budget")).toBeInTheDocument();
    expect(screen.getByText("Weekly Budget")).toBeInTheDocument();
    expect(screen.getByText("Monthly Budget")).toBeInTheDocument();
  });
});

describe("KeyboardShortcutsCard", () => {
  it("renders the card", () => {
    render(<KeyboardShortcutsCard />);
    expect(screen.getByText("Keyboard Shortcuts")).toBeInTheDocument();
  });
});

describe("WelcomeTutorialCard", () => {
  it("renders the tutorial card", () => {
    render(<WelcomeTutorialCard />);
    expect(screen.getByText("Welcome Tutorial")).toBeInTheDocument();
    expect(screen.getByText("Start Tutorial")).toBeInTheDocument();
    expect(screen.getByText("Reset")).toBeInTheDocument();
  });
});

describe("loadBudgetSettings / saveBudgetSettings", () => {
  it("returns defaults when no stored data", () => {
    localStorage.removeItem("smartkanban_budget");
    const budget = loadBudgetSettings();
    expect(budget.daily).toBe(10);
    expect(budget.weekly).toBe(50);
    expect(budget.monthly).toBe(150);
  });

  it("roundtrips save/load", () => {
    const custom = {
      daily: 20,
      weekly: 100,
      monthly: 300,
      warningThreshold: 90,
      pauseOnExceed: true,
    };
    saveBudgetSettings(custom);
    const loaded = loadBudgetSettings();
    expect(loaded).toEqual(custom);
  });
});

describe("SettingsPanel", () => {
  it("renders the main settings heading", () => {
    render(<SettingsPanel />);
    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(
      screen.getByText(/Configure Alma Kanban/),
    ).toBeInTheDocument();
  });
});
