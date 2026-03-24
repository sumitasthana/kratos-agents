/**
 * dashboard/src/components/ObservabilityPanel.tsx
 *
 * 2×2 grid layout:
 *   [ MetricsGrid    | TraceWaterfall ]
 *   [ LogStream      | AlertFeed      ]
 *
 * Props:
 *   activeInvestigationId — passed down to TraceWaterfall and LogStream filter.
 */

import React from "react";
import AlertFeed from "./AlertFeed";
import LogStream from "./LogStream";
import MetricsGrid from "./MetricsGrid";
import TraceWaterfall from "./TraceWaterfall";

export interface ObservabilityPanelProps {
  activeInvestigationId: string | null;
}

export default function ObservabilityPanel({
  activeInvestigationId,
}: ObservabilityPanelProps): React.JSX.Element {
  const logFilter = activeInvestigationId
    ? { investigationId: activeInvestigationId }
    : undefined;

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gridTemplateRows: "auto auto",
      gap: 12,
      height: "100%",
      overflow: "auto",
      padding: 4,
    }}>
      {/* Top-left: Metrics */}
      <div style={{
        background: "#1e293b",
        borderRadius: 8,
        overflow: "auto",
        border: "1px solid #334155",
      }}>
        <div style={{
          padding: "8px 12px",
          borderBottom: "1px solid #334155",
          fontSize: 11,
          color: "#94a3b8",
          textTransform: "uppercase",
          letterSpacing: 1,
        }}>
          Live Metrics
        </div>
        <MetricsGrid pollIntervalMs={2000} />
      </div>

      {/* Top-right: Trace waterfall */}
      <div style={{
        background: "#1e293b",
        borderRadius: 8,
        overflow: "auto",
        border: "1px solid #334155",
      }}>
        <div style={{
          padding: "8px 12px",
          borderBottom: "1px solid #334155",
          fontSize: 11,
          color: "#94a3b8",
          textTransform: "uppercase",
          letterSpacing: 1,
        }}>
          Trace Waterfall
          {activeInvestigationId && (
            <span style={{ color: "#475569", marginLeft: 8, fontSize: 10, fontFamily: "monospace" }}>
              {activeInvestigationId.slice(0, 12)}…
            </span>
          )}
        </div>
        <TraceWaterfall investigationId={activeInvestigationId} />
      </div>

      {/* Bottom-left: Log stream */}
      <div style={{
        background: "#1e293b",
        borderRadius: 8,
        overflow: "hidden",
        border: "1px solid #334155",
        display: "flex",
        flexDirection: "column",
      }}>
        <div style={{
          padding: "8px 12px",
          borderBottom: "1px solid #334155",
          fontSize: 11,
          color: "#94a3b8",
          textTransform: "uppercase",
          letterSpacing: 1,
          flexShrink: 0,
        }}>
          Structured Logs
        </div>
        <LogStream filter={logFilter} height={280} />
      </div>

      {/* Bottom-right: Alerts + events */}
      <div style={{
        background: "#1e293b",
        borderRadius: 8,
        overflow: "auto",
        border: "1px solid #334155",
      }}>
        <div style={{
          padding: "8px 12px",
          borderBottom: "1px solid #334155",
          fontSize: 11,
          color: "#94a3b8",
          textTransform: "uppercase",
          letterSpacing: 1,
        }}>
          Alerts &amp; Events
        </div>
        <AlertFeed />
      </div>
    </div>
  );
}
