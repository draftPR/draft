import { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  CheckCircle2,
  XCircle,
  AlertCircle,
  Shield,
  Undo2,
  GitMerge,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";

interface ChecklistItem {
  id: string;
  category: string;
  label: string;
  description: string;
  status: "passed" | "failed" | "pending" | "info";
  auto_checked: boolean;
  value?: string | number | boolean | null;
}

interface RollbackPlan {
  steps: Array<{
    order: number;
    type: string;
    description: string;
    command: string;
    is_automated: boolean;
    risk: string;
  }>;
  risk_level: string;
  estimated_time: string;
  requires_human: boolean;
}

interface MergeChecklistData {
  id: string;
  goal_id: string;

  // Auto-checks
  all_tests_passed: boolean;
  total_files_changed: number;
  total_lines_changed: number;
  total_cost_usd: number | null;
  budget_exceeded: boolean;

  // Manual checks
  code_reviewed: boolean;
  no_sensitive_data: boolean;
  rollback_plan_understood: boolean;
  documentation_updated: boolean;

  // Rollback
  rollback_plan_json: string | null;
  risk_level: string;

  // Status
  ready_to_merge: boolean;
  merged_at: string | null;
}

interface MergeChecklistProps {
  goalId: string;
  onMerge?: () => void;
}

export function MergeChecklist({ goalId, onMerge }: MergeChecklistProps) {
  const [checklist, setChecklist] = useState<MergeChecklistData | null>(null);
  const [rollbackPlan, setRollbackPlan] = useState<RollbackPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [merging, setMerging] = useState(false);
  const [showRollbackPlan, setShowRollbackPlan] = useState(false);

  useEffect(() => {
    loadChecklist();
  }, [goalId]);

  const loadChecklist = async () => {
    setLoading(true);
    try {
      // TODO: Replace with actual API call
      const response = await fetch(`/api/goals/${goalId}/merge-checklist`);
      if (!response.ok) throw new Error("Failed to load checklist");

      const data = await response.json();
      setChecklist(data);

      if (data.rollback_plan_json) {
        setRollbackPlan(JSON.parse(data.rollback_plan_json));
      }
    } catch (error) {
      toast.error("Failed to load merge checklist");
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const updateManualCheck = async (field: string, value: boolean) => {
    if (!checklist) return;

    try {
      const response = await fetch(`/api/merge-checklists/${checklist.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: value }),
      });

      if (!response.ok) throw new Error("Failed to update checklist");

      const updated = await response.json();
      setChecklist(updated);
      toast.success("Checklist updated");
    } catch (error) {
      toast.error("Failed to update checklist");
      console.error(error);
    }
  };

  const handleMerge = async () => {
    if (!checklist?.ready_to_merge) {
      toast.error("Not all checks are complete");
      return;
    }

    setMerging(true);
    try {
      // TODO: Implement actual merge logic
      const response = await fetch(`/api/goals/${goalId}/merge`, {
        method: "POST",
      });

      if (!response.ok) throw new Error("Merge failed");

      toast.success("Successfully merged all changes!");
      onMerge?.();
    } catch (error) {
      toast.error("Merge failed");
      console.error(error);
    } finally {
      setMerging(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (!checklist) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No checklist available yet. Complete some tickets first.
        </CardContent>
      </Card>
    );
  }

  const autoChecks: ChecklistItem[] = [
    {
      id: "tests",
      category: "verification",
      label: "All Tests Passed",
      description: "All verification commands completed successfully",
      status: checklist.all_tests_passed ? "passed" : "failed",
      auto_checked: true,
    },
    {
      id: "changes",
      category: "impact",
      label: "Changes Summary",
      description: `${checklist.total_files_changed} files, ${checklist.total_lines_changed} lines changed`,
      status: "info",
      auto_checked: true,
      value: `${checklist.total_files_changed} files`,
    },
    {
      id: "cost",
      category: "budget",
      label: "Cost Tracking",
      description: checklist.total_cost_usd
        ? `Total cost: $${checklist.total_cost_usd.toFixed(2)}`
        : "No cost data available",
      status: checklist.budget_exceeded ? "failed" : "info",
      auto_checked: true,
      value: checklist.total_cost_usd ? `$${checklist.total_cost_usd.toFixed(2)}` : "N/A",
    },
  ];

  const manualChecks = [
    {
      id: "code_reviewed",
      label: "Code Reviewed",
      description: "All changes have been reviewed by a human",
      checked: checklist.code_reviewed,
    },
    {
      id: "no_sensitive_data",
      label: "No Sensitive Data",
      description: "No API keys, credentials, or secrets exposed",
      checked: checklist.no_sensitive_data,
    },
    {
      id: "rollback_plan_understood",
      label: "Rollback Plan Understood",
      description: "Team understands how to rollback if needed",
      checked: checklist.rollback_plan_understood,
    },
    {
      id: "documentation_updated",
      label: "Documentation Updated",
      description: "README, docs, or comments updated as needed",
      checked: checklist.documentation_updated,
    },
  ];

  const canMerge = checklist.ready_to_merge;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <GitMerge className="h-5 w-5" />
                Merge Readiness Checklist
              </CardTitle>
              <CardDescription>
                Complete all checks before merging changes
              </CardDescription>
            </div>
            <Badge variant={canMerge ? "default" : "secondary"} className="text-xs">
              {canMerge ? "✓ Ready to Merge" : "Pending"}
            </Badge>
          </div>
        </CardHeader>

        <CardContent className="space-y-6">
          {/* Auto Checks */}
          <div className="space-y-3">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              Automated Checks
            </h3>
            {autoChecks.map((check) => (
              <div
                key={check.id}
                className="flex items-start gap-3 p-3 rounded-lg border bg-card"
              >
                <div className="flex-shrink-0 mt-0.5">
                  {check.status === "passed" && (
                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                  )}
                  {check.status === "failed" && (
                    <XCircle className="h-5 w-5 text-red-500" />
                  )}
                  {check.status === "info" && (
                    <AlertCircle className="h-5 w-5 text-blue-500" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium">{check.label}</p>
                    {check.value && (
                      <Badge variant="outline" className="text-xs">
                        {check.value}
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {check.description}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* Manual Checks */}
          <div className="space-y-3">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <Shield className="h-4 w-4" />
              Manual Verification
            </h3>
            {manualChecks.map((check) => (
              <div
                key={check.id}
                className="flex items-start gap-3 p-3 rounded-lg border bg-card"
              >
                <Checkbox
                  id={check.id}
                  checked={check.checked}
                  onCheckedChange={(checked) =>
                    updateManualCheck(check.id, checked as boolean)
                  }
                  className="mt-0.5"
                />
                <div className="flex-1 min-w-0">
                  <Label
                    htmlFor={check.id}
                    className="text-sm font-medium cursor-pointer"
                  >
                    {check.label}
                  </Label>
                  <p className="text-xs text-muted-foreground mt-1">
                    {check.description}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* Rollback Plan */}
          {rollbackPlan && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <Undo2 className="h-4 w-4" />
                  Rollback Plan
                </h3>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowRollbackPlan(!showRollbackPlan)}
                >
                  {showRollbackPlan ? "Hide" : "Show"}
                </Button>
              </div>

              {showRollbackPlan && (
                <div className="p-4 rounded-lg border bg-muted/50 space-y-3">
                  <div className="flex items-center gap-4 text-xs">
                    <Badge
                      variant={
                        rollbackPlan.risk_level === "high"
                          ? "destructive"
                          : rollbackPlan.risk_level === "medium"
                            ? "secondary"
                            : "outline"
                      }
                    >
                      {rollbackPlan.risk_level.toUpperCase()} RISK
                    </Badge>
                    <span className="text-muted-foreground">
                      Est. time: {rollbackPlan.estimated_time}
                    </span>
                  </div>

                  <div className="space-y-2">
                    {rollbackPlan.steps.map((step) => (
                      <div key={step.order} className="flex gap-3 text-sm">
                        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-medium">
                          {step.order}
                        </div>
                        <div className="flex-1">
                          <p className="font-medium">{step.description}</p>
                          <code className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded mt-1 block">
                            {step.command}
                          </code>
                          <div className="flex items-center gap-2 mt-1">
                            <Badge variant="outline" className="text-xs">
                              {step.type}
                            </Badge>
                            {step.is_automated ? (
                              <span className="text-xs text-green-600">
                                Automated
                              </span>
                            ) : (
                              <span className="text-xs text-amber-600">
                                Manual Required
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>

        <CardFooter className="flex justify-between">
          <div className="text-sm text-muted-foreground">
            {canMerge ? (
              <span className="text-green-600 flex items-center gap-1">
                <CheckCircle2 className="h-4 w-4" />
                All checks passed
              </span>
            ) : (
              <span className="flex items-center gap-1">
                <AlertCircle className="h-4 w-4" />
                {manualChecks.filter((c) => !c.checked).length} checks remaining
              </span>
            )}
          </div>
          <Button
            onClick={handleMerge}
            disabled={!canMerge || merging}
            size="lg"
          >
            {merging ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Merging...
              </>
            ) : (
              <>
                <GitMerge className="h-4 w-4 mr-2" />
                Merge All Changes
              </>
            )}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
