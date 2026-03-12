// import React, { useEffect, useMemo, useState } from "react";
// import { fetchLatest, fetchRun, fetchRuns, RunManifest } from "./api";
// import LineageGraph from "./LineageGraph";
// import GitDataflowGraph from "./GitDataflowGraph";
// import RCAFindings from "./RCAFindings";

// type TabType = "overview" | "rca" | "git" | "lineage";

// function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
//   return (
//     <button
//       onClick={onClick}
//       style={{
//         padding: "8px 16px",
//         border: "none",
//         borderBottom: active ? "2px solid #4a90e2" : "2px solid transparent",
//         background: active ? "#f0f6ff" : "transparent",
//         color: active ? "#4a90e2" : "#666",
//         fontWeight: active ? 700 : 400,
//         cursor: "pointer",
//         fontSize: 14,
//       }}
//     >
//       {children}
//     </button>
//   );
// }

// export default function App() {
//   const [runs, setRuns] = useState<RunManifest[]>([]);
//   const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
//   const [selectedRun, setSelectedRun] = useState<RunManifest | null>(null);
//   const [error, setError] = useState<string | null>(null);
//   const [activeTab, setActiveTab] = useState<TabType>("overview");
//   const [artifactData, setArtifactData] = useState<Record<string, any>>({});
//   const [loadingRuns, setLoadingRuns] = useState<boolean>(true);

//   const selectedArtifacts = useMemo(() => {
//     return selectedRun?.artifacts ?? {};
//   }, [selectedRun]);

//   useEffect(() => {
//     (async () => {
//       try {
//         setLoadingRuns(true);
//         const allRuns = await fetchRuns();
//         setRuns(allRuns);

//         const latest = await fetchLatest();
//         if (latest?.run_id) {
//           setSelectedRunId(latest.run_id);
//         } else if (allRuns.length > 0) {
//           setSelectedRunId(allRuns[0].run_id);
//         }
//       } catch (e: any) {
//         setError(e?.message ?? String(e));
//       } finally {
//         setLoadingRuns(false);
//       }
//     })();
//   }, []);

//   useEffect(() => {
//     if (!selectedRunId) {
//       setSelectedRun(null);
//       return;
//     }

//     (async () => {
//       try {
//         setError(null);
//         const r = await fetchRun(selectedRunId);
//         setSelectedRun(r);
        
//         // Load artifact data
//         const data: Record<string, any> = {};
//         for (const [key, path] of Object.entries(r.artifacts || {})) {
//           if (path) {
//             try {
//               const res = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
//               if (res.ok) {
//                 data[key] = await res.json();
//               }
//             } catch {
//               // ignore
//             }
//           }
//         }
//         setArtifactData(data);
        
//         // Auto-select appropriate tab
//         if (r.command === "orchestrate") setActiveTab("rca");
//         else if (r.command === "git-dataflow") setActiveTab("git");
//         else if (r.command === "lineage-extract") setActiveTab("lineage");
//         else setActiveTab("overview");
//       } catch (e: any) {
//         setError(e?.message ?? String(e));
//       }
//     })();
//   }, [selectedRunId]);

//   return (
//     <div style={{ display: "flex", height: "100vh", fontFamily: "Segoe UI, Arial, sans-serif" }}>
//       <div style={{ width: 360, borderRight: "1px solid #e5e5e5", padding: 12, overflow: "auto" }}>
//         <div style={{ fontWeight: 700, marginBottom: 8 }}>Kratos Dashboard</div>
//         <div style={{ fontSize: 12, color: "#666", marginBottom: 12 }}>
//           Local viewer for agent outputs under <code>runs/</code>
//         </div>

//         {error ? (
//           <div style={{ color: "#b00020", fontSize: 12, marginBottom: 12 }}>{error}</div>
//         ) : null}

