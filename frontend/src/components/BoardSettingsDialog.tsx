import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { Switch } from "@/components/ui/switch";
import { AlertCircle, Info, Loader2, RotateCcw, ShieldAlert, Trash2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { TeamSettings } from "@/components/TeamSettings";
import { useBoard } from "@/contexts/BoardContext";
import { useUIStore } from "@/stores/uiStore";

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
  const { currentBoard } = useBoard();
  const boardSettingsTab = useUIStore((s) => s.boardSettingsTab);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deletingBoard, setDeletingBoard] = useState(false);
  const [hasOverrides, setHasOverrides] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [showDeleteTicketsConfirm, setShowDeleteTicketsConfirm] = useState(false);
  const [showDeleteBoardConfirm, setShowDeleteBoardConfirm] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");

  // Form state
  const [executorModel, setExecutorModel] = useState<string | null>("auto");
  const [timeoutSecs, setTimeoutSecs] = useState(300);
  const [preferredExecutor, setPreferredExecutor] = useState("cursor-agent");
  const [yoloMode, setYoloMode] = useState(false);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preferredExecutor]);

  // Load current config
  useEffect(() => {
    if (open) {
      loadConfig();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
          setTimeoutSecs(execConfig.timeout);
        }
        if (execConfig.preferred_executor !== undefined) {
          setPreferredExecutor(execConfig.preferred_executor);
        }
        if (execConfig.yolo_mode !== undefined) {
          setYoloMode(execConfig.yolo_mode);
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
          timeout: timeoutSecs,
          preferred_executor: preferredExecutor,
          yolo_mode: yoloMode,
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
    setSaving(true);
    try {
      await clearBoardConfig(boardId);
      toast.success("Board settings reset to defaults");
      setExecutorModel("auto");
      setTimeoutSecs(300);
      setPreferredExecutor("cursor-agent");
      setYoloMode(false);
      setHasOverrides(false);
      onOpenChange(false);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to reset settings";
      toast.error(message);
    } finally {
      setSaving(false);
      setShowResetConfirm(false);
    }
  };

  const handleCancel = () => {
    onOpenChange(false);
  };

  const handleDeleteAllTickets = async () => {
    if (deleteConfirmText !== "DELETE") {
      toast.error("You must type 'DELETE' exactly to confirm");
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
      setShowDeleteTicketsConfirm(false);
      setDeleteConfirmText("");
    }
  };

  const handleDeleteBoard = async () => {
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
      setShowDeleteBoardConfirm(false);
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
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[650px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Board Settings</DialogTitle>
          <DialogDescription>
            Configure execution settings and agent team for this board.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue={boardSettingsTab} className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="execution">Execution</TabsTrigger>
            <TabsTrigger value="team">Agent Team</TabsTrigger>
          </TabsList>

          <TabsContent value="team" className="mt-4">
            <TeamSettings boardId={boardId} />
          </TabsContent>

          <TabsContent value="execution" className="mt-4">

        <div className="space-y-6 py-4">
          {hasOverrides && (
            <Alert>
              <Info className="h-4 w-4" />
              <AlertDescription>
                This board has custom execution settings configured.
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
              <span className="text-sm text-muted-foreground">{timeoutSecs}s</span>
            </div>
            <Slider
              id="timeout"
              min={60}
              max={900}
              step={30}
              value={[timeoutSecs]}
              onValueChange={(value) => setTimeoutSecs(value[0])}
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

          {/* YOLO Mode */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="yolo-mode" className="flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 text-amber-500" />
                  YOLO Mode
                </Label>
                <p className="text-xs text-muted-foreground">
                  Skip permission prompts for autonomous execution
                </p>
              </div>
              <Switch
                id="yolo-mode"
                checked={yoloMode}
                onCheckedChange={setYoloMode}
              />
            </div>
            {yoloMode && (
              <Alert variant="destructive" className="mt-2">
                <ShieldAlert className="h-4 w-4" />
                <AlertDescription className="text-xs">
                  YOLO mode runs AI agents with <code>--dangerously-skip-permissions</code>.
                  Changes are isolated in worktrees, but agents can execute arbitrary commands
                  without approval.
                </AlertDescription>
              </Alert>
            )}
          </div>

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
                onClick={() => setShowDeleteTicketsConfirm(true)}
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
                onClick={() => setShowDeleteBoardConfirm(true)}
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

          </TabsContent>
        </Tabs>

        <DialogFooter className="flex items-center justify-between sm:justify-between">
          <Button
            type="button"
            variant="outline"
            onClick={() => setShowResetConfirm(true)}
            disabled={!hasOverrides || saving}
            className="gap-2"
          >
            <RotateCcw className="h-4 w-4" />
            Reset to Defaults
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

    {/* Reset Confirm */}
    <AlertDialog open={showResetConfirm} onOpenChange={setShowResetConfirm}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Reset Board Settings?</AlertDialogTitle>
          <AlertDialogDescription>
            This will reset all board settings to defaults.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={handleReset}>Reset</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    {/* Delete All Tickets Confirm */}
    <AlertDialog open={showDeleteTicketsConfirm} onOpenChange={(open) => {
      setShowDeleteTicketsConfirm(open);
      if (!open) setDeleteConfirmText("");
    }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete All Tickets?</AlertDialogTitle>
          <AlertDialogDescription>
            This will permanently delete all tickets, jobs, revisions, workspaces, and evidence files. This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="py-2">
          <Label htmlFor="delete-confirm">Type DELETE to confirm:</Label>
          <Input
            id="delete-confirm"
            value={deleteConfirmText}
            onChange={(e) => setDeleteConfirmText(e.target.value)}
            placeholder="DELETE"
            className="mt-2"
          />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleDeleteAllTickets}
            disabled={deleteConfirmText !== "DELETE"}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            Delete All
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    {/* Delete Board Confirm */}
    <AlertDialog open={showDeleteBoardConfirm} onOpenChange={setShowDeleteBoardConfirm}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete Board?</AlertDialogTitle>
          <AlertDialogDescription>
            This will delete the board and all its tickets. This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleDeleteBoard}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            Delete Board
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    </>
  );
}
