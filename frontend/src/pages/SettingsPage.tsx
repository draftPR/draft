import { useState } from "react";
import { useSearchParams } from "react-router";
import { Settings, Save, Wrench, Loader2, Trash2, FolderGit, HardDrive } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  EditorSettingsCard,
  AgentSettingsCard,
  BudgetSettingsCard,
  KeyboardShortcutsCard,
  WelcomeTutorialCard,
  PlannerSettingsCard,
  ExecutorProfilesCard,
  VerificationCommandsCard,
  type BudgetSettings,
  loadBudgetSettings,
  saveBudgetSettings,
} from "@/components/SettingsPanel";
import {
  getPreferredEditor,
  setPreferredEditor,
  type EditorType,
} from "@/services/editorIntegration";
import { playSound } from "@/services/soundNotifications";
import { runCleanup } from "@/services/api";
import type { CleanupResponse } from "@/types/api";
import { toast } from "sonner";

export function SettingsPage() {
  const [searchParams] = useSearchParams();
  const defaultTab = searchParams.get("tab") || "general";
  const [editor, setEditor] = useState<EditorType>(getPreferredEditor());
  const [defaultAgent, setDefaultAgent] = useState(() =>
    localStorage.getItem("draft_default_agent") ?? "claude"
  );
  const [budget, setBudget] = useState<BudgetSettings>(loadBudgetSettings);
  const [hasChanges, setHasChanges] = useState(false);

  // Maintenance state
  const [cleanupLoading, setCleanupLoading] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<CleanupResponse | null>(null);
  const [cleanupDryRun, setCleanupDryRun] = useState(true);
  const [cleanupWorktrees, setCleanupWorktrees] = useState(true);
  const [cleanupEvidence, setCleanupEvidence] = useState(true);

  const handleCleanup = async () => {
    setCleanupLoading(true);
    setCleanupResult(null);
    try {
      const result = await runCleanup({
        dry_run: cleanupDryRun,
        delete_worktrees: cleanupWorktrees,
        delete_evidence: cleanupEvidence,
      });
      setCleanupResult(result);
      if (result.dry_run) {
        toast.info("Dry run complete", {
          description: "No files were actually deleted. Review the results below.",
        });
      } else {
        toast.success("Cleanup complete", {
          description: `Deleted ${result.worktrees_deleted} worktree(s) and ${result.evidence_files_deleted} evidence file(s).`,
        });
        playSound("success");
      }
    } catch (err) {
      toast.error("Cleanup failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setCleanupLoading(false);
    }
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
      localStorage.setItem("draft_default_agent", defaultAgent);
    }
    setHasChanges(false);
    playSound("success");
  };

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Settings
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure Draft to match your workflow
          </p>
        </div>
        {hasChanges && (
          <Button onClick={handleSave}>
            <Save className="h-4 w-4 mr-2" />
            Save Changes
          </Button>
        )}
      </div>

      <Tabs defaultValue={defaultTab}>
        <TabsList>
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="executors">Executors</TabsTrigger>
          <TabsTrigger value="budget">Budget</TabsTrigger>
          <TabsTrigger value="maintenance">Maintenance</TabsTrigger>
        </TabsList>

        <TabsContent value="general" className="space-y-6 mt-4">
          <EditorSettingsCard editor={editor} onEditorChange={handleEditorChange} />
          <KeyboardShortcutsCard />
          <WelcomeTutorialCard />
        </TabsContent>

        <TabsContent value="executors" className="space-y-6 mt-4">
          <AgentSettingsCard
            defaultAgent={defaultAgent}
            onAgentChange={(v) => { setDefaultAgent(v); setHasChanges(true); }}
          />
          <ExecutorProfilesCard />
          <VerificationCommandsCard />
          <PlannerSettingsCard onDirty={() => setHasChanges(true)} />
        </TabsContent>

        <TabsContent value="budget" className="space-y-6 mt-4">
          <BudgetSettingsCard budget={budget} onBudgetChange={handleBudgetChange} />
        </TabsContent>

        <TabsContent value="maintenance" className="space-y-6 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="section-header flex items-center gap-2">
                <Wrench className="h-4 w-4" />
                Cleanup
              </CardTitle>
              <CardDescription>
                Remove stale worktrees and old evidence files to free up disk space.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Cleanup options */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label htmlFor="cleanup-dry-run" className="flex flex-col gap-1">
                    <span className="text-sm font-medium">Dry run</span>
                    <span className="text-xs text-muted-foreground font-normal">
                      Preview what would be deleted without actually deleting
                    </span>
                  </Label>
                  <Switch
                    id="cleanup-dry-run"
                    checked={cleanupDryRun}
                    onCheckedChange={setCleanupDryRun}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="cleanup-worktrees" className="flex flex-col gap-1">
                    <span className="text-sm font-medium flex items-center gap-1.5">
                      <FolderGit className="h-3.5 w-3.5" />
                      Delete stale worktrees
                    </span>
                    <span className="text-xs text-muted-foreground font-normal">
                      Remove worktrees for tickets in terminal states
                    </span>
                  </Label>
                  <Switch
                    id="cleanup-worktrees"
                    checked={cleanupWorktrees}
                    onCheckedChange={setCleanupWorktrees}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="cleanup-evidence" className="flex flex-col gap-1">
                    <span className="text-sm font-medium flex items-center gap-1.5">
                      <HardDrive className="h-3.5 w-3.5" />
                      Delete old evidence
                    </span>
                    <span className="text-xs text-muted-foreground font-normal">
                      Remove orphaned evidence files from completed jobs
                    </span>
                  </Label>
                  <Switch
                    id="cleanup-evidence"
                    checked={cleanupEvidence}
                    onCheckedChange={setCleanupEvidence}
                  />
                </div>
              </div>

              <Button
                onClick={handleCleanup}
                disabled={cleanupLoading || (!cleanupWorktrees && !cleanupEvidence)}
                variant={cleanupDryRun ? "outline" : "destructive"}
                className="w-full"
              >
                {cleanupLoading ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4 mr-2" />
                )}
                {cleanupDryRun ? "Preview Cleanup" : "Run Cleanup"}
              </Button>

              {/* Cleanup results */}
              {cleanupResult && (
                <div className="rounded-lg border bg-muted/50 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-medium">
                      {cleanupResult.dry_run ? "Dry Run Results" : "Cleanup Results"}
                    </h4>
                    {cleanupResult.dry_run && (
                      <span className="text-[10px] uppercase tracking-wide text-amber-600 dark:text-amber-400 font-medium bg-amber-100 dark:bg-amber-900/30 px-1.5 py-0.5 rounded">
                        Preview
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div className="space-y-1">
                      <p className="text-muted-foreground text-xs">Worktrees deleted</p>
                      <p className="font-medium">{cleanupResult.worktrees_deleted}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-muted-foreground text-xs">Worktrees failed</p>
                      <p className="font-medium">{cleanupResult.worktrees_failed}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-muted-foreground text-xs">Worktrees skipped</p>
                      <p className="font-medium">{cleanupResult.worktrees_skipped}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-muted-foreground text-xs">Evidence files deleted</p>
                      <p className="font-medium">{cleanupResult.evidence_files_deleted}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-muted-foreground text-xs">Evidence files failed</p>
                      <p className="font-medium">{cleanupResult.evidence_files_failed}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-muted-foreground text-xs">Disk space freed</p>
                      <p className="font-medium">
                        {cleanupResult.bytes_freed >= 1048576
                          ? `${(cleanupResult.bytes_freed / 1048576).toFixed(1)} MB`
                          : cleanupResult.bytes_freed >= 1024
                            ? `${(cleanupResult.bytes_freed / 1024).toFixed(1)} KB`
                            : `${cleanupResult.bytes_freed} bytes`}
                      </p>
                    </div>
                  </div>
                  {cleanupResult.details.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">Details</p>
                      <div className="max-h-40 overflow-y-auto rounded bg-background border p-2 space-y-0.5">
                        {cleanupResult.details.map((detail, i) => (
                          <p key={i} className="text-xs text-foreground font-mono">
                            {detail}
                          </p>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
