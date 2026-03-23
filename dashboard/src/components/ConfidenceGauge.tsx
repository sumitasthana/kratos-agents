/**
 * ConfidenceGauge.tsx
 *
 * Displays the E×T×D×H confidence breakdown.
 * Accepts a pre-computed ConfidenceBreakdown from useInvestigation — no local state.
 */

import React from "react";
import type { ConfidenceBreakdown } from "../types/causelink";

interface Props {
  confidence: ConfidenceBreakdown | null;
}

const DIMENSION_LABELS: Array<{
  key: "evidenceScore" | "temporalScore" | "depthScore" | "hypothesisScore";
  label: string;
  color: string;
}> = [
  { key: "evidenceScore",   label: "Evidence (E)",     color: "#3b82f6" },
  { key: "temporalScore",   label: "Temporal (T)",     color: "#8b5cf6" },
  { key: "depthScore",      label: "Depth (D)",        color: "#06b6d4" },
  { key: "hypothesisScore", label: "Hypothesis (H)", color: "#10b981" },
];

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

function scoreColor(score: number): string {
  if (score >= 0.8) return "#4ade80";
  if (score >= 0.6) return "#fbbf24";
  return "#f87171";
}

const styles = {
  container: {
    background: "#111318",
    border: "1px solid #1f2937",
    borderRadius: 8,
    padding: "18px 20px",
  },
  title: {
    color: "#e2e8f0",
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: "0.08em",
    textTransform: "uppercase" as const,
    marginBottom: 16,
  },
  compositeRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    background: "#0f1117",
    border: "1px solid #1f2937",
    borderRadius: 6,
    padding: "10px 14px",
    marginBottom: 16,
  },
  compositeLabel: {
    color: "#64748b",
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: "0.07em",
  },
  compositeValue: (score: number) => ({
    fontSize: 24,
    fontWeight: 800,
    fontFamily: "'JetBrains Mono', monospace",
    color: scoreColor(score),
  }),
  statusBadge: (score: number) => ({
    background: scoreColor(score) + "22",
    color: scoreColor(score),
    borderRadius: 4,
    padding: "2px 10px",
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.05em",
  }),
  dimRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    marginBottom: 8,
  },
  dimLabel: {
    color: "#94a3b8",
    fontSize: 11,
    width: 130,
    flexShrink: 0,
  },
  barTrack: {
    flex: 1,
    height: 6,
    background: "#1f2937",
    borderRadius: 3,
    overflow: "hidden",
  },
  barFill: (score: number, color: string) => ({
    height: "100%",
    width: pct(score),
    background: color,
    borderRadius: 3,
    transition: "width 0.5s ease",
  }),
  dimScore: (color: string) => ({
    color,
    fontSize: 12,
    fontWeight: 700,
    fontFamily: "'JetBrains Mono', monospace",
    width: 36,
    textAlign: "right" as const,
  }),
  formula: {
    color: "#374151",
    fontSize: 10,
    fontFamily: "'JetBrains Mono', monospace",
    textAlign: "center" as const,
    marginTop: 10,
  },
  empty: {
    color: "#4b5563",
    fontSize: 13,
    textAlign: "center" as const,
    padding: "20px 0",
  },
};

export default function ConfidenceGauge({ confidence }: Props) {
  if (!confidence) {
    return (
      <div style={styles.container}>
        <div style={styles.title}>Confidence — E×T×D×H</div>
        <div style={styles.empty}>Awaiting confidence calculation…</div>
      </div>
    );
  }

  const composite = confidence.composite_score ?? 0;
  const statusLabel = composite >= 0.80 ? "CONFIRMED" : composite >= 0.50 ? "PROBABLE" : "POSSIBLE";

  return (
    <div style={styles.container}>
      <div style={styles.title}>Confidence — E×T×D×H</div>

      <div style={styles.compositeRow}>
        <div>
          <div style={styles.compositeLabel}>Composite Score</div>
          <div style={styles.compositeValue(composite)}>{composite.toFixed(4)}</div>
        </div>
        <span style={styles.statusBadge(composite)}>{statusLabel}</span>
      </div>

      {DIMENSION_LABELS.map(({ key, label, color }) => {
        const val = (confidence[key] ?? confidence[
          key === "evidenceScore"   ? "evidence_score" :
          key === "temporalScore"   ? "temporal_score" :
          key === "depthScore"      ? "depth_score" :
          "hypothesis_alignment_score"
        ] ?? 0) as number;
        return (
          <div key={key} style={styles.dimRow}>
            <span style={styles.dimLabel}>{label}</span>
            <div style={styles.barTrack}>
              <div style={styles.barFill(val, color)} />
            </div>
            <span style={styles.dimScore(color)}>{pct(val)}</span>
          </div>
        );
      })}

      <div style={styles.formula}>
        composite = E×0.40 + T×0.25 + D×0.20 + H×0.15
      </div>
    </div>
  );
}