//         <div style={{ fontWeight: 600, marginBottom: 8 }}>Runs</div>
//         <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
//           {loadingRuns ? <div style={{ fontSize: 12, color: "#666" }}>Loading runs...</div> : null}
//           {runs.map((r) => (
//             <button
//               key={r.run_id}
//               onClick={() => setSelectedRunId(r.run_id)}
//               style={{
//                 textAlign: "left",
//                 padding: "8px 10px",
//                 border: "1px solid #ddd",
//                 borderRadius: 6,
//                 background: r.run_id === selectedRunId ? "#f0f6ff" : "white",
//                 cursor: "pointer",
//               }}
//             >
//               <div style={{ fontSize: 12, fontWeight: 700 }}>{r.command}</div>
//               <div style={{ fontSize: 11, color: "#555" }}>{r.run_id}</div>
//               <div style={{ fontSize: 11, color: "#777" }}>{r.created_at}</div>
//             </button>
//           ))}
//           {runs.length === 0 ? <div style={{ fontSize: 12, color: "#666" }}>No runs found.</div> : null}
//         </div>
//       </div>

//       <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
//         {selectedRun ? (
//           <>
//             <div style={{ padding: 16, borderBottom: "1px solid #e5e5e5" }}>
//               <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
//                 <div>
//                   <div style={{ fontSize: 18, fontWeight: 800 }}>{selectedRun.command}</div>
//                   <div style={{ fontSize: 12, color: "#666" }}>{selectedRun.run_id}</div>
//                 </div>
//                 <div style={{ fontSize: 12, color: "#666" }}>{selectedRun.created_at}</div>
//               </div>

//               <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
//                 <TabButton active={activeTab === "overview"} onClick={() => setActiveTab("overview")}>
//                   Overview
//                 </TabButton>
//                 {(selectedRun.command === "orchestrate" || artifactData.orchestrator_json) && (
//                   <TabButton active={activeTab === "rca"} onClick={() => setActiveTab("rca")}>
//                     RCA Findings
//                   </TabButton>
//                 )}
//                 {(selectedRun.command === "git-dataflow" || artifactData.git_dataflow_json) && (
//                   <TabButton active={activeTab === "git"} onClick={() => setActiveTab("git")}>
//                     Git Dataflow
//                   </TabButton>
//                 )}
//                 {(selectedRun.command === "lineage-extract" || artifactData.lineage_json) && (
//                   <TabButton active={activeTab === "lineage"} onClick={() => setActiveTab("lineage")}>
//                     Lineage Map
//                   </TabButton>
//                 )}
//               </div>
//             </div>

//             <div style={{ flex: 1, overflow: "hidden", minHeight: 0 }}>
//               {activeTab === "overview" && (
//                 <div style={{ padding: 16, height: "100%", overflow: "auto" }}>
//                   <div style={{ marginBottom: 16 }}>
//                     <div style={{ fontWeight: 700, marginBottom: 4 }}>Highlights</div>
//                     <div style={{ fontSize: 14, color: "#333" }}>
//                       {(selectedRun.summary?.highlights ?? []).length > 0
//                         ? selectedRun.summary!.highlights!.map((h, idx) => <div key={idx}>• {h}</div>)
//                         : "(none)"}
//                     </div>
//                   </div>

//                   <div>
//                     <div style={{ fontWeight: 700, marginBottom: 4 }}>Artifacts</div>
//                     <div style={{ fontSize: 14, color: "#333" }}>
//                       {Object.keys(selectedArtifacts).length > 0 ? (
//                         Object.entries(selectedArtifacts).map(([k, v]) => (
//                           <div key={k}>
//                             <span style={{ fontWeight: 700 }}>{k}:</span>{" "}
//                             {v ? (
//                               <a href={`/api/file?path=${encodeURIComponent(v)}`} target="_blank" rel="noreferrer">
//                                 {v}
//                               </a>
//                             ) : (
//                               <span style={{ color: "#777" }}>(none)</span>
//                             )}
//                           </div>
//                         ))
//                       ) : (
//                         <div style={{ color: "#777" }}>(none)</div>
//                       )}
//                     </div>
//                   </div>
//                 </div>
//               )}

