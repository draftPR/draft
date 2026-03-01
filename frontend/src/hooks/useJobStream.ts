import { useState, useEffect, useRef } from 'react';

/**
 * WebSocket URL configuration
 * Uses ws:// for local development, wss:// for production
 */
const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_HOST = import.meta.env.VITE_BACKEND_URL?.replace(/^https?:\/\//, '') || 'localhost:8000';
const WS_URL = `${WS_PROTOCOL}//${WS_HOST}`;

export interface JobStreamMessage {
  type: 'output' | 'status' | 'complete' | 'error' | 'subscribed';
  content?: string;
  status?: string;
  timestamp?: string;
  job_id?: string;
  channel?: string;
}

export interface UseJobStreamResult {
  /** Full output as a single string */
  output: string;
  /** Output lines as an array */
  lines: string[];
  /** Whether the stream is currently active */
  isStreaming: boolean;
  /** Connection status */
  status: 'connecting' | 'connected' | 'disconnected' | 'error';
  /** Latest job status if received */
  jobStatus?: string;
  /** Error message if connection failed */
  error?: string;
}

/**
 * Hook for streaming live output from a running job via WebSocket.
 *
 * Connects to /ws/jobs/{jobId} and receives real-time updates including:
 * - stdout/stderr output
 * - status changes
 * - completion events
 * - errors
 *
 * @param jobId - The job ID to stream
 * @returns Job stream state and output
 *
 * @example
 * ```tsx
 * function JobViewer({ jobId }) {
 *   const { output, isStreaming, status } = useJobStream(jobId);
 *
 *   return (
 *     <div>
 *       <div>Status: {status}</div>
 *       <pre>{output}</pre>
 *       {isStreaming && <span>●</span>}
 *     </div>
 *   );
 * }
 * ```
 */
export function useJobStream(jobId: string | null | undefined): UseJobStreamResult {
  const [output, setOutput] = useState<string[]>([]);
  const [status, setStatus] = useState<'connecting' | 'connected' | 'disconnected' | 'error'>('disconnected');
  const [jobStatus, setJobStatus] = useState<string | undefined>();
  const [error, setError] = useState<string | undefined>();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    // Skip if no job ID
    if (!jobId) {
      setStatus('disconnected');
      return;
    }

    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    const reconnectDelay = 2000; // 2 seconds

    function connect() {
      // Clean up previous connection
      if (wsRef.current) {
        wsRef.current.close();
      }

      setStatus('connecting');
      setError(undefined);

      const ws = new WebSocket(`${WS_URL}/ws/jobs/${jobId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus('connected');
        reconnectAttempts = 0;

        // Send subscribe message
        ws.send('subscribe');

        // Set up ping interval to keep connection alive (every 30 seconds)
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 30000);
      };

      ws.onclose = (event) => {
        setStatus('disconnected');

        // Clear ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }

        // Attempt reconnect if not a normal closure and under max attempts
        if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts) {
          reconnectAttempts++;
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, Math.min(reconnectDelay * 2 ** reconnectAttempts, 30000)); // Exponential backoff
        }
      };

      ws.onerror = () => {
        setStatus('error');
        setError('WebSocket connection error');
      };

      ws.onmessage = (event) => {
        try {
          // Handle pong response
          if (event.data === 'pong') {
            return;
          }

          const message: JobStreamMessage = JSON.parse(event.data);

          switch (message.type) {
            case 'output':
              if (message.content) {
                setOutput((prev) => [...prev, message.content!]);
              }
              break;

            case 'status':
              if (message.status) {
                setJobStatus(message.status);
              }
              break;

            case 'complete':
              setStatus('disconnected');
              if (message.content) {
                setOutput((prev) => [...prev, message.content!]);
              }
              break;

            case 'error':
              setError(message.content || 'Unknown error');
              break;

            case 'subscribed':
              // Subscription confirmed
              break;

            default:
              console.warn('Unknown message type:', message.type);
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };
    }

    connect();

    // Cleanup on unmount or job ID change
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
      }
    };
  }, [jobId]);

  return {
    output: output.join('\n'),
    lines: output,
    isStreaming: status === 'connected',
    status,
    jobStatus,
    error,
  };
}
