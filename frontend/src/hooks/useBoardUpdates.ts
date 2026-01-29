import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * WebSocket URL configuration
 */
const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_HOST = import.meta.env.VITE_BACKEND_URL?.replace(/^https?:\/\//, '') || 'localhost:8000';
const WS_URL = `${WS_PROTOCOL}//${WS_HOST}`;

export interface BoardUpdateMessage {
  type: 'ticket_update' | 'job_created' | 'job_completed' | 'subscribed';
  ticket_id?: string;
  job_id?: string;
  data?: Record<string, any>;
  timestamp?: string;
  board_id?: string;
  channel?: string;
}

export type BoardUpdateListener = (message: BoardUpdateMessage) => void;

export interface UseBoardUpdatesResult {
  /** Whether connected to board updates */
  isConnected: boolean;
  /** Connection status */
  status: 'connecting' | 'connected' | 'disconnected' | 'error';
  /** Latest update message */
  lastUpdate: BoardUpdateMessage | null;
  /** All updates received since connection */
  updates: BoardUpdateMessage[];
  /** Error message if connection failed */
  error?: string;
  /** Subscribe to updates with a callback */
  subscribe: (listener: BoardUpdateListener) => () => void;
}

/**
 * Hook for receiving real-time board updates via WebSocket.
 *
 * Connects to /ws/board/{boardId} and receives:
 * - Ticket state transitions
 * - Job creation and completion events
 * - General board activity
 *
 * @param boardId - The board ID to monitor
 * @returns Board updates state and subscription function
 *
 * @example
 * ```tsx
 * function BoardMonitor({ boardId }) {
 *   const { isConnected, lastUpdate, subscribe } = useBoardUpdates(boardId);
 *
 *   useEffect(() => {
 *     const unsubscribe = subscribe((message) => {
 *       if (message.type === 'ticket_update') {
 *         console.log('Ticket updated:', message.ticket_id);
 *         // Refetch ticket data
 *       }
 *     });
 *     return unsubscribe;
 *   }, []);
 *
 *   return <div>Connected: {isConnected ? 'Yes' : 'No'}</div>;
 * }
 * ```
 */
export function useBoardUpdates(boardId: string | null | undefined): UseBoardUpdatesResult {
  const [status, setStatus] = useState<'connecting' | 'connected' | 'disconnected' | 'error'>('disconnected');
  const [lastUpdate, setLastUpdate] = useState<BoardUpdateMessage | null>(null);
  const [updates, setUpdates] = useState<BoardUpdateMessage[]>([]);
  const [error, setError] = useState<string | undefined>();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const listenersRef = useRef<Set<BoardUpdateListener>>(new Set());

  const subscribe = useCallback((listener: BoardUpdateListener) => {
    listenersRef.current.add(listener);

    // Return unsubscribe function
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);

  useEffect(() => {
    // Skip if no board ID
    if (!boardId) {
      setStatus('disconnected');
      return;
    }

    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    const reconnectDelay = 2000;

    function connect() {
      // Clean up previous connection
      if (wsRef.current) {
        wsRef.current.close();
      }

      setStatus('connecting');
      setError(undefined);

      const ws = new WebSocket(`${WS_URL}/ws/board/${boardId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus('connected');
        reconnectAttempts = 0;

        // Send subscribe message
        ws.send('subscribe');

        // Set up ping interval (every 30 seconds)
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

        // Attempt reconnect if not a normal closure
        if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts) {
          reconnectAttempts++;
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectDelay * reconnectAttempts);
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

          const message: BoardUpdateMessage = JSON.parse(event.data);

          // Update state
          setLastUpdate(message);
          if (message.type !== 'subscribed') {
            setUpdates((prev) => [...prev, message]);
          }

          // Notify all listeners
          listenersRef.current.forEach((listener) => {
            try {
              listener(message);
            } catch (err) {
              console.error('Board update listener error:', err);
            }
          });
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };
    }

    connect();

    // Cleanup on unmount or board ID change
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
  }, [boardId]);

  return {
    isConnected: status === 'connected',
    status,
    lastUpdate,
    updates,
    error,
    subscribe,
  };
}
