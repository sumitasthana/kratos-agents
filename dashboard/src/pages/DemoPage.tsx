/**
 * DemoPage.tsx
 *
 * Full demo layout with BOOT/IDLE/RUNNING/CONFIRMED/ERROR runtime states.
 *
 * Layout (height = 100vh - 36px StatusBar):
 *   
 *     Header                                              
 *   
 *     PhasePipeline (7 pills)                             
 *   
 *     ScenarioSelect   TabPanel                          
 *     (220px)          [trace|controls|incident|recs     
 *                       |confidence|data]                
 *   
 *     StatusBar (fixed bottom 36px)                       
 *   
 */

import React, { useState } from "react";

import BootScreen        from "../components/BootScreen";
import StatusBar         from "../components/StatusBar";
import PhasePipeline     from "../components/PhasePipeline";
import TabPanel          from "../components/TabPanel";
import type { TabId }    from "../components/TabPanel";
import ScenarioSelector  from "../components/ScenarioSelector";
import { ControlScanPanel }  from "../components/ControlScanPanel";
import { RcaTracePanel }     from "../components/RcaTracePanel";
import IncidentCard      from "../components/IncidentCard";
import RecommendationList from "../components/RecommendationList";
import { ConfidenceGauge }   from "../components/ConfidenceGauge";
import SampleDataTable   from "../components/SampleDataTable";
import ObservabilityPanel from "../components/ObservabilityPanel";
import { ReasoningStream }    from "../components/ReasoningStream";
import { EnvironmentSelector } from "../components/EnvironmentSelector";

import { usePlatformBoot }   from "../hooks/usePlatformBoot";
import { useInvestigation }  from "../hooks/useInvestigation";
import { useControlScan }    from "../hooks/useControlScan";
import { useMetrics }        from "../hooks/useMetrics";
import { useAlerts }         from "../hooks/useAlerts";

import type { RuntimeState, StatusBarState, ScenarioId } from "../types/demo";
import type { PhaseId } from "../types/causelink";

//  Runtime state derivation 

function deriveRuntimeState(
  isBooting: boolean,
  bootFailed: boolean,
  status: string | undefined,
  loading: boolean
): RuntimeState {
  if (isBooting)   return "BOOT";
  if (bootFailed)  return "ERROR";
  if (loading || status === "RUNNING") return "RUNNING";
  if (status === "CONFIRMED") return "CONFIRMED";
  if (status === "FAILED" || status === "ERROR") return "ERROR";
  return "IDLE";
}

//  Main page 

