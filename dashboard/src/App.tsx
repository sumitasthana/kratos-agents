import React, { useEffect, useMemo, useState } from "react";
import { fetchLatest, fetchRun, fetchRuns, RunManifest } from "./api";
import LineageGraph from "./LineageGraph";
import GitDataflowGraph from "./GitDataflowGraph";
import RCAFindings from "./RCAFindings";

type TabType = "overview" | "rca" | "git" | "lineage";

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "8px 16px",
        border: "none",
        borderBottom: active ? "2px solid #4a90e2" : "2px solid transparent",
        background: active ? "#f0f6ff" : "transparent",
        color: active ? "#4a90e2" : "#666",
        fontWeight: active ? 700 : 400,
        cursor: "pointer",
        fontSize: 14,
      }}
    >
      {children}
    </button>
  );
}

export default function App() {
  const [runs, setRuns] = useState<RunManifest[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<RunManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>("overview");
  const [artifactData, setArtifactData] = useState<Record<string, any>>({});
  const [loadingRuns, setLoadingRuns] = useState<boolean>(true);

  const selectedArtifacts = useMemo(() => {
    return selectedRun?.artifacts ?? {};
  }, [selectedRun]);

  useEffect(() => {
    (async () => {
      try {
        setLoadingRuns(true);
        const allRuns = await fetchRuns();
        setRuns(allRuns);

        const latest = await fetchLatest();
        if (latest?.run_id) {
          setSelectedRunId(latest.run_id);
        } else if (allRuns.length > 0) {
          setSelectedRunId(allRuns[0].run_id);
        }
      } catch (e: any) {
        setError(e?.message ?? String(e));
      } finally {
        setLoadingRuns(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRun(null);
      return;
    }

    (async () => {
      try {
        setError(null);
        const r = await fetchRun(selectedRunId);
        setSelectedRun(r);
        
        // Load artifact data
        const data: Record<string, any> = {};
        for (const [key, path] of Object.entries(r.artifacts || {})) {
          if (path) {
            try {
              const res = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
              if (res.ok) {
                data[key] = await res.json();
              }
            } catch {
              // ignore
            }
          }
        }
        setArtifactData(data);
        
        // Auto-select appropriate tab
        if (r.command === "orchestrate") setActiveTab("rca");
        else if (r.command === "git-dataflow") setActiveTab("git");
        else if (r.command === "lineage-extract") setActiveTab("lineage");
        else setActiveTab("overview");
      } catch (e: any) {
        setError(e?.message ?? String(e));
      }
    })();
  }, [selectedRunId]);

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "Segoe UI, Arial, sans-serif" }}>
      <div style={{ width: 360, borderRight: "1px solid #e5e5e5", padding: 12, overflow: "auto" }}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>Kratos Dashboard</div>
        <div style={{ fontSize: 12, color: "#666", marginBottom: 12 }}>
          Local viewer for agent outputs under <code>runs/</code>
        </div>

        {error ? (
          <div style={{ color: "#b00020", fontSize: 12, marginBottom: 12 }}>{error}</div>
        ) : null}

        <div style={{ fontWeight: 600, marginBottom: 8 }}>Runs</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {loadingRuns ? <div style={{ fontSize: 12, color: "#666" }}>Loading runs...</div> : null}
          {runs.map((r) => (
            <button
              key={r.run_id}
              onClick={() => setSelectedRunId(r.run_id)}
              style={{
                textAlign: "left",
                padding: "8px 10px",
                border: "1px solid #ddd",
                borderRadius: 6,
                background: r.run_id === selectedRunId ? "#f0f6ff" : "white",
                cursor: "pointer",
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 700 }}>{r.command}</div>
              <div style={{ fontSize: 11, color: "#555" }}>{r.run_id}</div>
              <div style={{ fontSize: 11, color: "#777" }}>{r.created_at}</div>
            </button>
          ))}
          {runs.length === 0 ? <div style={{ fontSize: 12, color: "#666" }}>No runs found.</div> : null}
        </div>
      </div>

      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {selectedRun ? (
          <>
            <div style={{ padding: 16, borderBottom: "1px solid #e5e5e5" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 800 }}>{selectedRun.command}</div>
                  <div style={{ fontSize: 12, color: "#666" }}>{selectedRun.run_id}</div>
                </div>
                <div style={{ fontSize: 12, color: "#666" }}>{selectedRun.created_at}</div>
              </div>

              <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                <TabButton active={activeTab === "overview"} onClick={() => setActiveTab("overview")}>
                  Overview
                </TabButton>
                {(selectedRun.command === "orchestrate" || artifactData.orchestrator_json) && (
                  <TabButton active={activeTab === "rca"} onClick={() => setActiveTab("rca")}>
                    RCA Findings
                  </TabButton>
                )}
                {(selectedRun.command === "git-dataflow" || artifactData.git_dataflow_json) && (
                  <TabButton active={activeTab === "git"} onClick={() => setActiveTab("git")}>
                    Git Dataflow
                  </TabButton>
                )}
                {(selectedRun.command === "lineage-extract" || artifactData.lineage_json) && (
                  <TabButton active={activeTab === "lineage"} onClick={() => setActiveTab("lineage")}>
                    Lineage Map
                  </TabButton>
                )}
              </div>
            </div>

            <div style={{ flex: 1, overflow: "hidden", minHeight: 0 }}>
              {activeTab === "overview" && (
                <div style={{ padding: 16, height: "100%", overflow: "auto" }}>
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontWeight: 700, marginBottom: 4 }}>Highlights</div>
                    <div style={{ fontSize: 14, color: "#333" }}>
                      {(selectedRun.summary?.highlights ?? []).length > 0
                        ? selectedRun.summary!.highlights!.map((h, idx) => <div key={idx}>• {h}</div>)
                        : "(none)"}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontWeight: 700, marginBottom: 4 }}>Artifacts</div>
                    <div style={{ fontSize: 14, color: "#333" }}>
                      {Object.keys(selectedArtifacts).length > 0 ? (
                        Object.entries(selectedArtifacts).map(([k, v]) => (
                          <div key={k}>
                            <span style={{ fontWeight: 700 }}>{k}:</span>{" "}
                            {v ? (
                              <a href={`/api/file?path=${encodeURIComponent(v)}`} target="_blank" rel="noreferrer">
                                {v}
                              </a>
                            ) : (
                              <span style={{ color: "#777" }}>(none)</span>
                            )}
                          </div>
                        ))
                      ) : (
                        <div style={{ color: "#777" }}>(none)</div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {activeTab === "rca" && (
                <div style={{ height: "100%", overflow: "auto" }}>
                  <RCAFindings orchestratorData={artifactData.orchestrator_json} />
                </div>
              )}

              {activeTab === "git" && (
                <div style={{ height: "100%", minHeight: 600 }}>
                  <GitDataflowGraph dataflowData={artifactData.git_dataflow_json} />
                </div>
              )}

              {activeTab === "lineage" && (
                <div style={{ height: "100%", minHeight: 600 }}>
                  <LineageGraph lineageData={artifactData.lineage_json} />
                </div>
              )}
            </div>
          </>
        ) : (
          <div style={{ padding: 16, color: "#666" }}>Select a run from the left.</div>
        )}
      </div>
    </div>
  );
}
