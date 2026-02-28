/**
 * Tracks backend connectivity.
 *
 * Pings the backend health endpoint on an interval.  When the backend is
 * unreachable the hook exposes `isOffline = true` so the UI can show a
 * banner and pause heavy polling.
 *
 * `wake()` asks the Vite dev server to spawn the backend process if it
 * isn't already running.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { config } from "@/config";

export interface BackendStatus {
  /** true when the backend hasn't responded to the last N pings */
  isOffline: boolean;
  /** timestamp of the last successful response (epoch ms), or null */
  lastSeen: number | null;
  /** manually trigger a reconnect attempt right now */
  retry: () => void;
  /** ask the Vite dev server to start the backend process */
  wake: () => Promise<void>;
  /** true while a wake request is in-flight */
  waking: boolean;
}

const PING_INTERVAL_MS = 10_000; // check every 10 s while online
const OFFLINE_PING_INTERVAL_MS = 30_000; // back off when offline
const FAIL_THRESHOLD = 2; // consecutive failures before we declare offline
const AUTO_WAKE_COOLDOWN_MS = 60_000; // don't auto-wake more than once per minute

export function useBackendStatus(): BackendStatus {
  const [isOffline, setIsOffline] = useState(false);
  const [lastSeen, setLastSeen] = useState<number | null>(null);
  const [waking, setWaking] = useState(false);
  const failCount = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();
  const lastAutoWake = useRef(0);

  const ping = useCallback(async () => {
    try {
      // Use a lightweight endpoint – just needs a 2xx.
      const res = await fetch(`${config.backendBaseUrl}/health`, {
        method: "GET",
        signal: AbortSignal.timeout(5_000),
      });
      if (res.ok) {
        failCount.current = 0;
        setIsOffline(false);
        setLastSeen(Date.now());
        return;
      }
    } catch {
      // network error / timeout
    }
    failCount.current += 1;
    if (failCount.current >= FAIL_THRESHOLD) {
      setIsOffline(true);

      // Auto-wake: ask the Vite plugin to restart the backend (with cooldown)
      const now = Date.now();
      if (now - lastAutoWake.current > AUTO_WAKE_COOLDOWN_MS) {
        lastAutoWake.current = now;
        fetch("/__api/wake-backend", { signal: AbortSignal.timeout(20_000) })
          .then((r) => {
            if (r.ok) {
              failCount.current = 0;
              setIsOffline(false);
              setLastSeen(Date.now());
            }
          })
          .catch(() => {});
      }
    }
  }, []);

  const retry = useCallback(() => {
    failCount.current = 0;
    ping();
  }, [ping]);

  const wake = useCallback(async () => {
    setWaking(true);
    try {
      const res = await fetch("/__api/wake-backend", {
        signal: AbortSignal.timeout(20_000),
      });
      if (res.ok) {
        // Backend is up — update state immediately
        failCount.current = 0;
        setIsOffline(false);
        setLastSeen(Date.now());
      }
    } catch {
      // Vite endpoint unreachable or timed out — fall through
    } finally {
      setWaking(false);
    }
  }, []);

  useEffect(() => {
    // initial ping
    ping();

    const schedule = () => {
      timerRef.current = setTimeout(() => {
        ping().finally(schedule);
      }, failCount.current >= FAIL_THRESHOLD ? OFFLINE_PING_INTERVAL_MS : PING_INTERVAL_MS);
    };
    schedule();

    return () => clearTimeout(timerRef.current);
  }, [ping]);

  return { isOffline, lastSeen, retry, wake, waking };
}
