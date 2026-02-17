/**
 * Hook for streaming terminal output from a running job via WebSocket.
 *
 * Similar to useJobStream but returns raw strings suitable for xterm.js,
 * including ANSI escape codes for colors.
 */

import { useEffect, useRef, useCallback, useState } from "react";

const WS_PROTOCOL = window.location.protocol === "https:" ? "wss:" : "ws:";
const WS_HOST =
  import.meta.env.VITE_BACKEND_URL?.replace(/^https?:\/\//, "") ||
  "localhost:8000";
const WS_URL = `${WS_PROTOCOL}//${WS_HOST}`;

export type TerminalStreamStatus =
  | "disconnected"
  | "connecting"
  | "connected"
  | "error";

export interface UseTerminalStreamResult {
  status: TerminalStreamStatus;
  error: string | null;
  /** Subscribe to raw output chunks. Returns unsubscribe fn. */
  subscribe: (callback: (data: string) => void) => () => void;
}

/**
 * Hook that connects to the job WebSocket and provides raw output
 * chunks via a subscription pattern (avoids re-renders on each chunk).
 */
export function useTerminalStream(
  jobId: string | null | undefined,
): UseTerminalStreamResult {
  const [status, setStatus] =
    useState<TerminalStreamStatus>("disconnected");
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const subscribersRef = useRef<Set<(data: string) => void>>(new Set());

  const subscribe = useCallback((callback: (data: string) => void) => {
    subscribersRef.current.add(callback);
    return () => {
      subscribersRef.current.delete(callback);
    };
  }, []);

  const emit = useCallback((data: string) => {
    for (const cb of subscribersRef.current) {
      cb(data);
    }
  }, []);

  useEffect(() => {
    if (!jobId) {
      setStatus("disconnected");
      return;
    }

    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
    let pingInterval: ReturnType<typeof setInterval> | null = null;

    function connect() {
      if (wsRef.current) {
        wsRef.current.close();
      }

      setStatus("connecting");
      setError(null);

      const ws = new WebSocket(`${WS_URL}/ws/jobs/${jobId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("connected");
        reconnectAttempts = 0;
        ws.send("subscribe");

        pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
          }
        }, 30000);
      };

      ws.onclose = (event) => {
        setStatus("disconnected");
        if (pingInterval) {
          clearInterval(pingInterval);
          pingInterval = null;
        }

        if (
          event.code !== 1000 &&
          reconnectAttempts < maxReconnectAttempts
        ) {
          reconnectAttempts++;
          reconnectTimeout = setTimeout(
            () => connect(),
            2000 * reconnectAttempts,
          );
        }
      };

      ws.onerror = () => {
        setStatus("error");
        setError("WebSocket connection error");
      };

      ws.onmessage = (event) => {
        if (event.data === "pong") return;

        try {
          const message = JSON.parse(event.data);

          switch (message.type) {
            case "output":
              if (message.content) {
                emit(message.content);
              }
              break;
            case "complete":
              if (message.content) {
                emit(message.content);
              }
              emit("\r\n\x1b[32m--- Job complete ---\x1b[0m\r\n");
              break;
            case "error":
              emit(
                `\r\n\x1b[31mError: ${message.content || "Unknown error"}\x1b[0m\r\n`,
              );
              break;
            case "status":
              emit(
                `\r\n\x1b[36m[Status: ${message.status}]\x1b[0m\r\n`,
              );
              break;
          }
        } catch {
          // Raw text fallback
          emit(event.data);
        }
      };
    }

    connect();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (pingInterval) clearInterval(pingInterval);
      if (wsRef.current) wsRef.current.close(1000, "Component unmounted");
    };
  }, [jobId, emit]);

  return { status, error, subscribe };
}
