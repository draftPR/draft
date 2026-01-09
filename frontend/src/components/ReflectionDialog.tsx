import { useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { reflectOnTickets, bulkUpdatePriorities } from "@/services/api";
import type {
  ReflectionResult,
  SuggestedPriorityChange,
  PriorityBucket,
} from "@/types/api";
import {
  PRIORITY_BUCKET_LABELS,
  PRIORITY_BUCKET_COLORS,
  PRIORITY_BUCKET_VALUES,
} from "@/types/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Check,
  CheckCircle2,
  Info,
  Lightbulb,
  Loader2,
  Sparkles,
  X,
  XCircle,
  Zap,
} from "lucide-react";

interface ReflectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  goalId: string;
  goalTitle: string;
  onPrioritiesUpdated: () => void;
}

type SelectionState = Record<string, boolean>;

const QUALITY_CONFIG: Record<
  ReflectionResult["overall_quality"],
  { icon: typeof CheckCircle2; color: string; label: string }
> = {
  good: {
    icon: CheckCircle2,
    color: "text-emerald-500",
    label: "Good Quality",
  },
  needs_work: {
    icon: AlertTriangle,
    color: "text-amber-500",
    label: "Needs Work",
  },
  insufficient: {
    icon: XCircle,
    color: "text-red-500",
    label: "Insufficient",
  },
};

function PriorityBadge({ bucket }: { bucket: PriorityBucket }) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium text-white",
        PRIORITY_BUCKET_COLORS[bucket]
      )}
    >
      {bucket}
    </span>
  );
}

interface BlastRadiusSummary {
  total: number;
  up: number;
  down: number;
  toP0: number;
}

function computeBlastRadius(
  changes: SuggestedPriorityChange[],
  selected: SelectionState
): BlastRadiusSummary {
  const selectedChanges = changes.filter((c) => selected[c.ticket_id]);
  let up = 0;
  let down = 0;
  let toP0 = 0;

  for (const change of selectedChanges) {
    const currentVal = PRIORITY_BUCKET_VALUES[change.current_bucket];
    const suggestedVal = PRIORITY_BUCKET_VALUES[change.suggested_bucket];

    if (suggestedVal > currentVal) {
      up++;
    } else if (suggestedVal < currentVal) {
      down++;
    }

    if (change.suggested_bucket === "P0" && change.current_bucket !== "P0") {
      toP0++;
    }
  }

  return { total: selectedChanges.length, up, down, toP0 };
}

