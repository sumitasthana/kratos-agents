/**
 * FdicDemo.tsx
 *
 * Redesigned FDIC Part 370/330 CauseLink demo page.
 *
 * Key differences vs DemoPage:
 *  • Slate-950 dark background (#020617) throughout
 *  • Left sidebar shows 3 clickable scenario cards (replaces generic ScenarioSelector)
 *  • Phase pipeline pill bar with CSS pulse animation on the active phase
 *  • 6-tab layout (trace | controls | incident | recommendations | confidence | data)
 *  • No observability/reasoning tabs keeps surface area focused on compliance RCA
 *
 * Layout (100vh):
 *   [Header            44px ]
 *   [Phase Pipeline    52px ]
 *   [Sidebar 240px | Tabs + Content  flex-1 ]
 *   [StatusBar         36px ]  ← position: fixed, always visible
 *
 * Build constraints:
 *  • No Tailwind (not installed) — inline styles with exact Tailwind color values
 *  • No new npm deps
 *  • TypeScript strict mode — no `any`, explicit types everywhere
 */

import React, { useState } from "react";

import BootScreen          from "../components/BootScreen";
import StatusBar           from "../components/StatusBar";
import { RcaTracePanel }       from "../components/RcaTracePanel";
import { ControlScanPanel }    from "../components/ControlScanPanel";
import IncidentCardPanel   from "../components/IncidentCard";
import RecommendationList  from "../components/RecommendationList";
import { ConfidenceGauge }     from "../components/ConfidenceGauge";
import SampleDataTable     from "../components/SampleDataTable";

import { usePlatformBoot }  from "../hooks/usePlatformBoot";
import { useInvestigation } from "../hooks/useInvestigation";
import { useControlScan }   from "../hooks/useControlScan";

import { SCENARIO_META, PHASE_ORDER, PHASE_LABELS } from "../constants/scenarios";
import type { ScenarioId, StatusBarState, RuntimeState } from "../types/demo";
import type { PhaseId } from "../types/causelink";

// ── Design tokens (Tailwind slate-950 palette, exact hex values) ─────────────
const C = {
  // Backgrounds
  bg:          "#020617",  // slate-950
  surface:     "#0f172a",  // slate-900
  elevated:    "#1e293b",  // slate-800
  // Borders
  border:      "#334155",  // slate-700
  borderDim:   "#1e293b",  // slate-800
  // Text
  text:        "#f1f5f9",  // slate-100
  textSub:     "#94a3b8",  // slate-400
  textMuted:   "#475569",  // slate-600
  // Accent (indigo)
  accent:      "#6366f1",  // indigo-500
  accentBg:    "#1e1b4b",  // indigo-950
  accentMid:   "#3730a3",  // indigo-700
  // Semantic colours
  green:       "#22c55e",  // green-500
  greenBg:     "#052e16",  // green-950
  greenBorder: "#166534",  // green-800
  amber:       "#f59e0b",  // amber-500
  amberBg:     "#1c1005",  // amber-950-ish
  amberBorder: "#92400e",  // amber-800
  red:         "#ef4444",  // red-500
  redBg:       "#1c0505",  // red-950-ish
  redBorder:   "#991b1b",  // red-800
} as const;

// Per-scenario colour themes matching ScenarioMeta.color values
const SCENARIO_PALETTE: Record<string, { main: string; bg: string; border: string }> = {
  red:   { main: C.red,   bg: C.redBg,   border: C.redBorder   },
  amber: { main: C.amber, bg: C.amberBg, border: C.amberBorder },
  green: { main: C.green, bg: C.greenBg, border: C.greenBorder },
};

// ── Local tab type (6 tabs — no reasoning/observability) ─────────────────────
type FdicTabId =
  | "trace"
  | "controls"
  | "incident"
  | "recommendations"
  | "confidence"
  | "data";

const TABS: Array<{ id: FdicTabId; label: string }> = [
  { id: "trace",           label: "Causal Trace"    },
  { id: "controls",        label: "Controls"        },
  { id: "incident",        label: "Incident"        },
  { id: "recommendations", label: "Recommendations" },
  { id: "confidence",      label: "Confidence"      },
  { id: "data",            label: "Sample Data"     },
];

