/**
 * ControlScanPanel.tsx
 *
 * Displays control scan findings.
 * Accepts result/loading/error from useControlScan hook in parent — no local fetch.
 */

import React from "react";
import type { ControlFinding, ControlScanResult } from "../types/causelink";

interface Props {
  result: ControlScanResult | null;
  loading: boolean;
  error: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  FAILED:  "#f87171",
  PASSED:  "#4ade80",
  WARNING: "#fb923c",
};

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "#f87171",
  HIGH:     "#fb923c",
  MEDIUM:   "#fbbf24",
  LOW:      "#94a3b8",
};

const s = {
  container: {
    background: "#111318",
    border: "1px solid #1f2937",
    borderRadius: 8,
    padding: "18px 20px",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 14,
  },
  title: {
    color: "#e2e8f0",
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: "0.08em",
    textTransform: "uppercase" as const,
  },
  badge: (color: string) => ({
    background: color + "22",
    color: color,
    borderRadius: 4,
    padding: "2px 8px",
    fontSize: 11,
    fontWeight: 700,
  }),
  summaryRow: {
    display: "flex",
    gap: 16,
    marginBottom: 14,
  },
  summaryItem: {
    background: "#161b25",
    border: "1px solid #1f2937",
    borderRadius: 6,
    padding: "8px 14px",
    textAlign: "center" as const,
    flex: 1,
  },
  summaryValue: {
    fontSize: 22,
    fontWeight: 700,
    color: "#e2e8f0",
  },
  summaryLabel: {
    fontSize: 10,
    color: "#64748b",
    textTransform: "uppercase" as const,
    letterSpacing: "0.07em",
    marginTop: 2,
  },
  table: {
    width: "100%",
    borderCollapse: "collapse" as const,
    fontSize: 12,
  },
  th: {
    color: "#64748b",
    textAlign: "left" as const,
    padding: "6px 10px",
    borderBottom: "1px solid #1f2937",
    fontWeight: 600,
    fontSize: 10,
    textTransform: "uppercase" as const,
    letterSpacing: "0.07em",
  },
  td: {
    padding: "8px 10px",
    borderBottom: "1px solid #1a2030",
    color: "#94a3b8",
    verticalAlign: "top" as const,
  },
  mono: {
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: 11,
  },
  empty: {
    color: "#4b5563",
    fontSize: 13,
    padding: "20px 0",
    textAlign: "center" as const,
  },
};

export default function ControlScanPanel({ result, loading, error }: Props) {
  if (loading) return <div style={{ ...s.container, ...s.empty }}>Loading control scan…</div>;
  if (error)   return <div style={{ ...s.container, color: "#f87171", fontSize: 12 }}>Error: {error}</div>;
  if (!result) return <div style={{ ...s.container, ...s.empty }}>Select a scenario to view controls.</div>;

  return (
    <div style={s.container}>
      <div style={s.header}>
        <span style={s.title}>Control Scan</span>
        {result.has_critical_failure && (
          <span style={s.badge("#f87171")}>CRITICAL FAILURE</span>
        )}
      </div>

      <div style={s.summaryRow}>
        <div style={s.summaryItem}>
          <div style={{ ...s.summaryValue, color: "#e2e8f0" }}>{result.total_controls}</div>
          <div style={s.summaryLabel}>Total</div>
        </div>
        <div style={s.summaryItem}>
          <div style={{ ...s.summaryValue, color: "#4ade80" }}>{result.passed}</div>
          <div style={s.summaryLabel}>Passed</div>
        </div>
        <div style={s.summaryItem}>
          <div style={{ ...s.summaryValue, color: "#f87171" }}>{result.failed}</div>
          <div style={s.summaryLabel}>Failed</div>
        </div>
        <div style={s.summaryItem}>
          <div style={{ ...s.summaryValue, color: "#fb923c" }}>{result.warnings}</div>
          <div style={s.summaryLabel}>Warnings</div>
        </div>
      </div>

      <table style={s.table}>
        <thead>
          <tr>
            <th style={s.th}>ID</th>
            <th style={s.th}>Name</th>
            <th style={s.th}>Regulation</th>
            <th style={s.th}>Status</th>
            <th style={s.th}>Severity</th>
            <th style={s.th}>Defect</th>
            <th style={s.th}>Reason</th>
          </tr>
        </thead>
        <tbody>
          {result.findings.map((f) => (
            <tr key={f.control_id}>
              <td style={{ ...s.td, ...s.mono, color: "#e2e8f0", fontWeight: 600 }}>
                {f.control_id}
              </td>
              <td style={{ ...s.td, color: "#cbd5e1" }}>{f.name}</td>
              <td style={{ ...s.td, ...s.mono, color: "#64748b", fontSize: 10 }}>
                {f.regulation}
              </td>
              <td style={s.td}>
                <span style={s.badge(STATUS_COLORS[f.status] ?? "#94a3b8")}>
                  {f.status}
                </span>
              </td>
              <td style={s.td}>
                <span style={{ color: SEVERITY_COLORS[f.severity] ?? "#94a3b8", fontWeight: 600, fontSize: 11 }}>
                  {f.severity}
                </span>
              </td>
              <td style={{ ...s.td, ...s.mono, color: "#f59e0b", fontSize: 11 }}>
                {f.defect_id ?? "—"}
              </td>
              <td style={{ ...s.td, color: "#64748b", maxWidth: 260 }}>
                {f.failure_reason ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