export function ReflectionDialog({
  open,
  onOpenChange,
  goalId,
  goalTitle,
  onPrioritiesUpdated,
}: ReflectionDialogProps) {
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [result, setResult] = useState<ReflectionResult | null>(null);
  const [selected, setSelected] = useState<SelectionState>({});
  const [expandedReasons, setExpandedReasons] = useState<Record<string, boolean>>({});

  const blastRadius = useMemo(() => {
    if (!result) return { total: 0, up: 0, down: 0, toP0: 0 };
    return computeBlastRadius(result.suggested_changes, selected);
  }, [result, selected]);

  const runReflection = async () => {
    setLoading(true);
    setResult(null);
    try {
      const reflectionResult = await reflectOnTickets(goalId);
      setResult(reflectionResult);
      // Pre-select all suggested changes
      const initial: SelectionState = {};
      const expanded: Record<string, boolean> = {};
      reflectionResult.suggested_changes.forEach((change) => {
        initial[change.ticket_id] = true;
        expanded[change.ticket_id] = true; // Start expanded to show rationale
      });
      setSelected(initial);
      setExpandedReasons(expanded);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Reflection failed";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handleApply = async () => {
    if (!result) return;

    const selectedChanges = result.suggested_changes.filter(
      (c) => selected[c.ticket_id]
    );
    if (selectedChanges.length === 0) {
      toast.error("No changes selected");
      return;
    }

    // Verify user has reviewed rationales (at least one must be expanded)
    const anyExpanded = selectedChanges.some((c) => expandedReasons[c.ticket_id]);
    if (!anyExpanded && selectedChanges.length > 0) {
      toast.error("Please review the rationale for at least one change before applying");
      return;
    }

    // Check if any changes are to P0
    const hasP0Changes = selectedChanges.some(
      (c) => c.suggested_bucket === "P0" && c.current_bucket !== "P0"
    );

    setApplying(true);
    try {
      const response = await bulkUpdatePriorities({
        goal_id: goalId,
        updates: selectedChanges.map((c) => ({
          ticket_id: c.ticket_id,
          priority_bucket: c.suggested_bucket,
        })),
        // Server requires allow_p0=true for P0 assignments
        allow_p0: hasP0Changes,
      });

      if (response.updated_count > 0) {
        toast.success(
          `Updated ${response.updated_count} ticket${response.updated_count > 1 ? "s" : ""}`
        );
        onPrioritiesUpdated();
        onOpenChange(false);
      }
      if (response.failed_count > 0) {
        toast.error(`Failed to update ${response.failed_count} tickets`);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Update failed";
      toast.error(message);
    } finally {
      setApplying(false);
    }
  };

  const toggleChange = (ticketId: string) => {
    setSelected((prev) => ({
      ...prev,
      [ticketId]: !prev[ticketId],
    }));
  };

  const toggleReason = (ticketId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedReasons((prev) => ({
      ...prev,
      [ticketId]: !prev[ticketId],
    }));
  };

  const selectedCount = Object.values(selected).filter(Boolean).length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            AI Reflection
          </DialogTitle>
          <DialogDescription>
            Analyze proposed tickets for "{goalTitle}"
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-4 pr-1">
          {/* Run reflection button (initial state) */}
          {!loading && !result && (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Lightbulb className="h-12 w-12 text-muted-foreground mb-4" />
              <p className="text-muted-foreground mb-4">
                Run AI reflection to evaluate ticket quality, identify coverage
                gaps, and get priority suggestions.
              </p>
              <Button onClick={runReflection}>
                <Sparkles className="mr-2 h-4 w-4" />
                Run Reflection
              </Button>
            </div>
          )}

          {/* Loading state */}
          {loading && (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
              <p className="text-muted-foreground">Analyzing tickets...</p>
            </div>
          )}

          {/* Results */}
          {result && (
            <>
              {/* Quality Assessment */}
              <div className="rounded-lg border p-4">
                <div className="flex items-center gap-2 mb-2">
                  {(() => {
                    const config = QUALITY_CONFIG[result.overall_quality];
                    const Icon = config.icon;
                    return (
                      <>
                        <Icon className={cn("h-5 w-5", config.color)} />
                        <span className="font-medium">{config.label}</span>
                      </>
                    );
                  })()}
                </div>
                <p className="text-sm text-muted-foreground">
                  {result.quality_notes}
                </p>
              </div>

              {/* Coverage Gaps */}
              {result.coverage_gaps.length > 0 && (
                <div className="rounded-lg border p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Info className="h-5 w-5 text-blue-500" />
                    <span className="font-medium">Coverage Gaps</span>
                  </div>
                  <ul className="space-y-1">
                    {result.coverage_gaps.map((gap, i) => (
                      <li
                        key={i}
                        className="text-sm text-muted-foreground flex items-start gap-2"
                      >
                        <span className="text-muted-foreground/50">•</span>
                        {gap}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Blast Radius Summary Banner */}
              {result.suggested_changes.length > 0 && blastRadius.total > 0 && (
                <div
                  className={cn(
                    "rounded-lg border p-3 flex items-center gap-3",
                    blastRadius.toP0 > 0
                      ? "border-red-500/50 bg-red-500/5"
                      : "border-amber-500/50 bg-amber-500/5"
                  )}
                >
                  <Zap
                    className={cn(
                      "h-5 w-5 flex-shrink-0",
                      blastRadius.toP0 > 0 ? "text-red-500" : "text-amber-500"
                    )}
                  />
                  <div className="text-sm">
                    <span className="font-medium">
                      You are changing {blastRadius.total} ticket
                      {blastRadius.total !== 1 ? "s" : ""}:
                    </span>{" "}
                    <span className="text-muted-foreground">
                      {blastRadius.up > 0 && (
                        <span className="inline-flex items-center gap-0.5">
                          <ArrowUp className="h-3 w-3 text-red-500" />
                          {blastRadius.up} up
                        </span>
                      )}
                      {blastRadius.up > 0 && blastRadius.down > 0 && ", "}
                      {blastRadius.down > 0 && (
                        <span className="inline-flex items-center gap-0.5">
                          <ArrowDown className="h-3 w-3 text-emerald-500" />
                          {blastRadius.down} down
                        </span>
                      )}
                      {blastRadius.toP0 > 0 && (
                        <span className="ml-1 text-red-600 font-medium">
                          ({blastRadius.toP0} moved into P0!)
                        </span>
                      )}
                    </span>
                  </div>
                </div>
              )}

              {/* Suggested Priority Changes */}
              {result.suggested_changes.length > 0 && (
                <div className="rounded-lg border p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <ArrowRight className="h-5 w-5 text-primary" />
                      <span className="font-medium">
                        Suggested Priority Changes
                      </span>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {selectedCount} of {result.suggested_changes.length}{" "}
                      selected
                    </span>
                  </div>

                  <div className="space-y-2">
                    {result.suggested_changes.map((change) => (
                      <PriorityChangeRow
                        key={change.ticket_id}
                        change={change}
                        selected={selected[change.ticket_id] ?? false}
                        expanded={expandedReasons[change.ticket_id] ?? false}
                        onToggle={() => toggleChange(change.ticket_id)}
                        onToggleReason={(e) => toggleReason(change.ticket_id, e)}
                      />
                    ))}
                  </div>
                </div>
              )}

              {result.suggested_changes.length === 0 && (
                <div className="text-center py-4 text-muted-foreground">
                  <CheckCircle2 className="h-8 w-8 mx-auto mb-2 text-emerald-500" />
                  No priority changes suggested
                </div>
              )}
            </>
          )}
        </div>

        {/* Actions */}
        {result && (
          <div className="flex items-center justify-between pt-4 border-t">
            <Button
              variant="ghost"
              size="sm"
              onClick={runReflection}
              disabled={loading}
            >
              Re-run Reflection
            </Button>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={applying}
              >
                <X className="mr-1.5 h-3.5 w-3.5" />
                Cancel
              </Button>
              {result.suggested_changes.length > 0 && (
                <Button
                  onClick={handleApply}
                  disabled={applying || selectedCount === 0}
                  className={cn(
                    blastRadius.toP0 > 0 && "bg-red-600 hover:bg-red-700"
                  )}
                >
                  {applying ? (
                    <>
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      Applying...
                    </>
                  ) : (
                    <>
                      <Check className="mr-1.5 h-3.5 w-3.5" />
                      Apply Selected ({selectedCount})
                    </>
                  )}
                </Button>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function PriorityChangeRow({
  change,
  selected,
  expanded,
  onToggle,
  onToggleReason,
}: {
  change: SuggestedPriorityChange;
  selected: boolean;
  expanded: boolean;
  onToggle: () => void;
  onToggleReason: (e: React.MouseEvent) => void;
}) {
  const isUpgrade =
    PRIORITY_BUCKET_VALUES[change.suggested_bucket] >
    PRIORITY_BUCKET_VALUES[change.current_bucket];
  const isToP0 = change.suggested_bucket === "P0" && change.current_bucket !== "P0";

  return (
    <div
      className={cn(
        "rounded-lg border cursor-pointer transition-colors",
        selected
          ? isToP0
            ? "border-red-500/50 bg-red-500/5"
            : "border-primary/50 bg-primary/5"
          : "border-border hover:bg-muted/50"
      )}
    >
      <div className="flex items-center gap-3 p-3" onClick={onToggle}>
        {/* Checkbox */}
        <div
          className={cn(
            "h-5 w-5 rounded border flex items-center justify-center flex-shrink-0 transition-colors",
            selected
              ? isToP0
                ? "bg-red-600 border-red-600 text-white"
                : "bg-primary border-primary text-primary-foreground"
              : "border-muted-foreground/30"
          )}
        >
          {selected && <Check className="h-3.5 w-3.5" />}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium truncate">
              {change.ticket_title}
            </span>
            {isUpgrade && (
              <ArrowUp className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
            )}
            {!isUpgrade && (
              <ArrowDown className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" />
            )}
          </div>
          <div className="flex items-center gap-2 text-xs">
            <PriorityBadge bucket={change.current_bucket} />
            <ArrowRight className="h-3 w-3 text-muted-foreground" />
            <PriorityBadge bucket={change.suggested_bucket} />
          </div>
        </div>

        {/* Expand reason button */}
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          onClick={onToggleReason}
        >
          {expanded ? "Hide" : "Show"} reason
        </Button>
      </div>

      {/* Expanded rationale */}
      {expanded && (
        <div className="px-3 pb-3 pt-0">
          <div className="ml-8 p-2 rounded bg-muted/50 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Rationale: </span>
            {change.reason}
          </div>
        </div>
      )}
    </div>
  );
}