// ── Runtime state derivation ──────────────────────────────────────────────────
function deriveRuntimeState(
  isBooting: boolean,
  bootFailed: boolean,
  invStatus: string | undefined,
  loading: boolean,
): RuntimeState {
  if (isBooting)                                   return "BOOT";
  if (bootFailed)                                  return "ERROR";
  if (loading || invStatus === "RUNNING")           return "RUNNING";
  if (invStatus === "CONFIRMED")                    return "CONFIRMED";
  if (invStatus === "FAILED" || invStatus === "ERROR") return "ERROR";
  return "IDLE";
}

// ── CSS keyframes injected once via <style> ───────────────────────────────────
const GLOBAL_CSS = `
  @keyframes fdic-pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(99,102,241,0.45); }
    50%       { box-shadow: 0 0 0 7px rgba(99,102,241,0);  }
  }
  @keyframes fdic-spin {
    to { transform: rotate(360deg); }
  }
  .fdic-phase-active {
    animation: fdic-pulse 1.6s ease-in-out infinite;
  }
  button.fdic-tab:focus-visible {
    outline: 2px solid #6366f1;
    outline-offset: -2px;
  }
  button.fdic-card:focus-visible {
    outline: 2px solid #6366f1;
    outline-offset: -2px;
  }
`;