//               {activeTab === "rca" && (
//                 <div style={{ height: "100%", overflow: "auto" }}>
//                   <RCAFindings orchestratorData={artifactData.orchestrator_json} />
//                 </div>
//               )}

//               {activeTab === "git" && (
//                 <div style={{ height: "100%", minHeight: 600 }}>
//                   <GitDataflowGraph dataflowData={artifactData.git_dataflow_json} />
//                 </div>
//               )}

//               {activeTab === "lineage" && (
//                 <div style={{ height: "100%", minHeight: 600 }}>
//                   <LineageGraph lineageData={artifactData.lineage_json} />
//                 </div>
//               )}
//             </div>
//           </>
//         ) : (
//           <div style={{ padding: 16, color: "#666" }}>Select a run from the left.</div>
//         )}
//       </div>
//     </div>
//   );
// }
import React, { useEffect, useMemo, useState } from "react";
import { fetchLatest, fetchRun, fetchRuns, RunManifest } from "./api";
import LineageGraph from "./LineageGraph";
import GitDataflowGraph from "./GitDataflowGraph";
import RCAFindings from "./RCAFindings";
import DemoRCA from "./DemoRCA";
import RCAWorkspace from "./RCAWorkspace";
import JobDashboard from "./JobDashboard";

// ── Simple hash-based page router ─────────────────────────────────────
function useHash() {
  const [hash, setHash] = useState(() => window.location.hash || "#runs");
  useEffect(() => {
    const onHash = () => setHash(window.location.hash || "#runs");
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return hash;
}

type TabType = "overview" | "rca" | "git" | "lineage";

// ── Helpers ───────────────────────────────────────────────────────────────────

function relativeTime(isoString: string): string {
  try {
    const diff = Date.now() - new Date(isoString).getTime();
    const mins  = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days  = Math.floor(diff / 86400000);
    if (mins  <  1) return "just now";
    if (mins  < 60) return `${mins}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${days}d ago`;
  } catch {
    return isoString;
  }
}

function commandMeta(cmd: string): { color: string; bg: string; icon: string } {
  switch (cmd) {
    case "orchestrate":     return { color: "#f59e0b", bg: "#1c1007", icon: "" };
    case "git-dataflow":    return { color: "#3b82f6", bg: "#0c1a2e", icon: "" };
    case "lineage-extract": return { color: "#22c55e", bg: "#071811", icon: "" };
    default:                return { color: "#9ca3af", bg: "#161b25", icon: "" };
  }
}

// ── Tab Button ────────────────────────────────────────────────────────────────

function TabButton({
  active, onClick, children,
}: {
  active: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "8px 18px",
        border: "none",
        borderBottom: active ? "2px solid #4a90e2" : "2px solid transparent",
        background: "transparent",
        color: active ? "#4a90e2" : "#666",
        fontWeight: active ? 700 : 400,
        cursor: "pointer",
        fontSize: 13,
        transition: "color 0.15s",
      }}
    >
      {children}
    </button>
  );
}

// ── Sidebar Run Card ──────────────────────────────────────────────────────────

