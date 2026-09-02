/**Polling helpers for backend state that the front end cannot observe directly.

The L2/L3 approval queue and the per-run debug trace live on the
server, so we re-fetch them on a timer rather than relying on the chat
response to push updates. Hooks here own that lifecycle and tear down
their timers on unmount so the front end does not leak intervals when
the user closes a conversation.
*/

import { useCallback, useEffect, useRef, useState } from "react";

import { listPendingDecisions } from "./api";
import type { PendingDecision } from "./types";


export type PendingDecisionsState = {
  pending: PendingDecision[];
  loading: boolean;
  error: string | null;
  lastFetchedAt: number | null;
  refresh: () => Promise<void>;
};


export function usePendingDecisions(intervalMs: number = 5000): PendingDecisionsState {
  const [pending, setPending] = useState<PendingDecision[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<number | null>(null);
  const cancelled = useRef<boolean>(false);

  const refresh = useCallback(async () => {
    try {
      const items = await listPendingDecisions();
      if (cancelled.current) {
        return;
      }
      setPending(items);
      setError(null);
      setLastFetchedAt(Date.now());
    } catch (err) {
      if (cancelled.current) {
        return;
      }
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (!cancelled.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    cancelled.current = false;
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, intervalMs);
    return () => {
      cancelled.current = true;
      window.clearInterval(timer);
    };
  }, [intervalMs, refresh]);

  return { pending, loading, error, lastFetchedAt, refresh };
}
