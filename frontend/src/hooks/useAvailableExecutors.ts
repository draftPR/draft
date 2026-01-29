import { useState, useEffect } from 'react';

export interface ExecutorMetadata {
  name: string;
  display_name: string;
  version: string;
  capabilities: string[];
  config_schema: any;
  documentation_url?: string;
  author?: string;
  license?: string;
  available: boolean;
}

export function useAvailableExecutors() {
  const [executors, setExecutors] = useState<ExecutorMetadata[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchExecutors() {
      try {
        setLoading(true);
        setError(null);

        const response = await fetch('http://localhost:8000/executors/available');

        if (!response.ok) {
          throw new Error(`Failed to fetch executors: ${response.statusText}`);
        }

        const data = await response.json();
        setExecutors(data);
      } catch (err) {
        console.error('Error fetching available executors:', err);
        setError(err instanceof Error ? err.message : 'Unknown error');
        // Provide fallback data
        setExecutors([
          {
            name: 'claude',
            display_name: 'Claude Code',
            version: '1.0.0',
            capabilities: ['streaming_output', 'yolo_mode', 'mcp_servers', 'cost_tracking'],
            config_schema: {},
            available: false,
          },
          {
            name: 'cursor',
            display_name: 'Cursor',
            version: '1.0.0',
            capabilities: ['streaming_output'],
            config_schema: {},
            available: false,
          },
        ]);
      } finally {
        setLoading(false);
      }
    }

    fetchExecutors();
  }, []);

  return {
    executors,
    loading,
    error,
  };
}
