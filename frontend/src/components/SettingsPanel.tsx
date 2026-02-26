import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Settings,
  Code,
  DollarSign,
  Bot,
  Keyboard,
  Save,
  Rocket,
  Cpu,
  CheckCircle2,
  XCircle,
  Loader2,
  Info,
  Terminal,
  Plus,
  Trash2,
  GripVertical,
} from "lucide-react";
import {
  getPreferredEditor,
  setPreferredEditor,
  getAvailableEditors,
  type EditorType,
} from "@/services/editorIntegration";
import { AgentSelector } from "./AgentSelector";
import { useWalkthrough } from "@/hooks/useWalkthrough";
import { playSound } from "@/services/soundNotifications";
import {
  fetchPlannerConfig,
  updatePlannerConfig,
  checkPlannerHealth,
  getBoardConfig,
  updateBoardConfig,
  fetchExecutorProfiles,
  saveExecutorProfiles,
} from "@/services/api";
import type { PlannerHealthResponse } from "@/types/api";
import { useBoard } from "@/contexts/BoardContext";

export interface BudgetSettings {
  daily: number;
  weekly: number;
  monthly: number;
  warningThreshold: number;
  pauseOnExceed: boolean;
}

const DEFAULT_BUDGET: BudgetSettings = {
  daily: 10,
  weekly: 50,
  monthly: 150,
  warningThreshold: 80,
  pauseOnExceed: false,
};

export function loadBudgetSettings(): BudgetSettings {
  if (typeof window === "undefined") return DEFAULT_BUDGET;
  const stored = localStorage.getItem("smartkanban_budget");
  if (stored) {
    try {
      return JSON.parse(stored);
    } catch {
      return DEFAULT_BUDGET;
    }
  }
  return DEFAULT_BUDGET;
}

export function saveBudgetSettings(settings: BudgetSettings): void {
  if (typeof window !== "undefined") {
    localStorage.setItem("smartkanban_budget", JSON.stringify(settings));
  }
}

/* ── Exportable sub-components ── */

