import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Alert, AlertDescription } from '../ui/alert';
import {
  AlertTriangle,
  CheckCircle,
  XCircle,
  Terminal,
  Database,
  Trash2,
  ArrowLeft,
  Copy,
  Check,
} from 'lucide-react';
import type { RollbackStep } from '../../hooks/useTicketEvidence';

interface RollbackPlanProps {
  steps: RollbackStep[];
}

export function RollbackPlan({ steps }: RollbackPlanProps) {
  const [copiedStep, setCopiedStep] = useState<number | null>(null);

  const copyCommand = (command: string, stepOrder: number) => {
    navigator.clipboard.writeText(command);
    setCopiedStep(stepOrder);
    setTimeout(() => setCopiedStep(null), 2000);
  };

  if (!steps || steps.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No rollback plan available
        </CardContent>
      </Card>
    );
  }

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'low':
        return 'bg-green-500';
      case 'medium':
        return 'bg-yellow-500';
      case 'high':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'git':
        return <ArrowLeft className="h-4 w-4" />;
      case 'migration':
        return <Database className="h-4 w-4" />;
      case 'cache':
        return <Trash2 className="h-4 w-4" />;
      case 'manual':
        return <Terminal className="h-4 w-4" />;
      default:
        return <Terminal className="h-4 w-4" />;
    }
  };

  const automatedSteps = steps.filter(s => s.is_automated);
  const manualSteps = steps.filter(s => !s.is_automated);
  const highRiskSteps = steps.filter(s => s.risk_level === 'high');

  return (
    <div className="space-y-4">
      {/* Overview */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Rollback Overview</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-1">
              <div className="text-2xl font-bold">{steps.length}</div>
              <div className="text-xs text-muted-foreground">Total Steps</div>
            </div>
            <div className="space-y-1">
              <div className="text-2xl font-bold text-green-500">{automatedSteps.length}</div>
              <div className="text-xs text-muted-foreground">Automated</div>
            </div>
            <div className="space-y-1">
              <div className="text-2xl font-bold text-yellow-500">{manualSteps.length}</div>
              <div className="text-xs text-muted-foreground">Manual</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* High risk warning */}
      {highRiskSteps.length > 0 && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            <strong>High Risk:</strong> This rollback plan contains {highRiskSteps.length} high-risk
            step{highRiskSteps.length > 1 ? 's' : ''}. Review carefully before executing.
          </AlertDescription>
        </Alert>
      )}

      {/* Rollback steps */}
      <div className="space-y-3">
        {steps
          .sort((a, b) => a.order - b.order)
          .map((step, idx) => (
            <Card
              key={idx}
              className={
                step.risk_level === 'high'
                  ? 'border-red-200 dark:border-red-800'
                  : step.risk_level === 'medium'
                  ? 'border-yellow-200 dark:border-yellow-800'
                  : ''
              }
            >
              <CardContent className="pt-4">
                <div className="space-y-3">
                  {/* Step header */}
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3 flex-1">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-secondary border-2 border-border font-semibold text-sm">
                        {step.order}
                      </div>
                      <div className="flex-1 space-y-2">
                        <div className="flex items-center gap-2">
                          {getTypeIcon(step.type)}
                          <span className="font-medium">{step.description}</span>
                        </div>

                        {/* Command */}
                        {step.command && (
                          <div className="relative">
                            <pre className="rounded bg-secondary border p-3 text-xs font-mono overflow-x-auto pr-12">
                              {step.command}
                            </pre>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="absolute top-2 right-2 h-6 w-6"
                              onClick={() => copyCommand(step.command!, step.order)}
                            >
                              {copiedStep === step.order ? (
                                <Check className="h-3 w-3 text-green-500" />
                              ) : (
                                <Copy className="h-3 w-3" />
                              )}
                            </Button>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Badges */}
                    <div className="flex flex-col gap-2 items-end">
                      <Badge className={getRiskColor(step.risk_level)}>
                        {step.risk_level} risk
                      </Badge>
                      {step.is_automated ? (
                        <Badge variant="secondary" className="text-green-600 dark:text-green-400">
                          <CheckCircle className="h-3 w-3 mr-1" />
                          Automated
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="text-yellow-600 dark:text-yellow-400">
                          <XCircle className="h-3 w-3 mr-1" />
                          Manual
                        </Badge>
                      )}
                      <Badge variant="outline">{step.type}</Badge>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
      </div>

      {/* Instructions */}
      <Card className="bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
        <CardContent className="pt-4">
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              ↩️ <strong>How to use this rollback plan:</strong>
            </p>
            <ol className="text-sm text-muted-foreground space-y-1 ml-6 list-decimal">
              <li>Execute steps in the order shown (Step 1 → Step 2 → ...)</li>
              <li>
                <strong>Automated steps</strong> can be run via API or script
              </li>
              <li>
                <strong>Manual steps</strong> require human intervention
              </li>
              <li>Test after each step to verify the rollback is working</li>
              <li>High-risk steps should be reviewed by a senior engineer</li>
            </ol>
          </div>
        </CardContent>
      </Card>

      {/* API integration hint */}
      <Card className="bg-purple-50 dark:bg-purple-950 border-purple-200 dark:border-purple-800">
        <CardContent className="pt-4">
          <p className="text-sm text-muted-foreground">
            🔧 <strong>Future:</strong> Automated rollback execution via API will allow you to
            rollback changes with a single click. For now, copy and run commands manually.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