export default function DemoPage() {
  const [activeTab,      setActiveTab]      = useState<TabId>("trace");
  const [selectedPhase,  setSelectedPhase]  = useState<PhaseId | null>(null);
  const [selectedScenario, setSelectedScenario] = useState<ScenarioId | null>(null);
  const [selectedAdapter,  setSelectedAdapter]  = useState<string>("kratos_demo");

  // Boot sequence
  const { bootState, isBooting, retryBoot } = usePlatformBoot();

  // Investigation state
  const { state: invState, loading: invLoading, error: invError, thoughts, startInvestigation, reset } =
    useInvestigation();

  // Control scan (driven from parent so ControlScanPanel has no own state)
  const { result: controlResult, loading: controlLoading, error: controlError } =
    useControlScan(selectedScenario);

  // Observability hooks — soft dependency on /obs API
  const { metrics, error: metricsError } = useMetrics();
  const { alerts } = useAlerts();

  // Derive runtime state
  const runtimeState = deriveRuntimeState(
    isBooting,
    bootState.stage === "FAILED",
    invState?.status,
    invLoading
  );

  // Assemble StatusBar state
  const confirmedHops = invState?.backtrackChain?.filter((h) => h.status === "ROOT_CAUSE" || h.status === "CONFIRMED_FAILED").length ?? 0;
  const totalHops = invState?.backtrackChain?.length ?? 0;

  const statusBar: StatusBarState = {
    runtimeState,
    scenarioId: selectedScenario ?? undefined,
    activePhase: invState?.currentPhase ?? selectedPhase ?? undefined,
    currentHop: totalHops > 0 ? confirmedHops : undefined,
    totalHops:  totalHops > 0 ? totalHops : undefined,
    confidence: invState?.confidence?.composite_score ??
                invState?.confidence?.composite_score ??
                undefined,
    recordsLoaded: bootState.recordsLoaded ?? 6006,
    latencyMs: undefined,
    obsP95Ms: metrics?.performance.phase_p95_ms ?? null,
    obsAlertCount: alerts.length,
    obsSseConnections: metrics?.sse.active_connections ?? 0,
    obsError: !!metricsError,
  };

  const handleStart = (scenarioId: ScenarioId, jobId: string) => {
    setSelectedScenario(scenarioId);
    reset();
    startInvestigation(scenarioId, jobId);
    setActiveTab("trace");
  };

  const handlePhaseClick = (phase: PhaseId) => {
    setSelectedPhase(phase);
  };

  return (
    <div
      style={{
        background: "#090b10",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
        color: "#e2e8f0",
        overflow: "hidden",
      }}
    >
      {/* Boot overlay  position: fixed, only this can do that */}
      {(isBooting || bootState.stage === "FAILED") && (
        <BootScreen bootState={bootState} onRetry={retryBoot} />
      )}

      {/* Header */}
      <div
        style={{
          background: "#0a0c10",
          borderBottom: "1px solid #1f2937",
          padding: "0 20px",
          height: 44,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexShrink: 0,
          zIndex: 10,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ color: "#3b82f6", fontWeight: 800, fontSize: 13, letterSpacing: "0.12em" }}>
            KRATOS
          </span>
          <span style={{ color: "#1f2937" }}>|</span>
          <span style={{ color: "#64748b", fontSize: 12 }}>CauseLink RCA Demo</span>
          {invState?.scenarioId && (
            <>
              <span style={{ color: "#1f2937" }}>|</span>
              <span style={{ color: "#94a3b8", fontSize: 11, fontFamily: "monospace" }}>
                {invState.scenarioId}
              </span>
            </>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span
            style={{
              background: "#051c0a",
              color: "#4ade80",
              border: "1px solid #166534",
              borderRadius: 4,
              padding: "2px 8px",
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "0.05em",
            }}
          >
            SYNTHETIC DATA  NOT FOR PRODUCTION USE
          </span>
          <EnvironmentSelector
            selectedId={selectedAdapter}
            onChange={setSelectedAdapter}
            disabled={invLoading}
          />
          {invState && (
            <button
              onClick={reset}
              style={{
                background: "none",
                border: "1px solid #1f2937",
                borderRadius: 4,
                color: "#6b7280",
                fontSize: 11,
                padding: "3px 10px",
                cursor: "pointer",
              }}
            >
              Reset
            </button>
          )}
        </div>
      </div>

      {/* Phase pipeline */}
      <PhasePipeline
        phases={invState?.phases ?? {}}
        currentPhase={invState?.currentPhase ?? null}
        runtimeState={runtimeState}
        onPhaseClick={handlePhaseClick}
      />

      {/* Main body: sidebar + content */}
      <div
        style={{
          display: "flex",
          flex: 1,
          minHeight: 0,
          // Reserve 36px for StatusBar
          height: "calc(100vh - 44px - 52px - 36px)",
        }}
      >
        {/* Left sidebar: 220px */}
        <div
          style={{
            width: 220,
            flexShrink: 0,
            borderRight: "1px solid #1f2937",
            display: "flex",
            flexDirection: "column",
            overflowY: "auto",
          }}
        >
          <div style={{ padding: 12 }}>
            <ScenarioSelector
              onStart={handleStart}
              disabled={invLoading}
              runtimeState={runtimeState}
            />
          </div>
        </div>

        {/* Right content: tabs */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {/* Error banner */}
          {invError && (
            <div
              style={{
                background: "#1c0808",
                border: "1px solid #7f1d1d",
                borderRadius: 0,
                padding: "8px 16px",
                color: "#fca5a5",
                fontSize: 12,
                flexShrink: 0,
              }}
            >
              Error: {invError}
            </div>
          )}

          <TabPanel
            activeTab={activeTab}
            onTabChange={setActiveTab}
            runtimeState={runtimeState}
          >
            {/* trace */}
            <div style={{ padding: 16 }}>
              <RcaTracePanel result={null} />
            </div>

            {/* controls */}
            <div style={{ padding: 16 }}>
              <ControlScanPanel controls={[]} loading={controlLoading} />
            </div>

            {/* incident */}
            <div style={{ padding: 16 }}>
              <IncidentCard incident={invState?.incidentCard ?? null} />
            </div>

            {/* recommendations */}
            <div style={{ padding: 16 }}>
              <RecommendationList recommendations={invState?.recommendations ?? []} />
            </div>

            {/* confidence */}
            <div style={{ padding: 16 }}>
              <ConfidenceGauge confidence={null} />
            </div>

            {/* data */}
            <SampleDataTable scenarioId={selectedScenario} />

            {/* observability */}
            <ObservabilityPanel activeInvestigationId={invState?.investigationId ?? null} />

            {/* reasoning */}
            <div style={{ padding: 16, height: "100%", boxSizing: "border-box" }}>
              <ReasoningStream
                thoughts={thoughts}
                isRunning={invLoading}
              />
            </div>
          </TabPanel>
        </div>
      </div>

      {/* Status bar  always visible, never conditional */}
      <StatusBar {...statusBar} />
    </div>
  );
}
