import { useState, useEffect } from "react";
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
  Volume2,
  VolumeX,
  Code,
  DollarSign,
  Bot,
  Keyboard,
  Save,
} from "lucide-react";
import {
  isSoundEnabled,
  setSoundEnabled,
  getVolume,
  setVolume,
  playSound,
} from "@/services/soundNotifications";
import {
  getPreferredEditor,
  setPreferredEditor,
  getAvailableEditors,
  type EditorType,
} from "@/services/editorIntegration";
import { AgentSelector } from "./AgentSelector";

interface BudgetSettings {
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

function loadBudgetSettings(): BudgetSettings {
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

function saveBudgetSettings(settings: BudgetSettings): void {
  if (typeof window !== "undefined") {
    localStorage.setItem("smartkanban_budget", JSON.stringify(settings));
  }
}

export function SettingsPanel() {
  // Sound settings
  const [soundOn, setSoundOn] = useState(isSoundEnabled);
  const [volumeLevel, setVolumeLevel] = useState(getVolume() * 100);
  
  // Editor settings
  const [editor, setEditor] = useState<EditorType>(getPreferredEditor());
  
  // Agent settings
  const [defaultAgent, setDefaultAgent] = useState("claude");
  
  // Budget settings
  const [budget, setBudget] = useState<BudgetSettings>(loadBudgetSettings);
  
  // Unsaved changes tracking
  const [hasChanges, setHasChanges] = useState(false);
  
  const handleSoundToggle = (enabled: boolean) => {
    setSoundOn(enabled);
    setSoundEnabled(enabled);
    if (enabled) {
      playSound("notification");
    }
    setHasChanges(true);
  };
  
  const handleVolumeChange = (values: number[]) => {
    const vol = values[0];
    setVolumeLevel(vol);
    setVolume(vol / 100);
    setHasChanges(true);
  };
  
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
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Settings className="h-6 w-6" />
            Settings
          </h1>
          <p className="text-muted-foreground">
            Configure Smart Kanban to match your workflow
          </p>
        </div>
        {hasChanges && (
          <Button onClick={handleSave}>
            <Save className="h-4 w-4 mr-2" />
            Save Changes
          </Button>
        )}
      </div>
      
      {/* Sound Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            {soundOn ? <Volume2 className="h-5 w-5" /> : <VolumeX className="h-5 w-5" />}
            Sound Notifications
          </CardTitle>
          <CardDescription>
            Audio feedback when tasks complete or need attention
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="sound-toggle">Enable Sounds</Label>
            <Switch
              id="sound-toggle"
              checked={soundOn}
              onCheckedChange={handleSoundToggle}
            />
          </div>
          
          {soundOn && (
            <div className="space-y-2">
              <Label>Volume</Label>
              <div className="flex items-center gap-4">
                <Slider
                  value={[volumeLevel]}
                  onValueChange={handleVolumeChange}
                  max={100}
                  step={5}
                  className="flex-1"
                />
                <span className="text-sm text-muted-foreground w-12">
                  {volumeLevel}%
                </span>
              </div>
              <div className="flex gap-2 mt-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => playSound("success")}
                >
                  Test Success
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => playSound("error")}
                >
                  Test Error
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => playSound("warning")}
                >
                  Test Warning
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
      
      {/* Editor Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
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
            <Select value={editor} onValueChange={handleEditorChange}>
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
      
      {/* Agent Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
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
              onChange={(v) => {
                setDefaultAgent(v);
                setHasChanges(true);
              }}
              showDetails
            />
          </div>
        </CardContent>
      </Card>
      
      {/* Budget Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
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
                  onChange={e => handleBudgetChange("daily", parseFloat(e.target.value) || 0)}
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
                  onChange={e => handleBudgetChange("weekly", parseFloat(e.target.value) || 0)}
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
                  onChange={e => handleBudgetChange("monthly", parseFloat(e.target.value) || 0)}
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
                onValueChange={(v) => handleBudgetChange("warningThreshold", v[0])}
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
              onCheckedChange={(v) => handleBudgetChange("pauseOnExceed", v)}
            />
          </div>
        </CardContent>
      </Card>
      
      {/* Keyboard Shortcuts */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
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
    </div>
  );
}
