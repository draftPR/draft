import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { DollarSign, TrendingUp, Zap, Database } from 'lucide-react';
import { EmptyState } from '@/components/EmptyState';
import type { CostBreakdown as CostData } from '../../hooks/useTicketEvidence';

interface CostBreakdownProps {
  cost: CostData;
}

export function CostBreakdown({ cost }: CostBreakdownProps) {
  if (!cost || cost.total_usd === 0) {
    return (
      <Card>
        <CardContent>
          <EmptyState icon={DollarSign} title="No cost data" description="Cost tracking will appear after AI agent runs" />
        </CardContent>
      </Card>
    );
  }

  const inputCostPerToken = cost.total_usd / (cost.input_tokens + cost.output_tokens) || 0;
  const inputCost = cost.input_tokens * inputCostPerToken;
  const outputCost = cost.output_tokens * inputCostPerToken;

  const formatTokens = (tokens: number) => {
    if (tokens >= 1000000) {
      return `${(tokens / 1000000).toFixed(2)}M`;
    } else if (tokens >= 1000) {
      return `${(tokens / 1000).toFixed(2)}K`;
    }
    return tokens.toString();
  };

  return (
    <div className="space-y-4">
      {/* Total cost */}
      <Card className="bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-950 dark:to-indigo-950 border-blue-200 dark:border-blue-800">
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <div className="text-sm text-muted-foreground">Total Cost</div>
              <div className="text-4xl font-bold">${cost.total_usd.toFixed(4)}</div>
            </div>
            <DollarSign className="h-12 w-12 text-blue-500 opacity-50" />
          </div>
        </CardContent>
      </Card>

      {/* Model information */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Model Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">Model</div>
              <Badge variant="secondary" className="font-mono">
                {cost.model}
              </Badge>
            </div>
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">Provider</div>
              <Badge variant="secondary">{cost.provider}</Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Token usage */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Token Usage</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Input tokens */}
          <div className="flex items-center justify-between p-3 rounded-lg bg-secondary">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded bg-green-100 dark:bg-green-950">
                <Database className="h-4 w-4 text-green-600 dark:text-green-400" />
              </div>
              <div>
                <div className="text-sm font-medium">Input Tokens</div>
                <div className="text-xs text-muted-foreground">Prompt and context</div>
              </div>
            </div>
            <div className="text-right">
              <div className="font-mono font-semibold">{formatTokens(cost.input_tokens)}</div>
              <div className="text-xs text-muted-foreground">
                ${inputCost.toFixed(4)}
              </div>
            </div>
          </div>

          {/* Output tokens */}
          <div className="flex items-center justify-between p-3 rounded-lg bg-secondary">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded bg-blue-100 dark:bg-blue-950">
                <Zap className="h-4 w-4 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <div className="text-sm font-medium">Output Tokens</div>
                <div className="text-xs text-muted-foreground">Generated response</div>
              </div>
            </div>
            <div className="text-right">
              <div className="font-mono font-semibold">{formatTokens(cost.output_tokens)}</div>
              <div className="text-xs text-muted-foreground">
                ${outputCost.toFixed(4)}
              </div>
            </div>
          </div>

          {/* Total tokens */}
          <div className="flex items-center justify-between p-3 rounded-lg bg-primary/10 border border-primary/20">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded bg-primary/20">
                <TrendingUp className="h-4 w-4 text-primary" />
              </div>
              <div>
                <div className="text-sm font-semibold">Total Tokens</div>
              </div>
            </div>
            <div className="text-right">
              <div className="font-mono font-bold text-lg">
                {formatTokens(cost.input_tokens + cost.output_tokens)}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Cost insights */}
      <Card className="bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
        <CardContent className="pt-4">
          <p className="text-sm text-muted-foreground mb-2">
            💰 <strong>LLM API costs are tracked per ticket.</strong> Use this data to:
          </p>
          <ul className="text-sm text-muted-foreground space-y-1 ml-6 list-disc">
            <li>Monitor budget usage across goals</li>
            <li>Identify expensive tickets that need optimization</li>
            <li>Compare cost efficiency between different executors</li>
            <li>Set budget limits to prevent runaway spending</li>
          </ul>
        </CardContent>
      </Card>

      {/* Budget warning if cost is high */}
      {cost.total_usd > 1.0 && (
        <Card className="bg-yellow-50 dark:bg-yellow-950 border-yellow-200 dark:border-yellow-800">
          <CardContent className="pt-4">
            <div className="flex items-start gap-2">
              <TrendingUp className="h-5 w-5 text-yellow-600 dark:text-yellow-400 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm font-semibold text-yellow-900 dark:text-yellow-100">
                  High cost ticket
                </p>
                <p className="text-sm text-yellow-800 dark:text-yellow-200">
                  This ticket cost more than $1.00. Consider reviewing the prompt complexity or
                  switching to a more cost-effective model.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
