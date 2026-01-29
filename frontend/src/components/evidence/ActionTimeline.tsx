import React from 'react';
import { Card, CardContent } from '../ui/card';
import { Badge } from '../ui/badge';
import { CheckCircle, XCircle, Clock, Terminal, FileEdit, Zap } from 'lucide-react';
import type { Action } from '../../hooks/useTicketEvidence';

interface ActionTimelineProps {
  actions: Action[];
}

export function ActionTimeline({ actions }: ActionTimelineProps) {
  if (!actions || actions.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No actions recorded yet
        </CardContent>
      </Card>
    );
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500" />;
      case 'skipped':
        return <Clock className="h-4 w-4 text-gray-400" />;
      default:
        return <Clock className="h-4 w-4 text-blue-500" />;
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'command':
        return <Terminal className="h-4 w-4" />;
      case 'file_change':
        return <FileEdit className="h-4 w-4" />;
      case 'api_call':
        return <Zap className="h-4 w-4" />;
      default:
        return <Terminal className="h-4 w-4" />;
    }
  };

  const getStatusBadge = (status: string) => {
    const variants = {
      success: 'default',
      failed: 'destructive',
      skipped: 'secondary',
    };
    return variants[status as keyof typeof variants] || 'secondary';
  };

  return (
    <div className="space-y-4">
      <div className="relative">
        {/* Timeline line */}
        <div className="absolute left-4 top-2 bottom-2 w-0.5 bg-border" />

        {/* Actions */}
        <div className="space-y-4">
          {actions.map((action, idx) => (
            <Card key={action.id} className="relative ml-10">
              {/* Timeline dot */}
              <div className="absolute -left-10 top-6 flex h-8 w-8 items-center justify-center rounded-full border-2 border-border bg-background">
                {getStatusIcon(action.status)}
              </div>

              <CardContent className="pt-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2">
                      {getTypeIcon(action.type)}
                      <span className="font-medium">{action.description}</span>
                    </div>

                    {action.details && (
                      <details className="group">
                        <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
                          View details
                        </summary>
                        <pre className="mt-2 rounded bg-secondary p-2 text-xs font-mono overflow-x-auto">
                          {action.details}
                        </pre>
                      </details>
                    )}

                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {new Date(action.timestamp).toLocaleString()}
                    </div>
                  </div>

                  <Badge variant={getStatusBadge(action.status) as any}>
                    {action.status}
                  </Badge>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <Card className="bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
        <CardContent className="pt-4">
          <p className="text-sm text-muted-foreground">
            ⚡ <strong>This timeline shows every action the agent took.</strong> Commands run,
            files modified, and API calls made are all logged for full transparency.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
