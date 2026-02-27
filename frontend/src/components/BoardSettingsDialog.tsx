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
import { clearBoardConfig, getBoardConfig, updateBoardConfig, getExecutorModels, deleteAllTickets, deleteBoard, type ExecutorModel } from "@/services/api";
import { toast } from "sonner";
import { AlertCircle, Info, Loader2, RotateCcw, Trash2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface BoardSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  boardId: string;
  onTicketsDeleted?: () => void;
  onBoardDeleted?: () => void;
}

const EXECUTOR_OPTIONS = [
  { id: "cursor-agent", name: "Cursor Agent (Headless)" },
  { id: "claude", name: "Claude Code CLI (Headless)" },
  { id: "cursor", name: "Cursor IDE (Interactive)" },
];

export function BoardSettingsDialog({
  open,
  onOpenChange,
  boardId,
  onTicketsDeleted,
  onBoardDeleted,
}: BoardSettingsDialogProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deletingBoard, setDeletingBoard] = useState(false);
  const [hasOverrides, setHasOverrides] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);

  // Form state
  const [executorModel, setExecutorModel] = useState<string | null>("auto");
  const [timeout, setTimeout] = useState(300);
  const [preferredExecutor, setPreferredExecutor] = useState("cursor-agent");
  const [modelOptions, setModelOptions] = useState<ExecutorModel[]>([]);

  // Fetch models when executor changes
  useEffect(() => {
    const fetchModels = async () => {
      setLoadingModels(true);
      try {
        const models = await getExecutorModels(preferredExecutor);
        setModelOptions(models);

        // If current model is not valid for new executor, reset to auto
        if (executorModel && executorModel !== "auto") {
          const isValidModel = models.some((opt: { id: string }) => opt.id === executorModel);
          if (!isValidModel) {
            setExecutorModel("auto");
          }
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load models";
        toast.error(message);
        setModelOptions([]);
      } finally {
        setLoadingModels(false);
      }
    };

    if (preferredExecutor) {
      fetchModels();
    }
  }, [preferredExecutor]);

  // Load current config
  useEffect(() => {
    if (open) {
      loadConfig();
    }
  }, [open, boardId]);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const response = await getBoardConfig(boardId);
      setHasOverrides(response.has_overrides);

      // Load execute config if present
      if (response.config?.execute_config) {
        const execConfig = response.config.execute_config;
        if (execConfig.executor_model !== undefined) {
          setExecutorModel(execConfig.executor_model);
        }
        if (execConfig.timeout !== undefined) {
          setTimeout(execConfig.timeout);
        }
        if (execConfig.preferred_executor !== undefined) {
          setPreferredExecutor(execConfig.preferred_executor);
        }
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load board config";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateBoardConfig(boardId, {
        execute_config: {
          executor_model: executorModel,
          timeout,
          preferred_executor: preferredExecutor,
        },
      });
      toast.success("Board settings saved");
      onOpenChange(false);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to save settings";
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (
      !confirm(
        "Reset all board-level overrides? Settings will revert to smartkanban.yaml defaults."
      )
    ) {
      return;
    }

    setSaving(true);
    try {
      await clearBoardConfig(boardId);
      toast.success("Board settings reset to YAML defaults");
      setExecutorModel("auto");
      setTimeout(300);
      setPreferredExecutor("cursor-agent");
      setHasOverrides(false);
      onOpenChange(false);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to reset settings";
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    onOpenChange(false);
  };

  const handleDeleteAllTickets = async () => {
    const confirmMsg = "⚠️ DELETE ALL TICKETS?\n\n" +
      "This will permanently delete:\n" +
      "• All tickets\n" +
      "• All jobs\n" +
      "• All revisions\n" +
      "• All workspaces\n" +
      "• All evidence files\n\n" +
      "This action CANNOT be undone!\n\n" +
      "Type 'DELETE' to confirm:";

    const userInput = prompt(confirmMsg);
    if (userInput !== "DELETE") {
      if (userInput !== null) {
        toast.error("Deletion cancelled - you must type 'DELETE' exactly");
      }
      return;
    }

    setDeleting(true);
    try {
      const result = await deleteAllTickets(boardId);
      toast.success(result.message);
      onTicketsDeleted?.();
      onOpenChange(false);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to delete tickets";
      toast.error(message);
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteBoard = async () => {
    if (
      !confirm(
        "Are you sure? This will delete the board and all its tickets. This action cannot be undone."
      )
    ) {
      return;
    }

    setDeletingBoard(true);
    try {
      await deleteBoard(boardId);
      toast.success("Board deleted successfully");
      onOpenChange(false);
      onBoardDeleted?.();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to delete board";
      toast.error(message);
    } finally {
      setDeletingBoard(false);
    }
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
          <DialogTitle>Board Settings</DialogTitle>
          <DialogDescription>
            Configure board-level overrides for execution settings.
            These override smartkanban.yaml configuration.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {hasOverrides && (
            <Alert>
              <Info className="h-4 w-4" />
              <AlertDescription>
                This board has custom settings that override the repository's smartkanban.yaml
              </AlertDescription>
            </Alert>
          )}

          {/* Model Selection */}
          <div className="space-y-2">
            <Label htmlFor="model">Execution Model</Label>
            <Select
              value={executorModel || "auto"}
              onValueChange={(value) => setExecutorModel(value)}
              disabled={loadingModels}
            >
              <SelectTrigger id="model" disabled={loadingModels}>
                {loadingModels ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Loading models...
                  </span>
                ) : (
                  <SelectValue placeholder="Select model" />
                )}
              </SelectTrigger>
              <SelectContent>
                {modelOptions.map((model) => (
                  <SelectItem key={model.id} value={model.id}>
                    <div className="flex flex-col">
                      <span>{model.name}</span>
                      <span className="text-xs text-muted-foreground">
                        {model.description}
                      </span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Default: Auto (intelligent model selection)
            </p>
          </div>

          {/* Timeout Slider */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="timeout">Execution Timeout</Label>
              <span className="text-sm text-muted-foreground">{timeout}s</span>
            </div>
            <Slider
              id="timeout"
              min={60}
              max={900}
              step={30}
              value={[timeout]}
              onValueChange={(value) => setTimeout(value[0])}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Maximum time for executor CLI to run (60-900 seconds)
            </p>
          </div>

          {/* Preferred Executor */}
          <div className="space-y-2">
            <Label htmlFor="executor">Preferred Executor</Label>
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
              Which CLI tool to use for code execution. Each executor supports different model options.
            </p>
          </div>

          {/* Info about other settings */}
          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription className="text-xs">
              Additional settings (YOLO mode, verify commands, etc.) can be configured
              in smartkanban.yaml in your repository.
            </AlertDescription>
          </Alert>

          {/* Danger Zone */}
          <div className="border-t pt-6 mt-6">
            <div className="space-y-3">
              <div className="flex items-start gap-2">
                <AlertCircle className="h-5 w-5 text-red-600 mt-0.5" />
                <div>
                  <h3 className="text-sm font-semibold text-red-600">Danger Zone</h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    Destructive actions that cannot be undone
                  </p>
                </div>
              </div>
              <Button
                type="button"
                variant="destructive"
                onClick={handleDeleteAllTickets}
                disabled={deleting || deletingBoard || saving}
                className="w-full gap-2"
              >
                {deleting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Deleting...
                  </>
                ) : (
                  <>
                    <Trash2 className="h-4 w-4" />
                    Delete All Tickets
                  </>
                )}
              </Button>
              <Button
                type="button"
                variant="destructive"
                onClick={handleDeleteBoard}
                disabled={deleting || deletingBoard || saving}
                className="w-full gap-2"
              >
                {deletingBoard ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Deleting Board...
                  </>
                ) : (
                  <>
                    <Trash2 className="h-4 w-4" />
                    Delete Board
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>

        <DialogFooter className="flex items-center justify-between sm:justify-between">
          <Button
            type="button"
            variant="outline"
            onClick={handleReset}
            disabled={!hasOverrides || saving}
            className="gap-2"
          >
            <RotateCcw className="h-4 w-4" />
            Reset to YAML
          </Button>
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
