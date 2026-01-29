import { useState, useEffect } from 'react';

export interface TicketPlan {
  description: string;
  approach: string;
  files_to_modify: string[];
  estimated_complexity: 'low' | 'medium' | 'high';
}

export interface Action {
  id: string;
  type: 'command' | 'file_change' | 'api_call';
  description: string;
  timestamp: string;
  status: 'success' | 'failed' | 'skipped';
  details?: string;
}

export interface FileDiff {
  file_path: string;
  additions: number;
  deletions: number;
  patch: string;
}

export interface TestResult {
  name: string;
  status: 'passed' | 'failed' | 'skipped';
  duration_ms: number;
  output?: string;
  error?: string;
}

export interface CostBreakdown {
  total_usd: number;
  input_tokens: number;
  output_tokens: number;
  model: string;
  provider: string;
}

export interface RollbackStep {
  order: number;
  type: 'git' | 'migration' | 'cache' | 'manual';
  description: string;
  command?: string;
  is_automated: boolean;
  risk_level: 'low' | 'medium' | 'high';
}

export interface TicketEvidence {
  plan: TicketPlan;
  actions: Action[];
  diffs: FileDiff[];
  diff_stat: {
    total_files: number;
    total_additions: number;
    total_deletions: number;
  };
  test_results: TestResult[];
  cost: CostBreakdown;
  rollback_steps: RollbackStep[];
}

export function useTicketEvidence(ticketId: string) {
  const [evidence, setEvidence] = useState<TicketEvidence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchEvidence() {
      if (!ticketId) {
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);

        const response = await fetch(`http://localhost:8000/tickets/${ticketId}/evidence`);

        if (!response.ok) {
          throw new Error(`Failed to fetch evidence: ${response.statusText}`);
        }

        const data = await response.json();
        setEvidence(data);
      } catch (err) {
        console.error('Error fetching ticket evidence:', err);
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    }

    fetchEvidence();
  }, [ticketId]);

  const refetch = async () => {
    setLoading(true);
    try {
      const response = await fetch(`http://localhost:8000/tickets/${ticketId}/evidence`);
      if (!response.ok) {
        throw new Error(`Failed to fetch evidence: ${response.statusText}`);
      }
      const data = await response.json();
      setEvidence(data);
      setError(null);
    } catch (err) {
      console.error('Error refetching evidence:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  return {
    evidence,
    loading,
    error,
    refetch,
  };
}
