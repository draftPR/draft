/**
 * MergeStrategyPicker -- Pick merge strategy (squash/merge/rebase) for a PR.
 */

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { mergePR } from "@/services/api";
import type { PRMergeStrategy } from "@/types/api";
import {
  GitMerge,
  Loader2,
  GitBranch,
  Layers,
} from "lucide-react";
import { toast } from "sonner";

interface MergeStrategyPickerProps {
  ticketId: string;
  prNumber: number;
  onMerged: () => void;
}

const strategies: {
  value: PRMergeStrategy;
  label: string;
  description: string;
  icon: React.ReactNode;
}[] = [
  {
    value: "squash",
    label: "Squash and merge",
    description: "Combine all commits into one",
    icon: <Layers className="h-3.5 w-3.5" />,
  },
  {
    value: "merge",
    label: "Merge commit",
    description: "Preserve all commits with merge commit",
    icon: <GitMerge className="h-3.5 w-3.5" />,
  },
  {
    value: "rebase",
    label: "Rebase and merge",
    description: "Rebase commits onto base branch",
    icon: <GitBranch className="h-3.5 w-3.5" />,
  },
];

export function MergeStrategyPicker({
  ticketId,
  prNumber,
  onMerged,
}: MergeStrategyPickerProps) {
  const [selected, setSelected] = useState<PRMergeStrategy>("squash");
  const [merging, setMerging] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const handleMerge = useCallback(async () => {
    setMerging(true);
    try {
      const result = await mergePR(ticketId, selected);
      if (result.success) {
        toast.success(`PR #${prNumber} merged`, {
          description: result.message,
        });
        onMerged();
      } else {
        toast.error("Merge failed", { description: result.message });
      }
    } catch (err) {
      toast.error("Merge failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setMerging(false);
      setShowConfirm(false);
    }
  }, [ticketId, prNumber, selected, onMerged]);

  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-3">
      <p className="text-[13px] font-medium">Merge PR #{prNumber}</p>

      {/* Strategy selection */}
      <div className="space-y-1.5">
        {strategies.map((s) => (
          <label
            key={s.value}
            className={`flex items-start gap-2.5 p-2 rounded-md cursor-pointer border transition-colors ${
              selected === s.value
                ? "border-primary bg-primary/5"
                : "border-transparent hover:bg-muted/50"
            }`}
          >
            <input
              type="radio"
              name="merge-strategy"
              value={s.value}
              checked={selected === s.value}
              onChange={() => setSelected(s.value)}
              className="mt-0.5"
            />
            <div className="flex items-start gap-2">
              <span className="mt-0.5 text-muted-foreground">{s.icon}</span>
              <div>
                <p className="text-[12px] font-medium">{s.label}</p>
                <p className="text-[11px] text-muted-foreground">
                  {s.description}
                </p>
              </div>
            </div>
          </label>
        ))}
      </div>

      {/* Merge button */}
      {showConfirm ? (
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="destructive"
            onClick={handleMerge}
            disabled={merging}
            className="flex-1"
          >
            {merging ? (
              <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
            ) : (
              <GitMerge className="h-3.5 w-3.5 mr-1.5" />
            )}
            Confirm Merge
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setShowConfirm(false)}
          >
            Cancel
          </Button>
        </div>
      ) : (
        <Button
          size="sm"
          onClick={() => setShowConfirm(true)}
          className="w-full"
        >
          <GitMerge className="h-3.5 w-3.5 mr-1.5" />
          Merge Pull Request
        </Button>
      )}
    </div>
  );
}