function RunCard({
  run, selected, onClick,
}: {
  run: RunManifest; selected: boolean; onClick: () => void;
}) {
  const meta = commandMeta(run.command);
  return (
    <button
      onClick={onClick}
      style={{
        textAlign: "left",
        padding: "8px 12px",
        border: "none",
        borderLeft: `2px solid ${selected ? "#3b82f6" : "transparent"}`,
        background: selected ? "#1a1f2e" : "transparent",
        cursor: "pointer",
        width: "100%",
        color: selected ? "#e5e7eb" : "#9ca3af",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
        <span style={{
          padding: "1px 7px",
          fontSize: 9, fontWeight: 600,
          background: meta.bg, color: meta.color,
          textTransform: "uppercase", letterSpacing: "0.08em",
          fontFamily: "'JetBrains Mono', 'Fira Mono', monospace",
        }}>
          {run.command}
        </span>
        <span style={{ marginLeft: "auto", fontSize: 10, color: "#4b5563",
          fontFamily: "'JetBrains Mono', 'Fira Mono', monospace" }}>
          {relativeTime(run.created_at)}
        </span>
      </div>
      <div style={{
        fontSize: 10, color: selected ? "#6b7280" : "#4b5563",
        fontFamily: "'JetBrains Mono', 'Fira Mono', monospace",
      }}>
        {run.run_id.slice(0, 14)}…
      </div>
    </button>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const hash = useHash();
  const isDemoRCA = hash === "#demo-rca";
  const isRCAWorkspace = hash === "#rca-workspace";
  const jobsDashboardMatch = hash.match(/^#jobs\/(.+)\/dashboard$/);
  const jobDashboardId = jobsDashboardMatch ? decodeURIComponent(jobsDashboardMatch[1]) : null;

  const [runs,          setRuns         ] = useState<RunManifest[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun,   setSelectedRun  ] = useState<RunManifest | null>(null);
  const [error,         setError        ] = useState<string | null>(null);
  const [activeTab,     setActiveTab    ] = useState<TabType>("overview");
  const [artifactData,  setArtifactData ] = useState<Record<string, any>>({});
  const [loadingRuns,   setLoadingRuns  ] = useState<boolean>(true);
  const [clearing,      setClearing     ] = useState<boolean>(false); // ← NEW

  const selectedArtifacts = useMemo(() => selectedRun?.artifacts ?? {}, [selectedRun]);

  // ── Load run list ──────────────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        setLoadingRuns(true);
        const allRuns = await fetchRuns();
        setRuns(allRuns);
        const latest = await fetchLatest();
        if (latest?.run_id)          setSelectedRunId(latest.run_id);
        else if (allRuns.length > 0) setSelectedRunId(allRuns[0].run_id);
      } catch (e: any) {
        setError(e?.message ?? String(e));
      } finally {
        setLoadingRuns(false);
      }
    })();
  }, []);

  // ── Load selected run ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!selectedRunId) { setSelectedRun(null); return; }
    (async () => {
      try {
        setError(null);
        const r = await fetchRun(selectedRunId);
        setSelectedRun(r);

        const data: Record<string, any> = {};
        for (const [key, path] of Object.entries(r.artifacts || {})) {
          if (path) {
            try {
              const res = await fetch(`/api/file?path=${encodeURIComponent(path as string)}`);
              if (res.ok) data[key] = await res.json();
            } catch { /* ignore */ }
          }
        }
        setArtifactData(data);

        if      (r.command === "orchestrate")     setActiveTab("rca");
        else if (r.command === "git-dataflow")    setActiveTab("git");
        else if (r.command === "lineage-extract") setActiveTab("lineage");
        else                                      setActiveTab("overview");
      } catch (e: any) {
        setError(e?.message ?? String(e));
      }
    })();
  }, [selectedRunId]);

  // ── NEW: Clear all history ─────────────────────────────────────────────────
  const handleClearHistory = async () => {
    if (!window.confirm("Delete all run history? This cannot be undone.")) return;
    try {
      setClearing(true);
      const res = await fetch("/api/clear-history", { method: "DELETE" });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      // Reset all state
      setRuns([]);
      setSelectedRunId(null);
      setSelectedRun(null);
      setArtifactData({});
      setError(null);
    } catch (e: any) {
      setError(e?.message ?? "Failed to clear history");
    } finally {
      setClearing(false);
    }
  };

  const meta = commandMeta(selectedRun?.command ?? "");

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "Inter, system-ui, sans-serif", background: "#111318" }}>

      {/* ══ SIDEBAR ══════════════════════════════════════════════════════════ */}
      <div style={{
        width: 220,
        borderRight: "1px solid #1f2937",
        background: "#0f1117",
        color: "#9ca3af",
        position: "fixed",
        height: "100vh",
        display: "flex", flexDirection: "column",
        overflow: "hidden",
        zIndex: 10,
      }}>
        {/* Logo / title */}
        <div style={{
          padding: "16px 14px 12px",
          borderBottom: "1px solid #1f2937",
        }}>
          <div style={{
            fontSize: 11, fontWeight: 500,
            fontFamily: "'JetBrains Mono', 'Fira Mono', monospace",
            color: "#9ca3af", letterSpacing: "0.15em",
            textTransform: "uppercase", marginBottom: 4,
          }}>
            KRATOS RCA
          </div>
          <div style={{ fontSize: 10, color: "#4b5563" }}>v0.1 · FDIC-370</div>
          <div style={{
            fontSize: 10, color: "#4b5563", marginTop: 6,
            fontFamily: "'JetBrains Mono', 'Fira Mono', monospace",
          }}>
            Local viewer · runs/
          </div>
        </div>

        {/* ── Nav links ── */}
        <div style={{ padding: "8px 0", borderBottom: "1px solid #1f2937" }}>
          <a
            href="#rca-workspace"
            style={{
              display: "block",
              padding: "9px 14px",
              borderLeft: isRCAWorkspace ? "2px solid #3b82f6" : "2px solid transparent",
              background: isRCAWorkspace ? "#1a1f2e" : "transparent",
              color: isRCAWorkspace ? "#e5e7eb" : "#9ca3af",
              fontSize: 13,
              fontWeight: isRCAWorkspace ? 500 : 400,
              textDecoration: "none",
            }}
          >
            RCA Workspace
          </a>
          <a
            href="#demo-rca"
            style={{
              display: "block",
              padding: "9px 14px",
              borderLeft: isDemoRCA ? "2px solid #3b82f6" : "2px solid transparent",
              background: isDemoRCA ? "#1a1f2e" : "transparent",
              color: isDemoRCA ? "#e5e7eb" : "#9ca3af",
              fontSize: 13,
              fontWeight: isDemoRCA ? 500 : 400,
              textDecoration: "none",
            }}
          >
            Demo RCA
          </a>
        </div>
        <div style={{ flex: 1, overflow: "auto", padding: "10px 10px" }}>

          {/* ── Section header + Clear button ── */}
          <div style={{
            display: "flex", alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 8,
          }}>
            <div style={{
              fontSize: 9, fontWeight: 600, color: "#4b5563",
              textTransform: "uppercase", letterSpacing: "0.1em",
              fontFamily: "'JetBrains Mono', 'Fira Mono', monospace",
            }}>
              Runs {runs.length > 0 && `(${runs.length})`}
            </div>

            {/* ── CLEAR HISTORY BUTTON ── */}
            {runs.length > 0 && (
              <button
                onClick={handleClearHistory}
                disabled={clearing}
                title="Clear all run history"
                style={{
                  border: "1px solid #374151",
                  background: "transparent",
                  color: clearing ? "#4b5563" : "#ef4444",
                  borderRadius: 2,
                  padding: "2px 8px",
                  fontSize: 9,
                  fontWeight: 600,
                  cursor: clearing ? "not-allowed" : "pointer",
                  fontFamily: "'JetBrains Mono', 'Fira Mono', monospace",
                  letterSpacing: "0.05em",
                  textTransform: "uppercase",
                }}
              >
                {clearing ? "Clearing" : "Clear"}
              </button>
            )}
          </div>

          {error && (
            <div style={{
              color: "#ef4444", fontSize: 11, marginBottom: 8,
              padding: "8px 10px",
              borderLeft: "2px solid #ef4444",
              background: "rgba(239,68,68,0.07)",
              fontFamily: "'JetBrains Mono', 'Fira Mono', monospace",
            }}>
              ERROR: {error}
            </div>
          )}

          {loadingRuns
            ? <div style={{ fontSize: 11, color: "#4b5563", padding: "8px 4px" }}>Loading runs…</div>
            : runs.length === 0
              ? (
                <div style={{
                  fontSize: 11, color: "#4b5563", padding: "24px 4px",
                  textAlign: "center", lineHeight: 1.8,
                }}>
                  No runs found.<br />
                  <span style={{ fontSize: 11 }}>Run a command to get started.</span>
                </div>
              )
              : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {runs.map((r) => (
                    <RunCard
                      key={r.run_id}
                      run={r}
                      selected={r.run_id === selectedRunId}
                      onClick={() => setSelectedRunId(r.run_id)}
                    />
                  ))}
                </div>
              )
          }
        </div>
      </div>

      {/* ══ MAIN PANEL ═══════════════════════════════════════════════════════ */}
      <div style={{ flex: 1, marginLeft: 220, display: "flex", flexDirection: "column", overflow: "hidden", background: "#111318" }}>
        {isRCAWorkspace ? (
          <RCAWorkspace />
        ) : jobDashboardId ? (
          <JobDashboard jobId={jobDashboardId} />
        ) : isDemoRCA ? (
          <DemoRCA />
        ) : selectedRun ? (
          <>
            {/* ── Header ── */}
            <div style={{
              padding: "14px 20px",
              borderBottom: "1px solid #e5e5e5",
              background: "#fff",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ fontSize: 20, fontWeight: 800, color: "#111" }}>
                    {selectedRun.command}
                  </span>
                  <span style={{
                    padding: "3px 10px", borderRadius: 99,
                    fontSize: 11, fontWeight: 700,
                    background: meta.bg, color: meta.color,
                    textTransform: "uppercase",
                  }}>
                    {meta.icon} {selectedRun.command}
                  </span>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 11, color: "#aaa", fontFamily: "monospace" }}>
                    {selectedRun.run_id}
                  </div>
                  <div style={{ fontSize: 11, color: "#aaa" }}>
                    {relativeTime(selectedRun.created_at)} · {new Date(selectedRun.created_at).toLocaleString()}
                  </div>
                </div>
              </div>

              {/* ── Tabs ── */}
              <div style={{
                marginTop: 12, display: "flex", gap: 0,
                borderBottom: "1px solid #f0f0f0",
              }}>
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

            {/* ── Tab Content ── */}
            <div style={{ flex: 1, overflow: "hidden", minHeight: 0, background: "#f7f8fa" }}>

              {activeTab === "overview" && (
                <div style={{ padding: 20, height: "100%", overflow: "auto" }}>
                  <div style={{ marginBottom: 20 }}>
                    <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 10, color: "#111" }}>
                      Highlights
                    </div>
                    <div style={{
                      padding: 16, background: "#fff",
                      border: "1px solid #e8e8e8", borderRadius: 8,
                      fontSize: 14, color: "#333", lineHeight: 1.8,
                    }}>
                      {(selectedRun.summary?.highlights ?? []).length > 0
                        ? selectedRun.summary!.highlights!.map((h, idx) => (
                            <div key={idx} style={{ display: "flex", gap: 8 }}>
                              <span style={{ color: "#4a90e2" }}>•</span>
                              <span>{h}</span>
                            </div>
                          ))
                        : <span style={{ color: "#aaa" }}>(none)</span>
                      }
                    </div>
                  </div>

                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 10, color: "#111" }}>
                      Artifacts
                    </div>
                    <div style={{
                      padding: 16, background: "#fff",
                      border: "1px solid #e8e8e8", borderRadius: 8,
                      fontSize: 13,
                    }}>
                      {Object.keys(selectedArtifacts).length > 0
                        ? Object.entries(selectedArtifacts).map(([k, v]) => (
                            <div key={k} style={{ marginBottom: 6, display: "flex", gap: 8 }}>
                              <span style={{ fontWeight: 700, color: "#555", minWidth: 140 }}>{k}</span>
                              {v
                                ? <a href={`/api/file?path=${encodeURIComponent(v as string)}`} target="_blank" rel="noreferrer" style={{ color: "#4a90e2" }}>{v as string}</a>
                                : <span style={{ color: "#aaa" }}>(none)</span>
                              }
                            </div>
                          ))
                        : <span style={{ color: "#aaa" }}>(none)</span>
                      }
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
          <div style={{
            padding: 40, color: "#aaa", fontSize: 14,
            textAlign: "center", marginTop: 60,
          }}>
            ← Select a run from the left panel
          </div>
        )}
      </div>
    </div>
  );
}
