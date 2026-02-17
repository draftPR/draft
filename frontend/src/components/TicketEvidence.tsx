import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Alert, AlertDescription } from './ui/alert';
import { Loader2, FileText, Zap, Code, CheckCircle, DollarSign, RotateCcw } from 'lucide-react';
import { useTicketEvidence } from '../hooks/useTicketEvidence';
import { PlanView } from './evidence/PlanView';
import { ActionTimeline } from './evidence/ActionTimeline';
import { DiffViewer } from './evidence/DiffViewer';
import { TestResults } from './evidence/TestResults';
import { CostBreakdown } from './evidence/CostBreakdown';
import { RollbackPlan } from './evidence/RollbackPlan';

interface TicketEvidenceProps {
  ticketId: string;
}

export function TicketEvidence({ ticketId }: TicketEvidenceProps) {
  const { evidence, loading, error } = useTicketEvidence(ticketId);

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin mr-2" />
          <span>Loading evidence...</span>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          Failed to load evidence: {error}
        </AlertDescription>
      </Alert>
    );
  }

  if (!evidence) {
    return (
      <Alert>
        <AlertDescription>
          No evidence available for this ticket yet. Execute the ticket to generate evidence.
        </AlertDescription>
      </Alert>
    );
  }

  const testsPassed = evidence.test_results.every(t => t.status === 'passed');
  const totalCost = evidence.cost.total_usd;

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Ticket Evidence</CardTitle>
            <CardDescription>
              Full transparency: plan, actions, changes, tests, cost, and rollback
            </CardDescription>
          </div>
          <div className="flex gap-2">
            {evidence.diff_stat && (
              <Badge variant="outline">
                {evidence.diff_stat.total_files} files changed
              </Badge>
            )}
            {testsPassed ? (
              <Badge variant="default" className="bg-green-500">
                Tests Passed
              </Badge>
            ) : (
              <Badge variant="destructive">Tests Failed</Badge>
            )}
            {totalCost > 0 && (
              <Badge variant="secondary">${totalCost.toFixed(4)}</Badge>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <Tabs defaultValue="plan" className="w-full">
          <TabsList className="grid w-full grid-cols-6">
            <TabsTrigger value="plan" className="flex items-center gap-1">
              <FileText className="h-4 w-4" />
              <span className="hidden sm:inline">Plan</span>
            </TabsTrigger>
            <TabsTrigger value="actions" className="flex items-center gap-1">
              <Zap className="h-4 w-4" />
              <span className="hidden sm:inline">Actions</span>
            </TabsTrigger>
            <TabsTrigger value="diffs" className="flex items-center gap-1">
              <Code className="h-4 w-4" />
              <span className="hidden sm:inline">Changes</span>
            </TabsTrigger>
            <TabsTrigger value="tests" className="flex items-center gap-1">
              <CheckCircle className="h-4 w-4" />
              <span className="hidden sm:inline">Tests</span>
            </TabsTrigger>
            <TabsTrigger value="cost" className="flex items-center gap-1">
              <DollarSign className="h-4 w-4" />
              <span className="hidden sm:inline">Cost</span>
            </TabsTrigger>
            <TabsTrigger value="rollback" className="flex items-center gap-1">
              <RotateCcw className="h-4 w-4" />
              <span className="hidden sm:inline">Rollback</span>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="plan" className="mt-4">
            <PlanView plan={evidence.plan} />
          </TabsContent>

          <TabsContent value="actions" className="mt-4">
            <ActionTimeline actions={evidence.actions} />
          </TabsContent>

          <TabsContent value="diffs" className="mt-4">
            <DiffViewer
              diffs={evidence.diffs}
              diffStat={evidence.diff_stat}
            />
          </TabsContent>

          <TabsContent value="tests" className="mt-4">
            <TestResults results={evidence.test_results} />
          </TabsContent>

          <TabsContent value="cost" className="mt-4">
            <CostBreakdown cost={evidence.cost} />
          </TabsContent>

          <TabsContent value="rollback" className="mt-4">
            <RollbackPlan steps={evidence.rollback_steps} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
