import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import type { TicketPlan } from '../../hooks/useTicketEvidence';

interface PlanViewProps {
  plan: TicketPlan;
}

export function PlanView({ plan }: PlanViewProps) {
  const complexityColors = {
    low: 'bg-green-500',
    medium: 'bg-yellow-500',
    high: 'bg-red-500',
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Agent's Plan</CardTitle>
            <Badge className={complexityColors[plan.estimated_complexity]}>
              {plan.estimated_complexity} complexity
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <h4 className="font-semibold mb-2">Description</h4>
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">
              {plan.description}
            </p>
          </div>

          <div>
            <h4 className="font-semibold mb-2">Approach</h4>
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">
              {plan.approach}
            </p>
          </div>

          {plan.files_to_modify && plan.files_to_modify.length > 0 && (
            <div>
              <h4 className="font-semibold mb-2">
                Files to Modify ({plan.files_to_modify.length})
              </h4>
              <ul className="space-y-1">
                {plan.files_to_modify.map((file, idx) => (
                  <li
                    key={idx}
                    className="text-sm font-mono text-muted-foreground bg-secondary px-2 py-1 rounded"
                  >
                    {file}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
        <CardContent className="pt-4">
          <p className="text-sm text-muted-foreground">
            💡 <strong>This is what the agent planned to do before execution.</strong> Compare
            this with the actual changes in the "Changes" tab to verify the agent stayed on track.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
