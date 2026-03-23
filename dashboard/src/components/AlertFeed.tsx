/**
 * dashboard/src/components/AlertFeed.tsx
 *
 * Renders active alerts (threshold violations) and recent named events.
 * CRITICAL alerts pulse via CSS animation.
 * Polls every 5 s via useAlerts.
 */

import React from "react";
import { useAlerts } from "../hooks/useAlerts";
import type { ObsAlert, ObsEvent } from "../types/observability";

// ── CSS keyframe ──────────────────────────────────────────────────────────────
// We inject once via a <style> tag rendered alongside the component.
const PULSE_CSS = `
@keyframes kratos-pulse {
  0%   { opacity: 1; }
  50%  { opacity: 0.45; }
  100% { opacity: 1; }
}
.kratos-pulse { animation: kratos-pulse 1s ease-in-out infinite; }
`;

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "#ef4444",
  WARNING:  "#f59e0b",
  INFO:     "#38bdf8",
};

// ── Alert row ─────────────────────────────────────────────────────────────────

function AlertRow({ alert }: { alert: ObsAlert }): React.JSX.Element {
  const color = SEVERITY_COLORS[alert.severity] ?? "#e2e8f0";
  const pulse = alert.severity === "CRITICAL" ? "kratos-pulse" : undefined;
  const ts = new Date(alert.fired_at).toLocaleTimeString();
  return (
    <div className={pulse} style={{
      display: "flex",
      alignItems: "flex-start",
      gap: 8,
      padding: "6px 10px",
      borderLeft: `3px solid ${color}`,
      background: "#0f172a",
      marginBottom: 4,
      borderRadius: "0 4px 4px 0",
    }}>
      <span style={{ color, fontSize: 11, fontWeight: 700, flexShrink: 0, width: 64 }}>
        {alert.severity}
      </span>
      <div style={{ flex: 1, fontSize: 11 }}>
        <div style={{ color: "#e2e8f0", fontWeight: 600 }}>{alert.name}</div>
        <div style={{ color: "#94a3b8", marginTop: 2 }}>{alert.message}</div>
      </div>
      <span style={{ color: "#475569", fontSize: 10, flexShrink: 0 }}>{ts}</span>
    </div>
  );
}

// ── Event row ─────────────────────────────────────────────────────────────────

function EventRow({ event }: { event: ObsEvent }): React.JSX.Element {
  const ts = new Date(event.timestamp).toLocaleTimeString();
  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: 8,
      padding: "3px 10px",
      fontSize: 11,
      borderBottom: "1px solid #1e293b",
    }}>
      <span style={{ color: "#475569", flexShrink: 0, width: 70 }}>{ts}</span>
      <span style={{ color: "#38bdf8", flex: 1, fontFamily: "monospace" }}>{event.event_name}</span>
      {event.payload["scenario_id"] !== undefined && (
        <span style={{ color: "#64748b", fontSize: 10 }}>
          {String(event.payload["scenario_id"])}
        </span>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function AlertFeed(): React.JSX.Element {
  const { alerts, events, lastChecked } = useAlerts();

  const checkedStr = lastChecked !== null
    ? new Date(lastChecked).toLocaleTimeString()
    : "never";

  return (
    <div style={{ padding: "8px 12px", overflow: "auto" }}>
      <style>{PULSE_CSS}</style>

      {/* Alerts section */}
      <div style={{ marginBottom: 16 }}>
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 8,
        }}>
          <span style={{ fontSize: 11, color: "#475569", textTransform: "uppercase", letterSpacing: 1.5 }}>
            Active Alerts
          </span>
          <span style={{ fontSize: 10, color: "#334155" }}>checked {checkedStr}</span>
        </div>
        {alerts.length === 0 ? (
          <div style={{ fontSize: 12, color: "#4ade80", padding: "4px 10px" }}>
            ✓ No active alerts
          </div>
        ) : (
          alerts.map((a) => <AlertRow key={a.alert_id} alert={a} />)
        )}
      </div>

      {/* Recent events section */}
      <div>
        <div style={{ fontSize: 11, color: "#475569", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 8 }}>
          Recent Events
        </div>
        {events.length === 0 ? (
          <div style={{ fontSize: 12, color: "#475569", padding: "4px 10px" }}>No events yet.</div>
        ) : (
          events.map((e) => <EventRow key={e.event_id} event={e} />)
        )}
      </div>
    </div>
  );
}
