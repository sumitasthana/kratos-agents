/**
 * IncidentCard.tsx
 *
 * Displays the structured incident card synthesized in the INCIDENT_CARD phase.
 * Accepts pre-computed IncidentCard data from useInvestigation — no local state.
 */

import React from "react";
import type { IncidentCard as IncidentData } from "../types/causelink";

interface Props {
  incident: IncidentData | null;
}

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "#f87171",
  HIGH:     "#fb923c",
  MEDIUM:   "#fbbf24",
  LOW:      "#4ade80",
};

const styles = {
  card: {
    background: "#111318",
    border: "1px solid #1f2937",
    borderRadius: 8,
    padding: "18px 20px",
    display: "flex",
    flexDirection: "column" as const,
    gap: 10,
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 4,
  },
  incidentId: {
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: 13,
    fontWeight: 700,
    color: "#e2e8f0",
  },
  severity: (sev: string) => ({
    background: (SEVERITY_COLORS[sev] ?? "#94a3b8") + "22",
    color: SEVERITY_COLORS[sev] ?? "#94a3b8",
    borderRadius: 4,
    padding: "2px 10px",
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.05em",
  }),
  title: {
    color: "#e2e8f0",
    fontSize: 15,
    fontWeight: 600,
    marginBottom: 2,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "6px 20px",
    marginTop: 4,
  },
  field: {
    display: "flex",
    flexDirection: "column" as const,
    gap: 1,
  },
  fieldLabel: {
    color: "#4b5563",
    fontSize: 10,
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: "0.07em",
  },
  fieldValue: {
    color: "#94a3b8",
    fontSize: 12,
    fontFamily: "'JetBrains Mono', monospace",
  },
  defectBox: {
    background: "#0f1117",
    border: "1px solid #7f1d1d",
    borderRadius: 5,
    padding: "8px 12px",
    marginTop: 4,
  },
  defectTitle: {
    color: "#fca5a5",
    fontSize: 10,
    fontWeight: 700,
    textTransform: "uppercase" as const,
    letterSpacing: "0.07em",
    marginBottom: 4,
  },
  defectId: {
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: 11,
    color: "#f59e0b",
    marginBottom: 2,
  },
  defectArtifact: {
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: 11,
    color: "#94a3b8",
    marginBottom: 4,
  },
  defectDesc: {
    color: "#9ca3af",
    fontSize: 12,
    lineHeight: 1.5,
  },
  empty: {
    color: "#4b5563",
    fontSize: 13,
    padding: "20px 0",
    textAlign: "center" as const,
  },
};

export default function IncidentCard({ incident }: Props) {
  if (!incident) {
    return (
      <div style={styles.card}>
        <div style={{ color: "#4b5563", fontSize: 13 }}>Awaiting incident card synthesis…</div>
      </div>
    );
  }

  const inc = incident;

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <span style={styles.incidentId}>{inc.incidentId ?? inc.incident_id}</span>
        <span style={styles.severity(inc.severity)}>{inc.severity}</span>
      </div>

      <div style={styles.title}>{inc.title}</div>

      <div style={styles.grid}>
        <div style={styles.field}>
          <span style={styles.fieldLabel}>Regulation</span>
          <span style={styles.fieldValue}>{inc.regulation || "—"}</span>
        </div>
        <div style={styles.field}>
          <span style={styles.fieldLabel}>Control</span>
          <span style={styles.fieldValue}>
            {(inc.controlId ?? inc.control_id) || "—"} — {(inc.controlName ?? inc.control_name) || "—"}
          </span>
        </div>
        <div style={styles.field}>
          <span style={styles.fieldLabel}>Status</span>
          <span style={styles.fieldValue}>{inc.status}</span>
        </div>
        <div style={styles.field}>
          <span style={styles.fieldLabel}>Reported At</span>
          <span style={styles.fieldValue}>
            {(inc.reportedAt ?? inc.reported_at)
              ? new Date(inc.reportedAt ?? inc.reported_at ?? "").toLocaleDateString()
              : "—"}
          </span>
        </div>
      </div>

      {((inc.defectId ?? inc.defect_id) || (inc.defectDescription ?? inc.defect_description)) && (
        <div style={styles.defectBox}>
          <div style={styles.defectTitle}>Root Defect</div>
          {(inc.defectId ?? inc.defect_id) && (
            <div style={styles.defectId}>{inc.defectId ?? inc.defect_id}</div>
          )}
          {(inc.defectArtifact ?? inc.defect_artifact) && (
            <div style={styles.defectArtifact}>{inc.defectArtifact ?? inc.defect_artifact}</div>
          )}
          {(inc.defectDescription ?? inc.defect_description) && (
            <div style={styles.defectDesc}>{inc.defectDescription ?? inc.defect_description}</div>
          )}
        </div>
      )}

      {inc.impact && Object.keys(inc.impact).length > 0 && (
        <div style={{ marginTop: 4 }}>
          <div style={{ ...styles.fieldLabel, marginBottom: 4 }}>Impact</div>
          <div style={{ display: "flex", flexWrap: "wrap" as const, gap: 8 }}>
            {Object.entries(inc.impact).map(([k, v]) => (
              <div
                key={k}
                style={{
                  background: "#161b25",
                  border: "1px solid #1f2937",
                  borderRadius: 5,
                  padding: "4px 10px",
                  fontSize: 11,
                }}
              >
                <span style={{ color: "#64748b", textTransform: "capitalize" as const }}>{k.replace(/_/g, " ")}: </span>
                <span style={{ color: "#e2e8f0", fontWeight: 600 }}>{String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
