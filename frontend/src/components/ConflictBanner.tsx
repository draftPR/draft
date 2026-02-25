/**
 * ConflictBanner -- shows conflict state, push status, and resolution actions
 * for a ticket's worktree.
 */

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import {
  rebaseTicket,
  continueRebase,
  abortConflict,
  pushTicketBranch,
  forcePushTicketBranch,
} from "@/services/api";
import type { ConflictStatusResponse, PushStatusResponse } from "@/types/api";
import {
  AlertTriangle,
  GitBranch,
  RotateCcw,
  XCircle,
  Loader2,
  FileWarning,
  ArrowDown,
  ArrowUp,
  Upload,
} from "lucide-react";
import { toast } from "sonner";

interface ConflictBannerProps {
  ticketId: string;
  conflictStatus: ConflictStatusResponse;
  pushStatus?: PushStatusResponse | null;
  onResolved: () => void;
}

export function ConflictBanner({
  ticketId,
  conflictStatus,
  pushStatus,
  onResolved,
}: ConflictBannerProps) {
  const [rebaseLoading, setRebaseLoading] = useState(false);
  const [continueLoading, setContinueLoading] = useState(false);
  const [abortLoading, setAbortLoading] = useState(false);
  const [pushLoading, setPushLoading] = useState(false);
  const [forcePushLoading, setForcePushLoading] = useState(false);
  const [showForcePushConfirm, setShowForcePushConfirm] = useState(false);

  const handleRebase = useCallback(async () => {
    setRebaseLoading(true);
    try {
      const result = await rebaseTicket(ticketId);
      if (result.success) {
        toast.success("Rebase completed");
        onResolved();
      } else if (result.has_conflicts) {
        toast.warning("Rebase paused", {
          description: `Conflicts in ${result.conflicted_files.length} file(s). Resolve and continue.`,
        });
        onResolved();
      } else {
        toast.error("Rebase failed", { description: result.message });
      }
    } catch (err) {
      toast.error("Rebase failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setRebaseLoading(false);
    }
  }, [ticketId, onResolved]);

  const handleContinue = useCallback(async () => {
    setContinueLoading(true);
    try {
      const result = await continueRebase(ticketId);
      if (result.success) {
        toast.success("Rebase completed");
        onResolved();
      } else if (result.has_conflicts) {
        toast.warning("More conflicts found", {
          description: `${result.conflicted_files.length} file(s) still in conflict`,
        });
        onResolved();
      } else {
        toast.error("Continue failed", { description: result.message });
      }
    } catch (err) {
      toast.error("Continue failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setContinueLoading(false);
    }
  }, [ticketId, onResolved]);

  const handleAbort = useCallback(async () => {
    setAbortLoading(true);
    try {
      const result = await abortConflict(ticketId);
      if (result.success) {
        toast.success("Operation aborted");
        onResolved();
      } else {
        toast.error("Abort failed", { description: result.message });
      }
    } catch (err) {
      toast.error("Abort failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setAbortLoading(false);
    }
  }, [ticketId, onResolved]);

  const handlePush = useCallback(async () => {
    setPushLoading(true);
    try {
      const result = await pushTicketBranch(ticketId);
      if (result.success) {
        toast.success("Branch pushed to remote");
        onResolved();
      } else {
        toast.error("Push failed", { description: result.message });
      }
    } catch (err) {
      toast.error("Push failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setPushLoading(false);
    }
  }, [ticketId, onResolved]);

  const handleForcePush = useCallback(async () => {
    setForcePushLoading(true);
    try {
      const result = await forcePushTicketBranch(ticketId);
      if (result.success) {
        toast.success("Branch force-pushed to remote");
        setShowForcePushConfirm(false);
        onResolved();
      } else {
        toast.error("Force-push failed", { description: result.message });
      }
    } catch (err) {
      toast.error("Force-push failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setForcePushLoading(false);
    }
  }, [ticketId, onResolved]);

  const { divergence } = conflictStatus;
  const showDivergenceOnly = !conflictStatus.has_conflict && divergence && !divergence.up_to_date;

  // Push status banner (branch is ahead of remote)
  if (pushStatus?.needs_push && !conflictStatus.has_conflict) {
    return (
      <div className="rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 p-4 space-y-3">
        <div className="flex items-start gap-2">
          <ArrowUp className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-[13px] font-medium text-blue-700 dark:text-blue-300">
              {pushStatus.ahead} local commit{pushStatus.ahead !== 1 ? "s" : ""} not pushed
            </p>
            <p className="text-[12px] text-blue-600 dark:text-blue-400 mt-1">
              {pushStatus.remote_exists
                ? "Push to update the remote branch."
                : "Push to create the remote branch."}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={handlePush}
            disabled={pushLoading}
            className="flex-1"
          >
            {pushLoading ? (
              <Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" />
            ) : (
              <Upload className="h-3.5 w-3.5 mr-2" />
            )}
            Push
          </Button>
          {pushStatus.remote_exists && (
            <>
              {showForcePushConfirm ? (
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={handleForcePush}
                    disabled={forcePushLoading}
                  >
                    {forcePushLoading ? (
                      <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                    ) : null}
                    Confirm
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setShowForcePushConfirm(false)}
                  >
                    Cancel
                  </Button>
                </div>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowForcePushConfirm(true)}
                  className="text-amber-600 hover:text-amber-700 border-amber-200"
                >
                  Force Push
                </Button>
              )}
            </>
          )}
        </div>
      </div>
    );
  }

  // Branch is behind but no active conflict -- offer rebase
  if (showDivergenceOnly) {
    return (
      <div className="rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 p-4 space-y-3">
        <div className="flex items-start gap-2">
          <ArrowDown className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-[13px] font-medium text-amber-700 dark:text-amber-300">
              Branch is {divergence.behind} commit{divergence.behind !== 1 ? "s" : ""} behind main
            </p>
            <p className="text-[12px] text-amber-600 dark:text-amber-400 mt-1">
              Rebase to incorporate latest changes before merging.
            </p>
          </div>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={handleRebase}
          disabled={rebaseLoading}
          className="w-full"
        >
          {rebaseLoading ? (
            <Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" />
          ) : (
            <GitBranch className="h-3.5 w-3.5 mr-2" />
          )}
          Rebase onto main
        </Button>
      </div>
    );
  }

  // Active conflict
  if (!conflictStatus.has_conflict) return null;

  const opLabel = conflictStatus.operation === "rebase"
    ? "Rebase"
    : conflictStatus.operation === "merge"
    ? "Merge"
    : conflictStatus.operation === "cherry_pick"
    ? "Cherry-pick"
    : "Operation";

  return (
    <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start gap-2">
        <AlertTriangle className="h-4 w-4 text-red-500 mt-0.5 shrink-0" />
        <div>
          <p className="text-[13px] font-medium text-red-700 dark:text-red-300">
            {opLabel} conflict
          </p>
          <p className="text-[12px] text-red-600 dark:text-red-400 mt-1">
            {conflictStatus.conflicted_files.length} file{conflictStatus.conflicted_files.length !== 1 ? "s" : ""} with conflicts
          </p>
        </div>
      </div>

      {/* Conflicted files list */}
      {conflictStatus.conflicted_files.length > 0 && (
        <div className="bg-red-100/50 dark:bg-red-900/30 rounded-md p-2 space-y-1">
          {conflictStatus.conflicted_files.map((file) => (
            <div key={file} className="flex items-center gap-2 text-[12px]">
              <FileWarning className="h-3 w-3 text-red-400 shrink-0" />
              <code className="text-red-700 dark:text-red-300 font-mono truncate">
                {file}
              </code>
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2">
        {conflictStatus.can_continue && (
          <Button
            size="sm"
            variant="outline"
            onClick={handleContinue}
            disabled={continueLoading}
            className="flex-1"
          >
            {continueLoading ? (
              <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
            ) : (
              <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
            )}
            Continue
          </Button>
        )}
        {conflictStatus.can_abort && (
          <Button
            size="sm"
            variant="outline"
            onClick={handleAbort}
            disabled={abortLoading}
            className="flex-1 text-red-600 hover:text-red-700 border-red-200"
          >
            {abortLoading ? (
              <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
            ) : (
              <XCircle className="h-3.5 w-3.5 mr-1.5" />
            )}
            Abort
          </Button>
        )}
      </div>
    </div>
  );
}
