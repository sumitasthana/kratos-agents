/**
 * EnvironmentSelector.tsx
 *
 * Compact dropdown that lets the user switch between registered
 * InfrastructureAdapters (fetched from GET /demo/adapters).
 * Falls back to a static "Kratos Demo" label when no adapters are available
 * or when the list contains only one entry.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { AdapterMeta } from "../types/causelink";

// ─── Types ──────────────────────────────────────────────────────────────────
interface Props {
  selectedId: string;
  onChange: (adapterId: string) => void;
  disabled?: boolean;
}

// ─── Component ──────────────────────────────────────────────────────────────
export function EnvironmentSelector({ selectedId, onChange, disabled = false }: Props) {
  const [adapters, setAdapters] = useState<AdapterMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const abortRef = useRef<AbortController | null>(null);

  const fetchAdapters = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const res = await fetch("/demo/adapters", { signal: ctrl.signal });
      if (res.ok) {
        const body = await res.json() as { items: AdapterMeta[]; total: number };
        setAdapters(body.items ?? []);
      }
    } catch {
      // Network or abort — leave adapters empty (fallback label shown)
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchAdapters();
    return () => { abortRef.current?.abort(); };
  }, [fetchAdapters]);

  // Single adapter or none → static label, no interaction
  if (loading || adapters.length <= 1) {
    return (
      <div style={styles.staticLabel} title="Infrastructure environment">
        <span style={styles.envIcon}>⬡</span>
        <span>{adapters[0]?.display_name ?? "Kratos Demo"}</span>
        {adapters[0] && (
          <span style={styles.envBadge}>{adapters[0].environment}</span>
        )}
      </div>
    );
  }

  const current = adapters.find((a) => a.adapter_id === selectedId) ?? adapters[0];

  return (
    <div style={styles.wrapper}>
      <span style={styles.envIcon} title="Infrastructure environment">⬡</span>
      <select
        value={current.adapter_id}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        style={{ ...styles.select, opacity: disabled ? 0.5 : 1 }}
        aria-label="Select infrastructure environment"
      >
        {adapters.map((a) => (
          <option key={a.adapter_id} value={a.adapter_id}>
            {a.display_name} ({a.environment})
          </option>
        ))}
      </select>
    </div>
  );
}

// ─── Inline styles ──────────────────────────────────────────────────────────
const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
  },
  staticLabel: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    color: "#94a3b8",
    fontSize: "12px",
    userSelect: "none",
  },
  envIcon: {
    color: "#6366f1",
    fontSize: "14px",
    lineHeight: "1",
  },
  envBadge: {
    background: "#1e293b",
    color: "#94a3b8",
    borderRadius: "4px",
    padding: "1px 6px",
    fontSize: "10px",
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: "0.05em",
  },
  select: {
    background: "#1e293b",
    color: "#e2e8f0",
    border: "1px solid #334155",
    borderRadius: "4px",
    padding: "3px 8px",
    fontSize: "12px",
    cursor: "pointer",
    outline: "none",
  },
};