export function EditorSettingsCard({
  editor,
  onEditorChange,
}: {
  editor: EditorType;
  onEditorChange: (value: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="section-header flex items-center gap-2">
          <Code className="h-5 w-5" />
          Editor Integration
        </CardTitle>
        <CardDescription>
          Choose how files open when clicking on diffs or file paths
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label>Preferred Editor</Label>
          <Select value={editor} onValueChange={onEditorChange}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {getAvailableEditors().map(e => (
                <SelectItem key={e.type} value={e.type}>
                  {e.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Files will open in {editor === "vscode" ? "VS Code" : editor === "cursor" ? "Cursor" : "your system default"}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

export function AgentSettingsCard({
  defaultAgent,
  onAgentChange,
}: {
  defaultAgent: string;
  onAgentChange: (value: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="section-header flex items-center gap-2">
          <Bot className="h-5 w-5" />
          AI Agent
        </CardTitle>
        <CardDescription>
          Configure your default AI coding agent
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label>Default Agent</Label>
          <AgentSelector
            value={defaultAgent}
            onChange={onAgentChange}
            showDetails
          />
        </div>
      </CardContent>
    </Card>
  );
}

export function ExecutorProfilesCard() {
  const [profiles, setProfiles] = useState<
    { name: string; executor_type: string; timeout: number; extra_flags: string[]; model: string | null; env: Record<string, string> }[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    fetchExecutorProfiles()
      .then((p) => setProfiles(p))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const addProfile = () => {
    setProfiles((prev) => [
      ...prev,
      { name: "", executor_type: "claude", timeout: 600, extra_flags: [], model: null, env: {} },
    ]);
    setDirty(true);
  };

  const removeProfile = (idx: number) => {
    setProfiles((prev) => prev.filter((_, i) => i !== idx));
    setDirty(true);
  };

  const updateProfile = (idx: number, field: string, value: string | number | string[]) => {
    setProfiles((prev) =>
      prev.map((p, i) => (i === idx ? { ...p, [field]: value } : p)),
    );
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const saved = await saveExecutorProfiles(
        profiles.filter((p) => p.name.trim()),
      );
      setProfiles(saved);
      setDirty(false);
      playSound("success");
    } catch {
      // Error handled silently
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="section-header flex items-center gap-2">
              <Cpu className="h-5 w-5" />
              Executor Profiles
            </CardTitle>
            <CardDescription>
              Named execution strategies (e.g. fast, thorough) with per-profile settings
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            {dirty && (
              <Button size="sm" onClick={handleSave} disabled={saving}>
                {saving ? (
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                ) : (
                  <Save className="h-3 w-3 mr-1" />
                )}
                Save
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={addProfile}>
              <Plus className="h-3 w-3 mr-1" />
              Add Profile
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading profiles...
          </div>
        ) : profiles.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No profiles configured. Add a profile to create execution strategies
            like &quot;fast&quot; (Haiku, 5min timeout) or &quot;thorough&quot; (Opus, 20min timeout).
          </p>
        ) : (
          profiles.map((profile, idx) => (
            <div
              key={idx}
              className="border rounded-lg p-3 space-y-3"
            >
              <div className="flex items-center gap-2">
                <GripVertical className="h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Profile name (e.g. fast)"
                  value={profile.name}
                  onChange={(e) => updateProfile(idx, "name", e.target.value)}
                  className="flex-1 h-8 text-sm"
                />
                <Select
                  value={profile.executor_type}
                  onValueChange={(v) => updateProfile(idx, "executor_type", v)}
                >
                  <SelectTrigger className="w-[130px] h-8 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="claude">Claude</SelectItem>
                    <SelectItem value="codex">Codex</SelectItem>
                    <SelectItem value="gemini">Gemini</SelectItem>
                    <SelectItem value="cursor">Cursor</SelectItem>
                    <SelectItem value="cursor-agent">Cursor Agent</SelectItem>
                    <SelectItem value="amp">Amp</SelectItem>
                    <SelectItem value="droid">Droid</SelectItem>
                    <SelectItem value="opencode">OpenCode</SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                  onClick={() => removeProfile(idx)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">Timeout (seconds)</Label>
                  <Input
                    type="number"
                    value={profile.timeout}
                    onChange={(e) =>
                      updateProfile(idx, "timeout", parseInt(e.target.value) || 600)
                    }
                    className="h-8 text-sm"
                    min={60}
                    step={60}
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Model override</Label>
                  <Input
                    placeholder="e.g. claude-haiku-4-5-20251001"
                    value={profile.model || ""}
                    onChange={(e) =>
                      updateProfile(idx, "model", e.target.value || "")
                    }
                    className="h-8 text-sm"
                  />
                </div>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Extra CLI flags (comma-separated)</Label>
                <Input
                  placeholder='e.g. --model, claude-haiku-4-5-20251001'
                  value={(profile.extra_flags || []).join(", ")}
                  onChange={(e) =>
                    updateProfile(
                      idx,
                      "extra_flags",
                      e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    )
                  }
                  className="h-8 text-sm font-mono"
                />
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

export function BudgetSettingsCard({
  budget,
  onBudgetChange,
}: {
  budget: BudgetSettings;
  onBudgetChange: (key: keyof BudgetSettings, value: number | boolean) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="section-header flex items-center gap-2">
          <DollarSign className="h-5 w-5" />
          Cost Budget
        </CardTitle>
        <CardDescription>
          Set spending limits for AI agent usage
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-4">
          <div className="space-y-2">
            <Label>Daily Budget</Label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
              <Input
                type="number"
                value={budget.daily}
                onChange={e => onBudgetChange("daily", parseFloat(e.target.value) || 0)}
                className="pl-7"
                min={0}
                step={1}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label>Weekly Budget</Label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
              <Input
                type="number"
                value={budget.weekly}
                onChange={e => onBudgetChange("weekly", parseFloat(e.target.value) || 0)}
                className="pl-7"
                min={0}
                step={5}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label>Monthly Budget</Label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
              <Input
                type="number"
                value={budget.monthly}
                onChange={e => onBudgetChange("monthly", parseFloat(e.target.value) || 0)}
                className="pl-7"
                min={0}
                step={10}
              />
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <Label>Warning Threshold</Label>
          <div className="flex items-center gap-4">
            <Slider
              value={[budget.warningThreshold]}
              onValueChange={(v) => onBudgetChange("warningThreshold", v[0])}
              max={100}
              step={5}
              className="flex-1"
            />
            <span className="text-sm text-muted-foreground w-12">
              {budget.warningThreshold}%
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Show warning when spending reaches this % of budget
          </p>
        </div>

        <div className="flex items-center justify-between">
          <div>
            <Label htmlFor="pause-toggle">Pause on Budget Exceed</Label>
            <p className="text-xs text-muted-foreground">
              Stop automated execution when budget is exceeded
            </p>
          </div>
          <Switch
            id="pause-toggle"
            checked={budget.pauseOnExceed}
            onCheckedChange={(v) => onBudgetChange("pauseOnExceed", v)}
          />
        </div>
      </CardContent>
    </Card>
  );
}

export function KeyboardShortcutsCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="section-header flex items-center gap-2">
          <Keyboard className="h-5 w-5" />
          Keyboard Shortcuts
        </CardTitle>
        <CardDescription>
          Navigate and interact faster with keyboard shortcuts
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Press <Badge variant="outline" className="font-mono mx-1">?</Badge>
          anywhere in the app to view all keyboard shortcuts.
        </p>
      </CardContent>
    </Card>
  );
}

export function WelcomeTutorialCard() {
  const { openWalkthrough, resetWalkthrough } = useWalkthrough();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="section-header flex items-center gap-2">
          <Rocket className="h-5 w-5" />
          Welcome Tutorial
        </CardTitle>
        <CardDescription>
          Replay the welcome walkthrough or reset your tutorial progress
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Replay Walkthrough</p>
            <p className="text-xs text-muted-foreground">
              View the step-by-step guide again
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={openWalkthrough}>
            <Rocket className="h-4 w-4 mr-2" />
            Start Tutorial
          </Button>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Reset Progress</p>
            <p className="text-xs text-muted-foreground">
              Mark walkthrough as not completed (will auto-open on next load)
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              resetWalkthrough();
              playSound("success");
            }}
          >
            Reset
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/* ── Planner / LLM Configuration Card ── */

const API_MODEL_PRESETS = [
  {
    label: "Anthropic Claude Sonnet 4.5",
    value: "anthropic/claude-sonnet-4-5-20250929",
    provider: "anthropic",
    description: "Claude Sonnet 4.5 via direct Anthropic API",
  },
  {
    label: "Anthropic Claude Haiku 4.5",
    value: "anthropic/claude-haiku-4-5-20251001",
    provider: "anthropic",
    description: "Fast and cost-effective via direct Anthropic API",
  },
  {
    label: "AWS Bedrock — Claude Sonnet 4.5",
    value: "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
    provider: "bedrock",
    description: "Claude Sonnet 4.5 via AWS Bedrock",
  },
  {
    label: "AWS Bedrock — Claude Haiku 4.5",
    value: "bedrock/anthropic.claude-haiku-4-5-20251001-v1:0",
    provider: "bedrock",
    description: "Claude Haiku 4.5 via AWS Bedrock",
  },
  {
    label: "OpenAI GPT-4o",
    value: "gpt-4o",
    provider: "openai",
    description: "OpenAI's flagship model",
  },
  {
    label: "OpenAI GPT-4o Mini",
    value: "gpt-4o-mini",
    provider: "openai",
    description: "Fast and affordable",
  },
];

function getProviderFromModel(model: string): string {
  if (model === "cli/claude" || model.startsWith("cli/")) return "cli";
  if (model.startsWith("anthropic/")) return "anthropic";
  if (model.startsWith("bedrock/")) return "bedrock";
  if (model.startsWith("gpt")) return "openai";
  return "custom";
}

function getSetupInstructions(provider: string): string {
  switch (provider) {
    case "anthropic":
      return "Set ANTHROPIC_API_KEY in backend/.env";
    case "openai":
      return "Set OPENAI_API_KEY in backend/.env";
    case "bedrock":
      return "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in backend/.env";
    default:
      return "Set the appropriate API key for your model provider in backend/.env";
  }
}

export function PlannerSettingsCard({
  onDirty,
}: {
  onDirty?: () => void;
}) {
  const [model, setModel] = useState("");
  const [agentPath, setAgentPath] = useState("");
  const [health, setHealth] = useState<PlannerHealthResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const isSameAsExecutor = model.startsWith("cli/");

  // Load planner config on mount
  useEffect(() => {
    fetchPlannerConfig()
      .then((cfg) => {
        setModel(cfg.model);
        setAgentPath(cfg.agent_path);
        setLoaded(true);
      })
      .catch((err) => {
        console.error("Failed to load planner config:", err);
        setLoaded(true);
      });
  }, []);

  // Auto-check health on load
  useEffect(() => {
    if (loaded && model) {
      checkPlannerHealth()
        .then(setHealth)
        .catch(() => setHealth({ status: "offline", model, error: "Failed to connect" }));
    }
  }, [loaded]);

  const runHealthCheck = useCallback(async () => {
    setChecking(true);
    setHealth(null);
    try {
      const result = await checkPlannerHealth();
      setHealth(result);
    } catch (err) {
      setHealth({ status: "offline", model, error: String(err) });
    } finally {
      setChecking(false);
    }
  }, [model]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const updated = await updatePlannerConfig({ model, agent_path: agentPath });
      setModel(updated.model);
      setAgentPath(updated.agent_path);
      playSound("success");
      // Re-check health after saving
      runHealthCheck();
    } catch (err) {
      console.error("Failed to save planner config:", err);
    } finally {
      setSaving(false);
    }
  }, [model, agentPath, runHealthCheck]);

  const handleToggle = useCallback((useSameAsExecutor: boolean) => {
    if (useSameAsExecutor) {
      setModel("cli/claude");
    } else {
      // Default to first API preset
      setModel(API_MODEL_PRESETS[0].value);
    }
    setHealth(null);
    onDirty?.();
  }, [onDirty]);

  const provider = getProviderFromModel(model);
  const selectedPreset = API_MODEL_PRESETS.find((p) => p.value === model);
  const isPreset = !!selectedPreset;

  if (!loaded) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="section-header flex items-center gap-2">
          <Cpu className="h-5 w-5" />
          Planner LLM
        </CardTitle>
        <CardDescription>
          Configure the LLM used for ticket generation, follow-ups, and reflections
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Same as executor toggle */}
        <div className="flex items-center justify-between">
          <div>
            <Label htmlFor="same-as-executor">Same as executor</Label>
            <p className="text-xs text-muted-foreground">
              Use the same Claude Code CLI as your execution agent
            </p>
          </div>
          <Switch
            id="same-as-executor"
            checked={isSameAsExecutor}
            onCheckedChange={handleToggle}
          />
        </div>

        {/* Details panel — matches AgentDetails style */}
        {isSameAsExecutor ? (
          /* Same-as-executor: simple status panel */
          <div className="p-3 bg-muted/50 rounded-lg space-y-2">
            <div className="flex items-center gap-2 text-sm">
              {checking ? (
                <Badge variant="outline">
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  Checking...
                </Badge>
              ) : health?.status === "online" ? (
                <Badge variant="default">
                  <CheckCircle2 className="h-3 w-3 mr-1" />
                  Available
                </Badge>
              ) : health?.status === "offline" ? (
                <Badge variant="destructive">
                  <XCircle className="h-3 w-3 mr-1" />
                  Not Installed
                </Badge>
              ) : (
                <Badge variant="outline">
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  Checking...
                </Badge>
              )}
              <span className="text-muted-foreground">
                Uses the same Claude Code CLI as ticket execution — no extra API key needed
              </span>
            </div>

            {health?.status === "offline" && (
              <div className="mt-1 p-2 bg-background rounded border text-sm space-y-1">
                <p className="font-medium flex items-center gap-1 text-xs">
                  <Info className="h-3.5 w-3.5" />
                  Setup required
                </p>
                <p className="text-xs text-muted-foreground">
                  Install Claude Code CLI or turn off this toggle to use an API model instead.
                </p>
              </div>
            )}
          </div>
        ) : (
          /* Custom model: model picker + status */
          <>
            <div className="space-y-2">
              <Label>LLM Model</Label>
              <Select
                value={isPreset ? model : "__custom__"}
                onValueChange={(v) => {
                  if (v !== "__custom__") {
                    setModel(v);
                    onDirty?.();
                  }
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a model">
                    {selectedPreset && (
                      <div className="flex items-center gap-2">
                        <Cpu className="h-4 w-4" />
                        <span>{selectedPreset.label}</span>
                      </div>
                    )}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {API_MODEL_PRESETS.map((preset) => (
                    <SelectItem key={preset.value} value={preset.value}>
                      <div className="flex items-center gap-2">
                        <Cpu className="h-4 w-4" />
                        <span>{preset.label}</span>
                      </div>
                    </SelectItem>
                  ))}
                  <SelectItem value="__custom__">
                    <div className="flex items-center gap-2">
                      <Settings className="h-4 w-4" />
                      <span>Custom model...</span>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>

              {!isPreset && (
                <Input
                  placeholder="e.g., bedrock/arn:aws:bedrock:us-east-2:..."
                  value={model}
                  onChange={(e) => {
                    setModel(e.target.value);
                    onDirty?.();
                  }}
                />
              )}
            </div>

            <div className="p-3 bg-muted/50 rounded-lg space-y-2">
              <div className="flex items-center gap-2 text-sm">
                {checking ? (
                  <Badge variant="outline">
                    <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                    Checking...
                  </Badge>
                ) : health?.status === "online" ? (
                  <Badge variant="default">
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                    Available
                  </Badge>
                ) : health?.status === "offline" ? (
                  <Badge variant="destructive">
                    <XCircle className="h-3 w-3 mr-1" />
                    Not Connected
                  </Badge>
                ) : (
                  <Badge variant="outline">
                    <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                    Checking...
                  </Badge>
                )}
                <span className="text-muted-foreground">
                  {selectedPreset?.description ?? `Custom model via ${provider}`}
                </span>
              </div>

              {health?.status === "offline" && (
                <div className="mt-1 p-2 bg-background rounded border text-sm space-y-1">
                  <p className="font-medium flex items-center gap-1 text-xs">
                    <Info className="h-3.5 w-3.5" />
                    Setup required
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {getSetupInstructions(provider)}. Then restart the backend.
                  </p>
                  {health.error && (
                    <p className="text-xs text-muted-foreground font-mono break-all">
                      {health.error.slice(0, 150)}
                    </p>
                  )}
                </div>
              )}
            </div>
          </>
        )}

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={runHealthCheck}
            disabled={checking}
          >
            {checking ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <CheckCircle2 className="h-4 w-4 mr-2" />}
            Test Connection
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
            Save
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/* ── Verification Commands Card ── */

export function VerificationCommandsCard() {
  const { currentBoard } = useBoard();
  const [commands, setCommands] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newCmd, setNewCmd] = useState("");

  useEffect(() => {
    if (!currentBoard?.id) return;
    getBoardConfig(currentBoard.id)
      .then((cfg) => {
        const cmds = cfg.config?.verify_config?.commands || [];
        setCommands(cmds);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [currentBoard?.id]);

  const handleSave = useCallback(async () => {
    if (!currentBoard?.id) return;
    setSaving(true);
    try {
      await updateBoardConfig(currentBoard.id, {
        config: { verify_config: { commands } },
      });
      playSound("success");
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  }, [currentBoard?.id, commands]);

  const addCommand = () => {
    if (!newCmd.trim()) return;
    setCommands((prev) => [...prev, newCmd.trim()]);
    setNewCmd("");
  };

  const removeCommand = (index: number) => {
    setCommands((prev) => prev.filter((_, i) => i !== index));
  };

  const moveCommand = (from: number, to: number) => {
    setCommands((prev) => {
      const next = [...prev];
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      return next;
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="section-header flex items-center gap-2">
          <Terminal className="h-5 w-5" />
          Verification Commands
        </CardTitle>
        <CardDescription>
          Commands run after each agent execution to verify the changes. They run sequentially in the ticket's worktree.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            {commands.length === 0 ? (
              <p className="text-sm text-muted-foreground italic">
                No verification commands configured. Add commands to automatically verify agent changes.
              </p>
            ) : (
              <div className="space-y-2">
                {commands.map((cmd, i) => (
                  <div key={i} className="flex items-center gap-2 group">
                    <div className="flex flex-col gap-0.5">
                      <button
                        onClick={() => i > 0 && moveCommand(i, i - 1)}
                        disabled={i === 0}
                        className="text-muted-foreground/50 hover:text-muted-foreground disabled:opacity-30 transition-colors"
                      >
                        <GripVertical className="h-3 w-3" />
                      </button>
                    </div>
                    <code className="flex-1 text-sm font-mono bg-muted/50 rounded px-3 py-2 text-foreground">
                      {cmd}
                    </code>
                    <button
                      onClick={() => removeCommand(i)}
                      className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-all"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Add new command */}
            <div className="flex gap-2">
              <Input
                value={newCmd}
                onChange={(e) => setNewCmd(e.target.value)}
                placeholder="e.g., npm test, pytest -q, make lint"
                className="font-mono text-sm"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && newCmd.trim()) {
                    e.preventDefault();
                    addCommand();
                  }
                }}
              />
              <Button size="sm" variant="outline" onClick={addCommand} disabled={!newCmd.trim()}>
                <Plus className="h-4 w-4" />
              </Button>
            </div>

            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
              Save Commands
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/* ── Main SettingsPanel (kept for backward compat) ── */

export function SettingsPanel() {
  const [editor, setEditor] = useState<EditorType>(getPreferredEditor());
  const [defaultAgent, setDefaultAgent] = useState(
    () => (typeof window !== "undefined" ? localStorage.getItem("smartkanban_default_agent") : null) || "claude"
  );
  const [budget, setBudget] = useState<BudgetSettings>(loadBudgetSettings);
  const [hasChanges, setHasChanges] = useState(false);

  const handleEditorChange = (value: string) => {
    setEditor(value as EditorType);
    setPreferredEditor(value as EditorType);
    setHasChanges(true);
  };

  const handleBudgetChange = (key: keyof BudgetSettings, value: number | boolean) => {
    setBudget(prev => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleSave = () => {
    saveBudgetSettings(budget);
    if (typeof window !== "undefined") {
      localStorage.setItem("smartkanban_default_agent", defaultAgent);
    }
    setHasChanges(false);
    playSound("success");
  };

  return (
    <div className="space-y-6 p-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Settings
          </h1>
          <p className="text-muted-foreground">
            Configure Alma Kanban to match your workflow
          </p>
        </div>
        {hasChanges && (
          <Button onClick={handleSave}>
            <Save className="h-4 w-4 mr-2" />
            Save Changes
          </Button>
        )}
      </div>

      <EditorSettingsCard editor={editor} onEditorChange={handleEditorChange} />
      <AgentSettingsCard
        defaultAgent={defaultAgent}
        onAgentChange={(v) => { setDefaultAgent(v); setHasChanges(true); }}
      />
      <ExecutorProfilesCard />
      <PlannerSettingsCard onDirty={() => setHasChanges(true)} />
      <VerificationCommandsCard />
      <BudgetSettingsCard budget={budget} onBudgetChange={handleBudgetChange} />
      <KeyboardShortcutsCard />
      <WelcomeTutorialCard />
    </div>
  );
}
