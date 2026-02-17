import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  TrendingUp,
  DollarSign,
  Clock,
  CheckCircle2,
  AlertTriangle,
  BarChart3,
  Zap,
  RefreshCw,
  Target,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { fetchDashboard, type DashboardResponse, type BudgetStatus, type SprintMetrics, type AgentMetrics } from "@/services/api";

// Default data for initial render
const defaultDashboardData: DashboardResponse = {
  budget: {
    daily_budget: 10,
    daily_spent: 0,
    daily_remaining: 10,
    weekly_budget: 50,
    weekly_spent: 0,
    weekly_remaining: 50,
    monthly_budget: 150,
    monthly_spent: 0,
    monthly_remaining: 150,
    is_over_budget: false,
    warning_threshold_reached: false,
  },
  sprint: {
    total_tickets: 0,
    completed_tickets: 0,
    in_progress_tickets: 0,
    blocked_tickets: 0,
    completion_rate: 0,
    avg_cycle_time_hours: 0,
    velocity: 0,
  },
  agent: {
    total_sessions: 0,
    successful_sessions: 0,
    success_rate: 0,
    avg_turns_per_session: 0,
    most_used_agent: "claude",
    total_cost_usd: 0,
  },
  cost_trend: [],
};

function BudgetCard({ budget }: { budget: BudgetStatus }) {
  const dailyPercent = (budget.daily_spent / (budget.daily_budget ?? 1)) * 100;
  const weeklyPercent = (budget.weekly_spent / (budget.weekly_budget ?? 1)) * 100;
  
  return (
    <Card className="min-w-0">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <DollarSign className="h-4 w-4" />
          Budget Status
          {budget.warning_threshold_reached && (
            <Badge variant="destructive" className="ml-auto">
              <AlertTriangle className="h-3 w-3 mr-1" />
              Near Limit
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Daily */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Today</span>
            <span className="font-medium">
              ${budget.daily_spent.toFixed(2)} / ${budget.daily_budget}
            </span>
          </div>
          <div className="h-2 bg-muted rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full transition-all",
                dailyPercent > 80 ? "bg-red-500" : dailyPercent > 60 ? "bg-amber-500" : "bg-emerald-500"
              )}
              style={{ width: `${Math.min(100, dailyPercent)}%` }}
            />
          </div>
        </div>
        
        {/* Weekly */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">This Week</span>
            <span className="font-medium">
              ${budget.weekly_spent.toFixed(2)} / ${budget.weekly_budget}
            </span>
          </div>
          <div className="h-2 bg-muted rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full transition-all",
                weeklyPercent > 80 ? "bg-red-500" : weeklyPercent > 60 ? "bg-amber-500" : "bg-emerald-500"
              )}
              style={{ width: `${Math.min(100, weeklyPercent)}%` }}
            />
          </div>
        </div>
        
        {/* Monthly summary */}
        <div className="pt-2 border-t">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Monthly Remaining</span>
            <span className="font-semibold text-emerald-600">
              ${budget.monthly_remaining.toFixed(2)}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function SprintProgressCard({ sprint }: { sprint: SprintMetrics }) {
  return (
    <Card className="min-w-0">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Target className="h-4 w-4" />
          Sprint Progress
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Completion ring */}
          <div className="flex items-center gap-4">
            <div className="relative w-16 h-16">
              <svg className="w-full h-full -rotate-90">
                <circle
                  cx="32"
                  cy="32"
                  r="28"
                  stroke="currentColor"
                  strokeWidth="6"
                  fill="none"
                  className="text-muted"
                />
                <circle
                  cx="32"
                  cy="32"
                  r="28"
                  stroke="currentColor"
                  strokeWidth="6"
                  fill="none"
                  strokeDasharray={`${sprint.completion_rate * 1.76} 176`}
                  className="text-emerald-500"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-sm font-bold">{sprint.completion_rate.toFixed(0)}%</span>
              </div>
            </div>
            <div className="space-y-1">
              <div className="text-2xl font-bold">
                {sprint.completed_tickets}/{sprint.total_tickets}
              </div>
              <div className="text-xs text-muted-foreground">tickets completed</div>
            </div>
          </div>
          
          {/* Status breakdown */}
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="p-2 bg-blue-500/10 rounded-lg">
              <div className="text-lg font-semibold text-blue-600">
                {sprint.in_progress_tickets}
              </div>
              <div className="text-xs text-muted-foreground">In Progress</div>
            </div>
            <div className="p-2 bg-amber-500/10 rounded-lg">
              <div className="text-lg font-semibold text-amber-600">
                {sprint.blocked_tickets}
              </div>
              <div className="text-xs text-muted-foreground">Blocked</div>
            </div>
            <div className="p-2 bg-muted rounded-lg">
              <div className="text-lg font-semibold">
                {sprint.total_tickets - sprint.completed_tickets - sprint.in_progress_tickets - sprint.blocked_tickets}
              </div>
              <div className="text-xs text-muted-foreground">Remaining</div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function VelocityCard({ sprint, agent }: { sprint: SprintMetrics; agent: AgentMetrics }) {
  return (
    <Card className="min-w-0">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Zap className="h-4 w-4" />
          Velocity & Efficiency
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-1">
              <span className="text-2xl font-bold">{sprint.velocity.toFixed(1)}</span>
              <TrendingUp className="h-4 w-4 text-emerald-500" />
            </div>
            <div className="text-xs text-muted-foreground">tickets/day</div>
          </div>
          
          <div className="space-y-1">
            <div className="flex items-center gap-1">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <span className="text-2xl font-bold">{sprint.avg_cycle_time_hours.toFixed(1)}h</span>
            </div>
            <div className="text-xs text-muted-foreground">avg cycle time</div>
          </div>
          
          <div className="space-y-1">
            <div className="flex items-center gap-1">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              <span className="text-2xl font-bold">{agent.success_rate.toFixed(0)}%</span>
            </div>
            <div className="text-xs text-muted-foreground">agent success</div>
          </div>
          
          <div className="space-y-1">
            <div className="text-2xl font-bold">{agent.avg_turns_per_session.toFixed(1)}</div>
            <div className="text-xs text-muted-foreground">turns/session</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function CostTrendChart({ trend }: { trend: { date: string; cost: number }[] }) {
  const maxCost = Math.max(...trend.map(t => t.cost), 1);
  
  return (
    <Card className="min-w-0">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <BarChart3 className="h-4 w-4" />
          Cost Trend (7 days)
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-end gap-1 h-24">
          {trend.map((day, i) => (
            <div key={i} className="flex-1 flex flex-col items-center gap-1">
              <div
                className={cn(
                  "w-full rounded-t transition-all",
                  day.cost > 0 ? "bg-blue-500" : "bg-muted"
                )}
                style={{ height: `${(day.cost / maxCost) * 100}%`, minHeight: day.cost > 0 ? 4 : 0 }}
              />
              <span className="text-[10px] text-muted-foreground">{day.date}</span>
            </div>
          ))}
        </div>
        <div className="mt-2 text-right text-xs text-muted-foreground">
          Total: ${trend.reduce((sum, d) => sum + d.cost, 0).toFixed(2)}
        </div>
      </CardContent>
    </Card>
  );
}

interface SprintDashboardProps {
  goalId?: string;
}

export function SprintDashboard({ goalId }: SprintDashboardProps) {
  const [data, setData] = useState<DashboardResponse>(defaultDashboardData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchDashboard(goalId);
      setData(response);
    } catch (err) {
      console.error("Failed to fetch dashboard:", err);
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    refresh();
  }, [goalId]);
  
  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Sprint Dashboard</h2>
        <Button variant="ghost" size="sm" onClick={refresh} disabled={loading}>
          <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
        </Button>
      </div>
      
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}
      
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
        <BudgetCard budget={data.budget} />
        <SprintProgressCard sprint={data.sprint} />
        <VelocityCard sprint={data.sprint} agent={data.agent} />
        <CostTrendChart trend={data.cost_trend} />
      </div>
    </div>
  );
}
