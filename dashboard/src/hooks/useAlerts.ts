/**
 * dashboard/src/hooks/useAlerts.ts
 *
 * Polls /obs/alerts/active and /obs/events on a configurable interval.
 */

import { useEffect, useRef, useState } from "react";
import type { ObsAlert, ObsEvent } from "../types/observability";

export interface UseAlertsResult {
  alerts: ObsAlert[];
  events: ObsEvent[];
  lastChecked: number | null;
}

export function useAlerts(pollIntervalMs = 5000): UseAlertsResult {
  const [alerts, setAlerts] = useState<ObsAlert[]>([]);
  const [events, setEvents] = useState<ObsEvent[]>([]);
  const [lastChecked, setLastChecked] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchBoth(): Promise<void> {
      try {
        const [alertRes, eventRes] = await Promise.all([
          fetch("/obs/alerts/active"),
          fetch("/obs/events?limit=10"),
        ]);

        if (alertRes.ok) {
          const data = await alertRes.json() as { alerts: ObsAlert[] };
          if (!cancelled) setAlerts(data.alerts ?? []);
        }

        if (eventRes.ok) {
          const data = await eventRes.json() as { items: ObsEvent[]; total: number };
          if (!cancelled) setEvents(data.items ?? []);
        }

        if (!cancelled) setLastChecked(Date.now());
      } catch {
        // Silent failure — keep stale data
      }
    }

    void fetchBoth();
    timerRef.current = setInterval(() => { void fetchBoth(); }, pollIntervalMs);

    return () => {
      cancelled = true;
      if (timerRef.current !== null) clearInterval(timerRef.current);
    };
  }, [pollIntervalMs]);

  return { alerts, events, lastChecked };
}
