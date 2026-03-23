/**
 * RecommendationList.tsx
 *
 * Renders the ranked remediation recommendations.
 * Accepts pre-computed Recommendation[] from useInvestigation — no local state.
 */

import React from "react";
import type { Recommendation } from "../types/causelink";

interface Props {
  recommendations: Recommendation[];
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
    marginBottom: 14,
  },
  item: {
    display: "flex",
    gap: 12,
    padding: "10px 12px",
    borderRadius: 6,
    border: "1px solid #1f2937",
    background: "#0f1117",
    marginBottom: 8,
    alignItems: "flex-start",
  },
  indexBadge: {
    background: "#1d4ed822",
    color: "#3b82f6",
    borderRadius: 5,
    padding: "2px 8px",
    fontSize: 11,
    fontWeight: 700,
    fontFamily: "'JetBrains Mono', monospace",
    flexShrink: 0,
    marginTop: 1,
  },
  defectTag: {
    color: "#f59e0b",
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: 11,
    fontWeight: 700,
    flexShrink: 0,
  },
  text: {
    color: "#94a3b8",
    fontSize: 12,
    lineHeight: 1.6,
  },
  empty: {
    color: "#4b5563",
    fontSize: 13,
    textAlign: "center" as const,
    padding: "20px 0",
  },
};

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "#f87171",
  HIGH:     "#fb923c",
  MEDIUM:   "#fbbf24",
  LOW:      "#94a3b8",
};

export default function RecommendationList({ recommendations }: Props) {
  if (recommendations.length === 0) {
    return (
      <div style={styles.container}>
        <div style={styles.title}>Recommendations</div>
        <div style={styles.empty}>Awaiting recommendation generation…</div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.title}>Recommendations ({recommendations.length})</div>
      {recommendations.map((rec, i) => {
        // Backend may send snake_case aliases; normalise here
        const defectId = rec.defectId ?? rec.defect_id;
        const regulation = rec.regulatoryBasis ?? rec.regulation;
        // `effort` from backend is a verbose string like "LOW — single-line JCL change"
        const effortRaw = (rec as Record<string, unknown>)["effort"] as string | undefined;
        const effortShort = effortRaw?.split("—")[0].trim();
        const confidence = rec.confidence;

        return (
          <div key={i} style={styles.item}>
            {/* Rank badge */}
            <span style={styles.indexBadge}>#{rec.rank ?? i + 1}</span>

            <div style={{ flex: 1 }}>
              {/* Top row: defect ID chip */}
              {defectId && (
                <div style={{ marginBottom: 4 }}>
                  <span style={styles.defectTag}>{defectId}</span>
                </div>
              )}

              {/* Main action text */}
              <div style={styles.text}>{rec.action}</div>

              {/* Artifact path */}
              {rec.artifact && (
                <div style={{
                  color: "#4b5563",
                  fontSize: 11,
                  fontFamily: "'JetBrains Mono', monospace",
                  marginTop: 4,
                }}>
                  {rec.artifact}
                </div>
              )}

              {/* Bottom meta row: regulation · effort · confidence */}
              {(regulation || effortShort || confidence !== undefined) && (
                <div style={{ display: "flex", gap: 10, marginTop: 6, flexWrap: "wrap" }}>
                  {regulation && (
                    <span style={{ color: "#64748b", fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }}>
                      {regulation}
                    </span>
                  )}
                  {effortShort && (
                    <span style={{
                      background: "#1e293b",
                      color: "#94a3b8",
                      borderRadius: 3,
                      padding: "1px 6px",
                      fontSize: 10,
                      fontWeight: 600,
                    }}>
                      {effortShort}
                    </span>
                  )}
                  {confidence !== undefined && (
                    <span style={{ color: "#64748b", fontSize: 10 }}>
                      conf {Math.round(confidence * 100)}%
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* Severity badge (optional) */}
            {rec.severity && (
              <span style={{
                background: (SEVERITY_COLORS[rec.severity] ?? "#94a3b8") + "22",
                color: SEVERITY_COLORS[rec.severity] ?? "#94a3b8",
                borderRadius: 4,
                padding: "1px 7px",
                fontSize: 10,
                fontWeight: 700,
                flexShrink: 0,
                alignSelf: "flex-start",
              }}>
                {rec.severity}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