// ── Main component ────────────────────────────────────────────────────────────
export default function FdicDemo() {
  const [activeTab, setActiveTab]               = useState<FdicTabId>("trace");
  const [selectedScenario, setSelectedScenario] = useState<ScenarioId | null>(null);

  // Platform boot (connectivity check + CSV load + ontology seed)
  const { bootState, isBooting, retryBoot } = usePlatformBoot();

  // Investigation state (SSE-driven)
  const {
    state: invState,
    loading,
    error: invError,
    thoughts,
    startInvestigation,
    reset,
  } = useInvestigation();

  // Control scan (driven whenever selectedScenario changes)
  const {
    result: controlResult,
    loading: controlLoading,
    error: controlError,
  } = useControlScan(selectedScenario);

  // Derived runtime state
  const runtimeState = deriveRuntimeState(
    isBooting,
    bootState.stage === "FAILED",
    invState?.status,
    loading,
  );

  // StatusBar data
  const confirmedHops = invState?.backtrackChain.filter(
    (h) => h.status === "ROOT_CAUSE" || h.status === "CONFIRMED_FAILED",
  ).length ?? 0;
  const totalHops = invState?.backtrackChain.length ?? 0;

  const statusBarProps: StatusBarState = {
    runtimeState,
    scenarioId:        selectedScenario ?? undefined,
    activePhase:       invState?.currentPhase ?? undefined,
    currentHop:        totalHops > 0 ? confirmedHops : undefined,
    totalHops:         totalHops > 0 ? totalHops : undefined,
    confidence:        invState?.confidence?.composite_score
                         ?? invState?.confidence?.composite
                         ?? undefined,
    recordsLoaded:     bootState.recordsLoaded ?? 6006,
    latencyMs:         undefined,
    obsP95Ms:          null,
    obsAlertCount:     0,
    obsSseConnections: 0,
    obsError:          false,
  };

  // Handlers
  const handleSelectScenario = (id: ScenarioId) => {
    if (loading) return;
    if (selectedScenario !== id) reset();
    setSelectedScenario(id);
  };

  const handleRunRca = () => {
    if (!selectedScenario || loading) return;
    const meta = SCENARIO_META.find((m) => m.id === selectedScenario);
    const jobId = meta?.defaultJobId ?? selectedScenario;
    reset();
    startInvestigation(selectedScenario, jobId);
    setActiveTab("trace");
  };

  // Phase pipeline status helper
  const phaseStatus = (phase: PhaseId): "done" | "active" | "pending" => {
    if (!invState) return "pending";
    if (invState.phases[phase]) return "done";
    const order = PHASE_ORDER as readonly string[];
    const curIdx = order.indexOf(invState.currentPhase);
    const pIdx   = order.indexOf(phase);
    if (curIdx > pIdx) return "done";
    if (curIdx === pIdx) return "active";
    return "pending";
  };

  return (
    <>
      <style>{GLOBAL_CSS}</style>

      <div
        style={{
          background: C.bg,
          height: "100vh",
          display: "flex",
          flexDirection: "column",
          fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
          color: C.text,
          overflow: "hidden",
        }}
      >
        {/* Boot overlay — covers everything while booting / on failure */}
        {(isBooting || bootState.stage === "FAILED") && (
          <BootScreen bootState={bootState} onRetry={retryBoot} />
        )}

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <header
          style={{
            background: C.surface,
            borderBottom: `1px solid ${C.borderDim}`,
            height: 44,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 20px",
            flexShrink: 0,
            zIndex: 10,
          }}
        >
          {/* Left: branding + active scenario chip */}
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <span
              style={{
                color: C.accent,
                fontWeight: 800,
                fontSize: 14,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
              }}
            >
              KRATOS
            </span>

            <span style={{ color: C.borderDim, fontSize: 18, lineHeight: 1 }}>|</span>

            <span style={{ color: C.textSub, fontSize: 12 }}>
              CauseLink FDIC Part 370/330 Demo
            </span>

            {invState?.scenarioId && (
              <>
                <span style={{ color: C.borderDim, fontSize: 18, lineHeight: 1 }}>|</span>
                <span
                  style={{
                    color: C.textMuted,
                    fontSize: 10,
                    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                    background: C.elevated,
                    padding: "2px 8px",
                    borderRadius: 4,
                    border: `1px solid ${C.border}`,
                    letterSpacing: "0.04em",
                  }}
                >
                  {invState.scenarioId}
                </span>
              </>
            )}
          </div>

          {/* Right: synthetic-data badge + reset button */}
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span
              style={{
                background: C.greenBg,
                color: C.green,
                border: `1px solid ${C.greenBorder}`,
                borderRadius: 4,
                padding: "2px 8px",
                fontSize: 9,
                fontWeight: 700,
                letterSpacing: "0.07em",
                textTransform: "uppercase",
              }}
            >
              Synthetic Data — Not for Production Use
            </span>

            {invState && !loading && (
              <button
                onClick={reset}
                style={{
                  background: "none",
                  border: `1px solid ${C.border}`,
                  borderRadius: 4,
                  color: C.textSub,
                  fontSize: 11,
                  padding: "3px 10px",
                  cursor: "pointer",
                }}
              >
                Reset
              </button>
            )}
          </div>
        </header>

        {/* ── Phase pipeline ───────────────────────────────────────────────── */}
        <div
          aria-label="Investigation phases"
          style={{
            background: C.surface,
            borderBottom: `1px solid ${C.borderDim}`,
            height: 52,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "0 20px",
            gap: 0,
            flexShrink: 0,
          }}
        >
          {(PHASE_ORDER as readonly PhaseId[]).map((phase, idx) => {
            const st       = phaseStatus(phase);
            const isDone   = st === "done";
            const isActive = st === "active";
            const isLast   = idx === PHASE_ORDER.length - 1;

            return (
              <React.Fragment key={phase}>
                {/* Phase pill */}
                <div
                  className={isActive ? "fdic-phase-active" : undefined}
                  aria-current={isActive ? "step" : undefined}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    background: isDone
                      ? C.greenBg
                      : isActive
                      ? C.accentBg
                      : C.elevated,
                    border: `1px solid ${
                      isDone
                        ? C.greenBorder
                        : isActive
                        ? C.accentMid
                        : C.border
                    }`,
                    borderRadius: 20,
                    padding: "4px 14px",
                    transition: "background 0.3s, border-color 0.3s",
                    whiteSpace: "nowrap",
                  }}
                >
                  {/* Status dot */}
                  <span
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      background: isDone
                        ? C.green
                        : isActive
                        ? C.accent
                        : C.textMuted,
                      flexShrink: 0,
                    }}
                  />
                  {/* Label */}
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: isDone || isActive ? 600 : 400,
                      color: isDone
                        ? C.green
                        : isActive
                        ? "#a5b4fc"   // indigo-300
                        : C.textMuted,
                      letterSpacing: "0.02em",
                    }}
                  >
                    {PHASE_LABELS[phase]}
                  </span>
                </div>

                {/* Connector line between pills */}
                {!isLast && (
                  <div
                    style={{
                      width: 18,
                      height: 1,
                      background: isDone ? C.green : C.border,
                      transition: "background 0.3s",
                      flexShrink: 0,
                    }}
                  />
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* ── Main body: sidebar + tab content ─────────────────────────────── */}
        <div
          style={{
            display: "flex",
            flex: 1,
            minHeight: 0,
            // Leave 36px gap at the bottom for the fixed StatusBar
            paddingBottom: 36,
            boxSizing: "border-box",
          }}
        >
          {/* ── Left sidebar: scenario cards ─────────────────────────────── */}
          <aside
            style={{
              width: 240,
              flexShrink: 0,
              borderRight: `1px solid ${C.borderDim}`,
              display: "flex",
              flexDirection: "column",
              padding: "14px 10px 14px 10px",
              gap: 8,
              overflowY: "auto",
              background: C.surface,
            }}
          >
            {/* Section label */}
            <div
              style={{
                color: C.textMuted,
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                marginBottom: 2,
                paddingLeft: 2,
              }}
            >
              Select Scenario
            </div>

            {/* Scenario cards */}
            {SCENARIO_META.map((meta) => {
              const palette   = SCENARIO_PALETTE[meta.color] ?? SCENARIO_PALETTE.red;
              const isSelected = selectedScenario === meta.id;

              return (
                <button
                  key={meta.id}
                  className="fdic-card"
                  onClick={() => handleSelectScenario(meta.id as ScenarioId)}
                  disabled={loading}
                  style={{
                    background: isSelected ? palette.bg : C.elevated,
                    border: `1px solid ${
                      isSelected ? palette.border : C.border
                    }`,
                    borderRadius: 8,
                    padding: "10px 12px",
                    textAlign: "left",
                    cursor: loading ? "not-allowed" : "pointer",
                    opacity: loading && !isSelected ? 0.55 : 1,
                    transition: "background 0.2s, border-color 0.2s, opacity 0.2s",
                  }}
                >
                  {/* Top row: severity badge + defect ID */}
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: 7,
                    }}
                  >
                    <span
                      style={{
                        background: palette.bg,
                        color: palette.main,
                        border: `1px solid ${palette.border}`,
                        borderRadius: 3,
                        padding: "1px 6px",
                        fontSize: 9,
                        fontWeight: 700,
                        letterSpacing: "0.07em",
                        textTransform: "uppercase",
                      }}
                    >
                      {meta.severity}
                    </span>
                    <span
                      style={{
                        color: C.textMuted,
                        fontSize: 9,
                        fontFamily: "'JetBrains Mono', monospace",
                      }}
                    >
                      {meta.defectId}
                    </span>
                  </div>

                  {/* Title */}
                  <div
                    style={{
                      color: isSelected ? C.text : C.textSub,
                      fontSize: 12,
                      fontWeight: 600,
                      marginBottom: 4,
                      lineHeight: 1.35,
                    }}
                  >
                    {meta.title}
                  </div>

                  {/* Subtitle (financial impact) */}
                  <div
                    style={{
                      color: C.textMuted,
                      fontSize: 11,
                      lineHeight: 1.4,
                      marginBottom: 8,
                    }}
                  >
                    {meta.subtitle}
                  </div>

                  {/* Control failed */}
                  <div
                    style={{
                      color: C.textMuted,
                      fontSize: 10,
                      fontFamily: "'JetBrains Mono', monospace",
                      borderTop: `1px solid ${C.borderDim}`,
                      paddingTop: 6,
                    }}
                  >
                    {meta.controlFailed}
                  </div>
                </button>
              );
            })}

            {/* Spacer */}
            <div style={{ flex: 1, minHeight: 8 }} />

            {/* Active job ID display */}
            {selectedScenario && (
              <div
                style={{
                  background: C.elevated,
                  border: `1px solid ${C.border}`,
                  borderRadius: 6,
                  padding: "8px 10px",
                }}
              >
                <div
                  style={{
                    color: C.textMuted,
                    fontSize: 9,
                    fontWeight: 600,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    marginBottom: 4,
                  }}
                >
                  Job ID
                </div>
                <div
                  style={{
                    color: C.textSub,
                    fontSize: 10,
                    fontFamily: "'JetBrains Mono', monospace",
                    wordBreak: "break-all",
                    lineHeight: 1.4,
                  }}
                >
                  {SCENARIO_META.find((m) => m.id === selectedScenario)
                    ?.defaultJobId ?? "—"}
                </div>
              </div>
            )}

            {/* Run button */}
            <button
              onClick={handleRunRca}
              disabled={!selectedScenario || loading}
              style={{
                background:
                  selectedScenario && !loading ? C.accent : C.elevated,
                border: `1px solid ${
                  selectedScenario && !loading ? C.accent : C.border
                }`,
                borderRadius: 6,
                color:
                  selectedScenario && !loading ? "#ffffff" : C.textMuted,
                fontSize: 13,
                fontWeight: 600,
                padding: "10px 0",
                cursor:
                  !selectedScenario || loading ? "not-allowed" : "pointer",
                transition: "background 0.2s, border-color 0.2s",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
              }}
            >
              {loading ? (
                <>
                  <span
                    style={{
                      width: 12,
                      height: 12,
                      border: "2px solid rgba(255,255,255,0.25)",
                      borderTopColor: "#ffffff",
                      borderRadius: "50%",
                      animation: "fdic-spin 0.75s linear infinite",
                      display: "inline-block",
                      flexShrink: 0,
                    }}
                  />
                  Analyzing...
                </>
              ) : (
                "Run RCA Analysis"
              )}
            </button>
          </aside>

          {/* ── Right: tab bar + content ──────────────────────────────────── */}
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              minWidth: 0,
              background: C.bg,
            }}
          >
            {/* Error banner */}
            {invError && (
              <div
                role="alert"
                style={{
                  background: C.redBg,
                  borderBottom: `1px solid ${C.redBorder}`,
                  padding: "8px 16px",
                  color: "#fca5a5",  // red-300
                  fontSize: 12,
                  flexShrink: 0,
                }}
              >
                Investigation error: {invError}
              </div>
            )}

            {/* Tab bar */}
            <div
              role="tablist"
              aria-label="Investigation results"
              style={{
                display: "flex",
                borderBottom: `1px solid ${C.borderDim}`,
                background: C.surface,
                padding: "0 16px",
                flexShrink: 0,
                overflowX: "auto",
              }}
            >
              {TABS.map((tab) => {
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    role="tab"
                    aria-selected={isActive}
                    className="fdic-tab"
                    onClick={() => setActiveTab(tab.id)}
                    style={{
                      background: "none",
                      border: "none",
                      borderBottom: `2px solid ${
                        isActive ? C.accent : "transparent"
                      }`,
                      color: isActive ? C.text : C.textMuted,
                      fontSize: 12,
                      fontWeight: isActive ? 600 : 400,
                      padding: "10px 14px",
                      cursor: "pointer",
                      transition: "color 0.15s, border-color 0.15s",
                      whiteSpace: "nowrap",
                      flexShrink: 0,
                    }}
                  >
                    {tab.label}
                  </button>
                );
              })}
            </div>

            {/* Tab content panels */}
            <div
              role="tabpanel"
              style={{ flex: 1, overflowY: "auto", minHeight: 0 }}
            >
              {activeTab === "trace" && (
                <div style={{ padding: 16 }}>
                  <RcaTracePanel result={null} />
                </div>
              )}

              {activeTab === "controls" && (
                <div style={{ padding: 16 }}>
                  <ControlScanPanel controls={[]} loading={controlLoading} />
                </div>
              )}

              {activeTab === "incident" && (
                <div style={{ padding: 16 }}>
                  <IncidentCardPanel incident={invState?.incidentCard ?? null} />
                </div>
              )}

              {activeTab === "recommendations" && (
                <div style={{ padding: 16 }}>
                  <RecommendationList
                    recommendations={invState?.recommendations ?? []}
                  />
                </div>
              )}

              {activeTab === "confidence" && (
                <div style={{ padding: 16 }}>
                  <ConfidenceGauge confidence={null} />
                </div>
              )}

              {activeTab === "data" && (
                <SampleDataTable scenarioId={selectedScenario} />
              )}
            </div>
          </div>
        </div>

        {/* ── Status bar — position:fixed, always visible ───────────────── */}
        <StatusBar {...statusBarProps} />
      </div>
    </>
  );
}
