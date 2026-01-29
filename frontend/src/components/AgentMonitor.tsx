import React, { useState } from 'react';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Loader2, Activity, CheckCircle, XCircle, Clock, Maximize2, Minimize2 } from 'lucide-react';
import { useJobStream } from '../hooks/useJobStream';

interface Job {
  id: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled';
  ticket: {
    id: string;
    title: string;
  };
  executor?: string;
  startedAt?: string;
}

interface AgentMonitorProps {
  /** List of active jobs to monitor */
  jobs: Job[];
  /** Callback when user clicks to view full logs */
  onViewLogs?: (jobId: string) => void;
  /** Callback when user clicks to stop a job */
  onStopJob?: (jobId: string) => void;
  /** Compact mode for sidebar */
  compact?: boolean;
}

/**
 * Real-time agent monitor component.
 *
 * Displays active job executions with live output streaming via WebSocket.
 * Shows job status, executor type, elapsed time, and output preview.
 *
 * @example
 * ```tsx
 * const activeJobs = [
 *   { id: 'job-1', status: 'running', ticket: { id: 't1', title: 'Fix bug' } }
 * ];
 *
 * <AgentMonitor
 *   jobs={activeJobs}
 *   onViewLogs={(id) => openLogsModal(id)}
 *   onStopJob={(id) => cancelJob(id)}
 * />
 * ```
 */
export function AgentMonitor({ jobs, onViewLogs, onStopJob, compact = false }: AgentMonitorProps) {
  if (jobs.length === 0) {
    return (
      <div className="text-muted-foreground text-sm p-4 text-center">
        {compact ? 'No active jobs' : 'No active executions'}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {jobs.map((job) => (
        <AgentJobCard
          key={job.id}
          job={job}
          onViewLogs={onViewLogs}
          onStopJob={onStopJob}
          compact={compact}
        />
      ))}
    </div>
  );
}

interface AgentJobCardProps {
  job: Job;
  onViewLogs?: (jobId: string) => void;
  onStopJob?: (jobId: string) => void;
  compact?: boolean;
}

function AgentJobCard({ job, onViewLogs, onStopJob, compact }: AgentJobCardProps) {
  const { output, isStreaming, status: wsStatus } = useJobStream(job.id);
  const [expanded, setExpanded] = useState(!compact);

  // Get executor icon
  const getExecutorIcon = (executor?: string) => {
    const iconMap: Record<string, string> = {
      claude: '🤖',
      aider: '🎯',
      cursor: '✨',
      'amazon-q': '📦',
      gemini: '💎',
      copilot: '🚁',
      goose: '🪿',
      cline: '🧑‍💻',
    };
    return executor ? iconMap[executor] || '⚡' : '⚡';
  };

  // Get status badge config
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'queued':
        return { icon: Clock, label: 'Queued', variant: 'secondary' as const, pulse: false };
      case 'running':
        return { icon: Activity, label: 'Running', variant: 'default' as const, pulse: true };
      case 'succeeded':
        return { icon: CheckCircle, label: 'Succeeded', variant: 'outline' as const, pulse: false };
      case 'failed':
        return { icon: XCircle, label: 'Failed', variant: 'destructive' as const, pulse: false };
      case 'canceled':
        return { icon: XCircle, label: 'Canceled', variant: 'secondary' as const, pulse: false };
      default:
        return { icon: Activity, label: status, variant: 'secondary' as const, pulse: false };
    }
  };

  // Format elapsed time
  const formatElapsed = (startedAt?: string) => {
    if (!startedAt) return '—';
    const start = new Date(startedAt);
    const now = new Date();
    const seconds = Math.floor((now.getTime() - start.getTime()) / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${minutes % 60}m`;
  };

  const statusBadge = getStatusBadge(job.status);
  const StatusIcon = statusBadge.icon;

  return (
    <Card className="p-3 hover:bg-accent/50 transition-colors">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="text-lg" title={job.executor}>
            {getExecutorIcon(job.executor)}
          </span>
          <span className="font-medium text-sm truncate">{job.ticket.title}</span>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={statusBadge.variant} className="text-xs">
            <StatusIcon className={`h-3 w-3 mr-1 ${statusBadge.pulse ? 'animate-pulse' : ''}`} />
            {statusBadge.label}
          </Badge>
          {!compact && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setExpanded(!expanded)}
              className="h-6 w-6 p-0"
            >
              {expanded ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
            </Button>
          )}
        </div>
      </div>

      {/* Output preview (expandable) */}
      {expanded && (
        <>
          <div className="bg-secondary rounded p-2 font-mono text-xs max-h-24 overflow-hidden mb-2">
            {output ? (
              <pre className="whitespace-pre-wrap">
                {output.slice(-500)}
                {isStreaming && <span className="animate-pulse">▋</span>}
              </pre>
            ) : (
              <div className="text-muted-foreground italic">
                {wsStatus === 'connecting' ? 'Connecting...' : 'No output yet'}
              </div>
            )}
          </div>

          {/* Footer with actions */}
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground text-xs">
              {job.status === 'running' && (
                <>
                  <Activity className="h-3 w-3 inline mr-1" />
                  {formatElapsed(job.startedAt)}
                </>
              )}
              {isStreaming && wsStatus === 'connected' && (
                <span className="ml-2">
                  <Loader2 className="h-3 w-3 inline animate-spin mr-1" />
                  Streaming
                </span>
              )}
            </span>
            <div className="flex gap-1">
              {onViewLogs && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => onViewLogs(job.id)}
                  className="h-6 text-xs"
                >
                  View Logs
                </Button>
              )}
              {onStopJob && job.status === 'running' && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => onStopJob(job.id)}
                  className="h-6 text-xs text-destructive hover:text-destructive"
                >
                  Stop
                </Button>
              )}
            </div>
          </div>
        </>
      )}

      {/* Compact view (just status line) */}
      {!expanded && compact && (
        <div className="text-xs text-muted-foreground">
          {job.status === 'running' && formatElapsed(job.startedAt)}
        </div>
      )}
    </Card>
  );
}
