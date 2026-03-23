/**
 * dashboard/src/components/TraceWaterfall.tsx
 *
 * Renders OTel spans as a waterfall chart for a single investigation.
 * Each bar is positioned by (span.start_time_ms - traceStart) / traceDuration
 * and sized by span.duration_ms / traceDuration × 100%.
 * Depth is inferred from parent_span_id hierarchy.
 */

import React, { useMemo } from "react";
import { useTraces } from "../hooks/useTraces";
import type { ObsSpan } from "../types/observability";

// ── Helpers ───────────────────────────────────────────────────────────────────

function computeDepths(spans: ObsSpan[]): Map<string, number> {
  const depths = new Map<string, number>();
  const childrenOf = new Map<string | null, ObsSpan[]>();

  for (const span of spans) {
    const key = span.parent_span_id ?? null;
    if (!childrenOf.has(key)) childrenOf.set(key, []);
    childrenOf.get(key)!.push(span);
  }

  function visit(spanId: string | null, depth: number): void {
    const children = childrenOf.get(spanId) ?? [];
    for (const child of children) {
      depths.set(child.span_id, depth);
      visit(child.span_id, depth + 1);
    }
  }
  visit(null, 0);
  return depths;
}

// ── Row ───────────────────────────────────────────────────────────────────────

interface SpanRowProps {
  span: ObsSpan;
  depth: number;
  traceStart: number;
  traceDuration: number;
}

function SpanRow({ span, depth, traceStart, traceDuration }: SpanRowProps): React.JSX.Element {
  const left = traceDuration > 0
    ? ((span.start_time_ms - traceStart) / traceDuration) * 100
    : 0;
  const width = traceDuration > 0
    ? Math.max((span.duration_ms / traceDuration) * 100, 0.5)
    : 100;

  const barColor = span.status === "ERROR" ? "#ef4444" : "#14b8a6";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2, minHeight: 24 }}>
      {/* Name column — fixed 220px */}
      <div style={{
        width: 220,
        flexShrink: 0,
        paddingLeft: depth * 14,
        fontSize: 11,
        color: "#cbd5e1",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
      }}
        title={span.name}
      >
        <span style={{ color: "#475569", marginRight: 4 }}>{"›".repeat(depth) || "●"}</span>
        {span.name}
      </div>

      {/* Bar column — fills remaining space */}
      <div style={{ flex: 1, position: "relative", height: 14, background: "#1e293b", borderRadius: 2 }}>
        <div style={{
          position: "absolute",
          left: `${left.toFixed(1)}%`,
          width: `${width.toFixed(1)}%`,
          height: "100%",
          background: barColor,
          borderRadius: 2,
          opacity: 0.85,
        }} />
      </div>

      {/* Duration */}
      <div style={{ width: 60, flexShrink: 0, fontSize: 10, color: "#64748b", textAlign: "right" }}>
        {span.duration_ms < 1000
          ? `${span.duration_ms.toFixed(0)}ms`
          : `${(span.duration_ms / 1000).toFixed(2)}s`}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export interface TraceWaterfallProps {
  investigationId: string | null;
}

export default function TraceWaterfall({ investigationId }: TraceWaterfallProps): React.JSX.Element {
  const { spans, loading, error } = useTraces(investigationId);

  const { sorted, depths, traceStart, traceDuration } = useMemo(() => {
    if (spans.length === 0) {
      return { sorted: [], depths: new Map<string, number>(), traceStart: 0, traceDuration: 1 };
    }
    const start = Math.min(...spans.map((s) => s.start_time_ms));
    const end = Math.max(...spans.map((s) => s.end_time_ms));
    const dur = Math.max(end - start, 1);
    const byStart = [...spans].sort((a, b) => a.start_time_ms - b.start_time_ms);
    return { sorted: byStart, depths: computeDepths(spans), traceStart: start, traceDuration: dur };
  }, [spans]);

  if (!investigationId) {
    return (
      <div style={{ padding: 24, color: "#475569", fontSize: 13 }}>
        No investigation selected. Start an RCA to see trace spans.
      </div>
    );
  }

  if (loading) {
    return <div style={{ padding: 16, color: "#94a3b8" }}>Loading trace…</div>;
  }

  if (error) {
    return <div style={{ padding: 16, color: "#f87171", fontFamily: "monospace" }}>Trace error: {error}</div>;
  }

  if (sorted.length === 0) {
    return (
      <div style={{ padding: 16, color: "#475569", fontSize: 13 }}>
        No spans recorded for this investigation yet.
      </div>
    );
  }

  return (
    <div style={{ padding: "8px 12px", overflow: "auto" }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <div style={{ width: 220, flexShrink: 0, fontSize: 10, color: "#475569", textTransform: "uppercase" }}>
          Span name
        </div>
        <div style={{ flex: 1, fontSize: 10, color: "#475569", textTransform: "uppercase" }}>
          Timeline ({traceDuration < 1000 ? `${traceDuration.toFixed(0)}ms` : `${(traceDuration / 1000).toFixed(2)}s`} total)
        </div>
        <div style={{ width: 60, flexShrink: 0, fontSize: 10, color: "#475569", textAlign: "right" }}>
          Dur.
        </div>
      </div>
      {sorted.map((span) => (
        <SpanRow
          key={span.span_id}
          span={span}
          depth={depths.get(span.span_id) ?? 0}
          traceStart={traceStart}
          traceDuration={traceDuration}
        />
      ))}
    </div>
  );
}
