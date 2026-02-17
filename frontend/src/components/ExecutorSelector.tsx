import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from './ui/select';
import { Badge } from './ui/badge';
import { Alert, AlertDescription } from './ui/alert';
import { Loader2, CheckCircle, XCircle, Info } from 'lucide-react';
import { useAvailableExecutors } from '../hooks/useAvailableExecutors';

interface ExecutorSelectorProps {
  value: string;
  onValueChange: (value: string) => void;
  className?: string;
}

export function ExecutorSelector({ value, onValueChange, className }: ExecutorSelectorProps) {
  const { executors, loading, error } = useAvailableExecutors();

  if (loading) {
    return (
      <div className={`flex items-center gap-2 ${className || ''}`}>
        <Loader2 className="h-4 w-4 animate-spin" />
        <span className="text-sm text-muted-foreground">Loading executors...</span>
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive" className={className}>
        <AlertDescription>Failed to load executors: {error}</AlertDescription>
      </Alert>
    );
  }

  const availableExecutors = executors.filter(e => e.available);
  const unavailableExecutors = executors.filter(e => !e.available);
  const recommendedExecutors = availableExecutors.filter(e =>
    e.capabilities.includes('yolo_mode') || e.capabilities.includes('streaming_output')
  );

  const getExecutorIcon = (name: string) => {
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
    return iconMap[name] || '⚡';
  };

  const getCapabilityBadges = (capabilities: string[]) => {
    const badgeMap: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' }> = {
      streaming_output: { label: 'Stream', variant: 'secondary' },
      yolo_mode: { label: 'YOLO', variant: 'default' },
      mcp_servers: { label: 'MCP', variant: 'outline' },
      cost_tracking: { label: 'Cost', variant: 'outline' },
      session_resume: { label: 'Resume', variant: 'outline' },
    };

    return capabilities.map(cap => {
      const config = badgeMap[cap] || { label: cap, variant: 'outline' as const };
      return (
        <Badge key={cap} variant={config.variant} className="text-xs">
          {config.label}
        </Badge>
      );
    });
  };

  return (
    <div className={className}>
      <Select value={value} onValueChange={onValueChange}>
        <SelectTrigger>
          <div className="flex items-center gap-2">
            <span className="text-lg">{getExecutorIcon(value)}</span>
            <SelectValue placeholder="Select an executor" />
          </div>
        </SelectTrigger>

        <SelectContent>
          {/* Recommended executors */}
          {recommendedExecutors.length > 0 && (
            <>
              <SelectGroup>
                <SelectLabel className="flex items-center gap-2">
                  <CheckCircle className="h-3 w-3 text-green-500" />
                  Recommended (Full Auto)
                </SelectLabel>
                {recommendedExecutors.map(executor => (
                  <SelectItem key={executor.name} value={executor.name}>
                    <div className="flex items-center gap-3 py-1">
                      <span className="text-lg">{getExecutorIcon(executor.name)}</span>
                      <div className="flex-1">
                        <div className="font-medium">{executor.display_name}</div>
                        <div className="flex gap-1 mt-1">
                          {getCapabilityBadges(executor.capabilities)}
                        </div>
                      </div>
                    </div>
                  </SelectItem>
                ))}
              </SelectGroup>
              <SelectSeparator />
            </>
          )}

          {/* Other available executors */}
          {availableExecutors.length > recommendedExecutors.length && (
            <>
              <SelectGroup>
                <SelectLabel className="flex items-center gap-2">
                  <CheckCircle className="h-3 w-3 text-green-500" />
                  Available
                </SelectLabel>
                {availableExecutors
                  .filter(e => !recommendedExecutors.includes(e))
                  .map(executor => (
                    <SelectItem key={executor.name} value={executor.name}>
                      <div className="flex items-center gap-3 py-1">
                        <span className="text-lg">{getExecutorIcon(executor.name)}</span>
                        <div className="flex-1">
                          <div className="font-medium">{executor.display_name}</div>
                          <div className="flex gap-1 mt-1">
                            {getCapabilityBadges(executor.capabilities)}
                          </div>
                        </div>
                      </div>
                    </SelectItem>
                  ))}
              </SelectGroup>
              <SelectSeparator />
            </>
          )}

          {/* Unavailable executors */}
          {unavailableExecutors.length > 0 && (
            <SelectGroup>
              <SelectLabel className="flex items-center gap-2">
                <XCircle className="h-3 w-3 text-muted-foreground" />
                Not Installed
              </SelectLabel>
              {unavailableExecutors.map(executor => (
                <SelectItem key={executor.name} value={executor.name} disabled>
                  <div className="flex items-center gap-3 py-1 opacity-50">
                    <span className="text-lg">{getExecutorIcon(executor.name)}</span>
                    <div className="flex-1">
                      <div className="font-medium">{executor.display_name}</div>
                      <div className="text-xs text-muted-foreground">Not installed</div>
                    </div>
                  </div>
                </SelectItem>
              ))}
            </SelectGroup>
          )}
        </SelectContent>
      </Select>

      {/* Help text */}
      <div className="mt-2 flex items-start gap-2 text-xs text-muted-foreground">
        <Info className="h-3 w-3 mt-0.5 flex-shrink-0" />
        <p>
          Select which AI coding agent to use for execution. Recommended agents support full
          automation (YOLO mode) and streaming output.
        </p>
      </div>
    </div>
  );
}
