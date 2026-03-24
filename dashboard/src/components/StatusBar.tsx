/**
 * StatusBar.tsx
 *
 * Always-visible 36px fixed-bottom status bar reflecting runtime state.
 * Never conditional — always rendered regardless of runtime state.
 * Sits BELOW all content via z-index: 100.
 */

import React from "react";
import type { StatusBarState } from "../types/demo";

interface StatusBarProps extends StatusBarState {}

const STATE_DOT: Record<StatusBarState["runtimeState"], { color: string; pulse: boolean; label: string }> = {
  BOOT:      { color: "#f59e0b", pulse: true,  label: "BOOT"      },
  IDLE:      { color: "#6b7280", pulse: false, label: "IDLE"      },
  RUNNING:   { color: "#3b82f6", pulse: true,  label: "RUNNING"   },
  CONFIRMED: { color: "#22c55e", pulse: false, label: "CONFIRMED" },
  ERROR:     { color: "#ef4444", pulse: false, label: "ERROR"     },
};

export default function StatusBar({
  runtimeState,
  scenarioId,
  activePhase,
  currentHop,
  totalHops,
  confidence,
  recordsLoaded,
  latencyMs,
  obsP95Ms,
  obsAlertCount,
  obsSseConnections,
  obsError,
}: StatusBarProps) {
  const dot = STATE_DOT[runtimeState];

  return (
    <div
      role="status"
      aria-label={`Platform status: ${dot.label}`}
      style={{
        position: "fixed",
        bottom: 0,
        left: 0,
        right: 0,
        height: 36,
        zIndex: 100,
        background: "#0a0c10",
        borderTop: "1px solid #1f2937",
        display: "flex",
        alignItems: "center",
        padding: "0 14px",
        gap: 0,
        fontSize: 11,
        fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
        color: "#94a3b8",
        userSelect: "none",
      }}
    >
      {/* Left section: state dot + label */}
      <div style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 120 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: dot.color,
            display: "inline-block",
            flexShrink: 0,
            boxShadow: dot.pulse ? `0 0 0 0 ${dot.color}` : undefined,
            animation: dot.pulse ? "statusPulse 1.2s ease-out infinite" : "none",
          }}
        />
        <span style={{ color: dot.color, fontWeight: 700, letterSpacing: "0.06em" }}>
          {dot.label}
        </span>
      </div>

      <Divider />

      {/* Middle section: scenario + phase + hop */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, flex: 1 }}>
        {scenarioId ? (
          <span style={{ color: "#e2e8f0", maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {scenarioId}
          </span>
        ) : (
          <span style={{ color: "#374151" }}>no scenario</span>
        )}
        {activePhase && (
          <>
            <Sep />
            <span style={{ color: "#6b7280" }}>phase</span>
            <span style={{ color: "#60a5fa", fontFamily: "monospace" }}>{activePhase}</span>
          </>
        )}
        {currentHop !== undefined && totalHops !== undefined && totalHops > 0 && (
          <>
            <Sep />
            <span style={{ color: "#6b7280" }}>hop</span>
            <span style={{ color: "#a78bfa", fontFamily: "monospace" }}>
              {currentHop}/{totalHops}
            </span>
          </>
        )}
      </div>

      <Divider />

      {/* Right section: confidence | records | latency */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, minWidth: 260, justifyContent: "flex-end" }}>
        {confidence !== undefined && confidence !== null ? (
          <Stat
            label="conf"
            value={`${(confidence * 100).toFixed(0)}%`}
            color={confidence >= 0.7 ? "#22c55e" : confidence >= 0.4 ? "#f59e0b" : "#ef4444"}
          />
        ) : (
          <Stat label="conf" value="—" color="#374151" />
        )}
        <Stat
          label="records"
          value={recordsLoaded !== undefined ? recordsLoaded.toLocaleString() : "—"}
          color="#94a3b8"
        />
        <Stat
          label="api"
          value={latencyMs !== undefined ? `${latencyMs}ms` : "—"}
          color={latencyMs !== undefined ? (latencyMs < 300 ? "#22c55e" : latencyMs < 1000 ? "#f59e0b" : "#ef4444") : "#374151"}
        />
      </div>

      <Divider />

      {/* Obs section: P95 | alerts | SSE */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 220, justifyContent: "flex-end" }}>
        <span style={{ color: "#334155", fontSize: 10, textTransform: "uppercase", letterSpacing: 1 }}>obs</span>
        <Stat
          label="P95"
          value={obsP95Ms !== null ? `${obsP95Ms}ms` : "—"}
          color={obsP95Ms !== null ? (obsP95Ms > 5000 ? "#f87171" : obsP95Ms > 2000 ? "#fbbf24" : "#4ade80") : "#374151"}
        />
        <Sep />
        <Stat
          label="alerts"
          value={String(obsAlertCount)}
          color={obsAlertCount > 0 ? "#ef4444" : "#22c55e"}
        />
        <Sep />
        <Stat
          label="SSE"
          value={String(obsSseConnections)}
          color={obsSseConnections > 10 ? "#f87171" : "#60a5fa"}
        />
        {obsError && (
          <span style={{ color: "#f87171", fontSize: 9, marginLeft: 4 }}>⚠ obs</span>
        )}
      </div>

      <style>{`
        @keyframes statusPulse {
          0%   { box-shadow: 0 0 0 0 currentColor; opacity: 1; }
          70%  { box-shadow: 0 0 0 6px transparent; opacity: 0.7; }
          100% { box-shadow: 0 0 0 0 transparent; opacity: 1; }
        }
      `}</style>
    </div>
  );
}

function Divider() {
  return (
    <div style={{ width: 1, height: 18, background: "#1f2937", margin: "0 14px", flexShrink: 0 }} />
  );
}

function Sep() {
  return <span style={{ color: "#1f2937" }}>·</span>;
}

interface StatProps {
  label: string;
  value: string;
  color: string;
}
function Stat({ label, value, color }: StatProps) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
      <span style={{ color: "#4b5563" }}>{label}</span>
      <span style={{ color, fontFamily: "monospace", fontWeight: 600 }}>{value}</span>
    </div>
  );
}
