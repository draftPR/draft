import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { getGlobalSettings, updateGlobalSettings } from "@/services/api";
import { toast } from "sonner";
import { Info, Loader2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface GlobalSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const EXECUTOR_OPTIONS = [
  { id: "cursor-agent", name: "Cursor Agent (Headless)" },
  { id: "claude", name: "Claude Code CLI (Headless)" },
  { id: "cursor", name: "Cursor IDE (Interactive)" },
];

export function GlobalSettingsDialog({
  open,
  onOpenChange,
}: GlobalSettingsDialogProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // Form state
  const [executorModel, setExecutorModel] = useState<string>("auto");
  const [timeoutValue, setTimeoutValue] = useState(600);
  const [preferredExecutor, setPreferredExecutor] = useState("cursor-agent");
  const [configPath, setConfigPath] = useState("");

  // Load current config
  useEffect(() => {
    if (open) {
      loadConfig();
    }
  }, [open]);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const response = await getGlobalSettings();
      setConfigPath(response.config_path);

      const execConfig = response.execute_config;
      if (execConfig.timeout !== undefined) {
        setTimeoutValue(execConfig.timeout);
      }
      if (execConfig.preferred_executor !== undefined) {
        setPreferredExecutor(execConfig.preferred_executor);
      }
      if (execConfig.executor_model !== undefined) {
        setExecutorModel(execConfig.executor_model || "auto");
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load settings";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateGlobalSettings({
        execute_config: {
          executor_model: executorModel,
          timeout: timeoutValue,
          preferred_executor: preferredExecutor,
        },
      });
      toast.success("Settings saved");
      onOpenChange(false);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to save settings";
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    onOpenChange(false);
  };

  if (loading) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[550px]">
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[550px]">
        <DialogHeader>
          <DialogTitle>AI Agent Configuration</DialogTitle>
          <DialogDescription>
            Configure which AI agent and model to use for automated coding.
            Changes are saved to the board configuration.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription className="text-xs">
              These settings control how AI agents execute tickets across all boards.
              <br />
              Saved to: {configPath}
            </AlertDescription>
          </Alert>

          {/* Preferred Executor */}
          <div className="space-y-2">
            <Label htmlFor="executor">AI Coding Agent</Label>
            <Select value={preferredExecutor} onValueChange={setPreferredExecutor}>
              <SelectTrigger id="executor">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EXECUTOR_OPTIONS.map((exec) => (
                  <SelectItem key={exec.id} value={exec.id}>
                    {exec.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Choose which CLI tool to use for automated code execution
            </p>
          </div>

          {/* Model Selection */}
          <div className="space-y-2">
            <Label>AI Model</Label>
            <div className="flex h-10 w-full items-center rounded-md border border-input bg-muted/50 px-3 text-sm text-muted-foreground">
              Auto (intelligently selects the best model for each task)
            </div>
            <p className="text-xs text-muted-foreground">
              Per-model selection can be configured in board settings or executor profiles.
            </p>
          </div>

          {/* Timeout Slider */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="timeout">Execution Timeout</Label>
              <span className="text-sm text-muted-foreground">{timeoutValue}s</span>
            </div>
            <Slider
              id="timeout"
              min={60}
              max={900}
              step={30}
              value={[timeoutValue]}
              onValueChange={(value) => setTimeoutValue(value[0])}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Maximum time for AI agent to run (60-900 seconds)
            </p>
          </div>
        </div>

        <DialogFooter className="flex items-center justify-between sm:justify-end">
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleCancel}
              disabled={saving}
            >
              Cancel
            </Button>
            <Button type="button" onClick={handleSave} disabled={saving}>
              {saving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                "Save"
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
