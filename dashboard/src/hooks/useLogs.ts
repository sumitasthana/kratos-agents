/**
 * dashboard/src/hooks/useLogs.ts
 *
 * Tails the structured log SSE stream from /obs/logs/stream.
 * Keeps a rolling window of the last 100 lines in state.
 * Supports optional filtering by investigation_id and/or level.
 */

import { useCallback, useEffect, useState } from "react";
import type { ObsLogLine } from "../types/observability";

const MAX_LINES = 100;

export interface UseLogsFilter {
  investigationId?: string;
  level?: string;
}

export interface UseLogsResult {
  lines: ObsLogLine[];
  connected: boolean;
  clear: () => void;
}

export function useLogs(filter?: UseLogsFilter): UseLogsResult {
  const [lines, setLines] = useState<ObsLogLine[]>([]);
  const [connected, setConnected] = useState(false);

  const clear = useCallback(() => setLines([]), []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (filter?.investigationId) {
      params.set("investigation_id", filter.investigationId);
    }
    if (filter?.level) {
      params.set("level", filter.level);
    }
    const url = `/obs/logs/stream${params.toString() ? `?${params.toString()}` : ""}`;

    const es = new EventSource(url);

    es.onopen = () => setConnected(true);

    es.onmessage = (e: MessageEvent<string>) => {
      try {
        const line = JSON.parse(e.data) as ObsLogLine;
        setLines((prev) => {
          const next = [...prev, line];
          return next.length > MAX_LINES ? next.slice(next.length - MAX_LINES) : next;
        });
      } catch {
        // Silently ignore malformed SSE frames
      }
    };

    es.onerror = () => setConnected(false);

    return () => es.close();
  }, [filter?.investigationId, filter?.level]); // eslint-disable-line react-hooks/exhaustive-deps

  return { lines, connected, clear };
}
