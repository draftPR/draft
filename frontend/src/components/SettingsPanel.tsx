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
} from "@/services/api";
import type { PlannerHealthResponse } from "@/types/api";

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

/* ── Main SettingsPanel (kept for backward compat) ── */

export function SettingsPanel() {
  const [editor, setEditor] = useState<EditorType>(getPreferredEditor());
  const [defaultAgent, setDefaultAgent] = useState("claude");
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

  useEffect(() => {
    const stored = localStorage.getItem("smartkanban_default_agent");
    if (stored) setDefaultAgent(stored);
  }, []);

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
      <BudgetSettingsCard budget={budget} onBudgetChange={handleBudgetChange} />
      <KeyboardShortcutsCard />
      <WelcomeTutorialCard />
    </div>
  );
}
