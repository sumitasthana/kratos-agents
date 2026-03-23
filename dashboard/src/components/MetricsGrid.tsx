/**
 * dashboard/src/components/MetricsGrid.tsx
 *
 * Live metrics grid — RED signals + USE signals.
 * Polls /obs/metrics/live via useMetrics(2000).
 * Renders delta arrows (↑↓→) by comparing against previous snapshot.
 * A tiny 20-point SVG sparkline is drawn for P95 latency history.
 */

import React, { useEffect, useRef, useState } from "react";
import { useMetrics } from "../hooks/useMetrics";

// ── Sparkline ─────────────────────────────────────────────────────────────────

const SPARKLINE_W = 80;
const SPARKLINE_H = 24;
const SPARKLINE_MAX_PTS = 20;

function buildSparklinePath(values: number[]): string {
  if (values.length < 2) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * SPARKLINE_W;
    const y = SPARKLINE_H - ((v - min) / range) * SPARKLINE_H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return `M${pts.join(" L")}`;
}

// ── Metric card primitives ────────────────────────────────────────────────────

type DeltaDir = "up" | "down" | "flat";

function delta(curr: number, prev: number | undefined): DeltaDir {
  if (prev === undefined) return "flat";
  if (curr > prev) return "up";
  if (curr < prev) return "down";
  return "flat";
}

const DELTA_CHARS: Record<DeltaDir, string> = { up: "↑", down: "↓", flat: "→" };

interface CardProps {
  label: string;
  value: string;
  dir?: DeltaDir;
  color?: string;
  spark?: number[];
}

function Card({ label, value, dir = "flat", color = "#e2e8f0", spark }: CardProps): React.JSX.Element {
  const dirColor = dir === "up" ? "#f87171" : dir === "down" ? "#4ade80" : "#94a3b8";
  return (
    <div style={{
      background: "#1e293b",
      border: "1px solid #334155",
      borderRadius: 8,
      padding: "10px 14px",
      display: "flex",
      flexDirection: "column",
      gap: 4,
      minWidth: 130,
    }}>
      <span style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: 1 }}>
        {label}
      </span>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
        <span style={{ fontSize: 20, fontWeight: 700, color, fontVariantNumeric: "tabular-nums" }}>
          {value}
        </span>
        <span style={{ fontSize: 13, color: dirColor }}>{DELTA_CHARS[dir]}</span>
      </div>
      {spark && spark.length >= 2 && (
        <svg width={SPARKLINE_W} height={SPARKLINE_H} style={{ display: "block", marginTop: 2 }}>
          <path d={buildSparklinePath(spark)} fill="none" stroke="#38bdf8" strokeWidth={1.5} />
        </svg>
      )}
    </div>
  );
}

// ── Section header ────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }): React.JSX.Element {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11, color: "#475569", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 8 }}>
        {title}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {children}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export interface MetricsGridProps {
  pollIntervalMs?: number;
}

export default function MetricsGrid({ pollIntervalMs = 2000 }: MetricsGridProps): React.JSX.Element {
  const { metrics, prevMetrics, error } = useMetrics(pollIntervalMs);

  // Accumulate P95 history for sparkline
  const p95Hist = useRef<number[]>([]);
  useEffect(() => {
    if (metrics?.performance.phase_p95_ms !== undefined) {
      p95Hist.current = [
        ...p95Hist.current,
        metrics.performance.phase_p95_ms,
      ].slice(-SPARKLINE_MAX_PTS);
    }
  }, [metrics?.performance.phase_p95_ms]);

  if (error) {
    return (
      <div style={{ padding: 16, color: "#f87171", fontFamily: "monospace" }}>
        Metrics unavailable: {error}
      </div>
    );
  }

  if (!metrics) {
    return (
      <div style={{ padding: 16, color: "#94a3b8" }}>Loading metrics…</div>
    );
  }

  const p = metrics;
  const q = prevMetrics;

  const fmtMs = (v: number): string => `${v.toFixed(0)}ms`;
  const fmtPct = (v: number): string => `${(v * 100).toFixed(1)}%`;
  const fmtInt = (v: number): string => String(Math.round(v));

  return (
    <div style={{ padding: "12px 0", overflow: "auto" }}>
      {/* RED — Rate · Errors · Duration */}
      <Section title="RED — Investigations">
        <Card
          label="Rate (in-flight)"
          value={fmtInt(p.investigations.in_flight)}
          dir={delta(p.investigations.in_flight, q?.investigations.in_flight)}
          color="#38bdf8"
        />
        <Card
          label="Completed"
          value={fmtInt(p.investigations.completed_total)}
          dir={delta(p.investigations.completed_total, q?.investigations.completed_total)}
          color="#4ade80"
        />
        <Card
          label="Error rate"
          value={fmtPct(p.investigations.error_rate)}
          dir={delta(p.investigations.error_rate, q?.investigations.error_rate)}
          color={p.investigations.error_rate > 0.1 ? "#f87171" : "#4ade80"}
        />
        <Card
          label="P95 latency"
          value={fmtMs(p.performance.phase_p95_ms)}
          dir={delta(p.performance.phase_p95_ms, q?.performance.phase_p95_ms)}
          color={p.performance.phase_p95_ms > 5000 ? "#f87171" : "#e2e8f0"}
          spark={p95Hist.current}
        />
      </Section>

      {/* Evidence */}
      <Section title="Evidence">
        <Card
          label="Collected"
          value={fmtInt(p.evidence.collected_total)}
          dir={delta(p.evidence.collected_total, q?.evidence.collected_total)}
          color="#e2e8f0"
        />
        <Card
          label="Signal ratio"
          value={fmtPct(p.evidence.signal_ratio)}
          dir={delta(p.evidence.signal_ratio, q?.evidence.signal_ratio)}
          color={p.evidence.signal_ratio > 0.5 ? "#4ade80" : "#fbbf24"}
        />
      </Section>

      {/* Validation */}
      <Section title="Validation Gates">
        <Card
          label="Gate pass"
          value={fmtInt(p.validation.pass_total)}
          dir={delta(p.validation.pass_total, q?.validation.pass_total)}
          color="#4ade80"
        />
        <Card
          label="Gate fail rate"
          value={fmtPct(p.validation.gate_fail_rate)}
          dir={delta(p.validation.gate_fail_rate, q?.validation.gate_fail_rate)}
          color={p.validation.gate_fail_rate > 0.05 ? "#f87171" : "#4ade80"}
        />
      </Section>

      {/* Confidence */}
      <Section title="Confidence">
        <Card
          label="Avg score"
          value={fmtPct(p.confidence.current_avg)}
          dir={delta(p.confidence.current_avg, q?.confidence.current_avg)}
          color={p.confidence.current_avg >= 0.7 ? "#4ade80" : "#fbbf24"}
        />
        <Card
          label="P95 score"
          value={fmtPct(p.confidence.p95)}
          dir="flat"
          color="#e2e8f0"
        />
      </Section>

      {/* SSE */}
      <Section title="SSE Streams">
        <Card
          label="Active"
          value={fmtInt(p.sse.active_connections)}
          dir={delta(p.sse.active_connections, q?.sse.active_connections)}
          color={p.sse.active_connections > 10 ? "#f87171" : "#38bdf8"}
        />
        <Card
          label="Events sent"
          value={fmtInt(p.sse.events_emitted_total)}
          dir={delta(p.sse.events_emitted_total, q?.sse.events_emitted_total)}
          color="#e2e8f0"
        />
      </Section>
    </div>
  );
}
