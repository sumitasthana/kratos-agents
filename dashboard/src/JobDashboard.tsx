/**
 * JobDashboard.tsx
 *
 * Per-job RCA dashboard page. Fetches the RcaDashboardSummary from
 * GET /api/rca/jobs/{jobId}/dashboard and renders it in full.
 *
 * Accessible at hash #jobs/{jobId}/dashboard
 */
import React, { useEffect, useState } from "react";

// ─── Design tokens ────────────────────────────────────────────────────────────

const D = {
  bgBase:       "#0f1117",
  bgSurface:    "#111318",
  bgCard:       "#161b25",
  border:       "#1f2937",
  textPrimary:  "#e5e7eb",
  textSecond:   "#9ca3af",
  textMuted:    "#4b5563",
  mono:         "'JetBrains Mono', 'Fira Mono', monospace" as const,
  green:        "#22c55e",
  amber:        "#f59e0b",
  red:          "#ef4444",
  blue:         "#3b82f6",
  grey:         "#374151",
} as const;

// ─── Types ────────────────────────────────────────────────────────────────────

interface LineageWalkNode {
  node_id: string;
  display_name: string;
  label: string;
  status: string;
  subtitle: string;
  order_index: number;
  ontology_path_fragment: string;
  was_evaluated: boolean;
}

interface AgentAnalysisChainEntry {
  agent_name: string;
  status: string;
  health: string;
  problem_type: string;
  control: string | null;
  key_finding: string;
  duration_ms: number;
}

interface IncidentCardData {
  job_id: string;
  scenario_name: string;
  problem_type: string;
  job_status: string;
  control_triggered: string | null;
  failed_node: string | null;
  failure_reason: string | null;
  confidence: number;
  health_score: number;
  findings: string[];
  recommendations: string[];
}

interface RcaDashboardSummary {
  investigation_id: string;
  scenario_name: string;
  anchor_type: string;
  anchor_id: string;
  health_score: number;
  health_status: string;
  problem_type: string;
  control_triggered: string | null;
  lineage_failure_node: string | null;
  confidence: number;
  lineage_walk: LineageWalkNode[];
  failed_node: string | null;
  failed_node_status: string | null;
  failure_reason: string | null;
  findings: string[];
  agent_analysis_chain: AgentAnalysisChainEntry[];
  evidence_objects: string[];
  ontology_paths_used: string[];
  audit_trace: string[];
  stop_reason: string | null;
  traversal_mode: string;
  generated_at: string;
  session_id: string | null;
  dashboard_url: string;
  incident_card_data: IncidentCardData | null;
}

// ─── Small components ─────────────────────────────────────────────────────────

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: D.bgCard,
      border: `1px solid ${D.border}`,
      borderRadius: 6,
      padding: "14px 16px",
      ...style,
    }}>
      {children}
    </div>
  );
}

function SectionTitle({ title }: { title: string }) {
  return (
    <div style={{
      fontSize: 9,
      fontWeight: 700,
      fontFamily: D.mono,
      color: D.textMuted,
      textTransform: "uppercase",
      letterSpacing: "0.12em",
      marginBottom: 10,
    }}>
      {title}
    </div>
  );
}

function HealthGauge({ score, status }: { score: number; status: string }) {
  const color = status === "FAILED" ? D.red
    : status === "DEGRADED" ? D.amber
    : status === "HEALTHY" ? D.green
    : D.grey;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
      <div style={{
        width: 64, height: 64,
        borderRadius: "50%",
        border: `4px solid ${color}`,
        display: "flex", alignItems: "center", justifyContent: "center",
        flexDirection: "column",
        flexShrink: 0,
      }}>
        <div style={{ fontSize: 18, fontWeight: 800, color, lineHeight: 1 }}>
          {Math.round(score)}
        </div>
        <div style={{ fontSize: 8, color: D.textMuted, lineHeight: 1, marginTop: 1 }}>/ 100</div>
      </div>
      <div>
        <div style={{ fontSize: 20, fontWeight: 700, color }}>{status}</div>
        <div style={{ fontSize: 11, color: D.textMuted }}>health status</div>
      </div>
    </div>
  );
}

function StatusDot({ status, evaluated }: { status: string; evaluated: boolean }) {
  if (!evaluated) return (
    <div style={{ width: 8, height: 8, borderRadius: "50%", background: D.grey, opacity: 0.5 }} />
  );
  const color = status === "FAILED" ? D.red
    : status === "DEGRADED" ? D.amber
    : status === "HEALTHY" ? D.green
    : D.grey;
  return <div style={{ width: 8, height: 8, borderRadius: "50%", background: color }} />;
}

function LineageWalk({ nodes }: { nodes: LineageWalkNode[] }) {
  if (!nodes.length) return (
    <div style={{ fontSize: 11, color: D.textMuted }}>No lineage walk data.</div>
  );
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 0, overflowX: "auto", padding: "4px 0" }}>
      {nodes.map((node, i) => {
        const isLast = i === nodes.length - 1;
        const color = node.status === "FAILED" ? D.red
          : node.status === "DEGRADED" ? D.amber
          : node.status === "HEALTHY" ? D.green
          : D.grey;
        return (
          <div key={node.node_id} style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
            <div style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 4,
              padding: "8px 10px",
              background: node.was_evaluated ? `${color}11` : "transparent",
              border: `1px solid ${node.was_evaluated ? `${color}44` : D.border}`,
              borderRadius: 4,
              minWidth: 80,
            }}>
              <StatusDot status={node.status} evaluated={node.was_evaluated} />
              <div style={{
                fontSize: 10, fontWeight: 600,
                color: node.was_evaluated ? D.textPrimary : D.textMuted,
                textAlign: "center",
                maxWidth: 80,
                wordBreak: "break-word",
              }}>
                {node.display_name}
              </div>
              <div style={{ fontSize: 9, color: D.textMuted, textAlign: "center" }}>
                {node.label}
              </div>
              {!node.was_evaluated && (
                <div style={{ fontSize: 8, color: D.textMuted, fontFamily: D.mono }}>
                  skipped
                </div>
              )}
            </div>
            {!isLast && (
              <div style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
                {nodes[i + 1]?.ontology_path_fragment && (
                  <div style={{
                    fontSize: 8,
                    color: D.textMuted,
                    fontFamily: D.mono,
                    padding: "0 4px",
                    whiteSpace: "nowrap",
                  }}>
                    {nodes[i + 1].ontology_path_fragment}
                  </div>
                )}
                <div style={{ color: D.textMuted, fontSize: 14 }}>{">"}</div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function AgentChainTable({ entries }: { entries: AgentAnalysisChainEntry[] }) {
  if (!entries.length) return (
    <div style={{ fontSize: 11, color: D.textMuted }}>No agent analysis chain data.</div>
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {entries.map((entry, i) => {
        const healthColor = entry.health === "FAILED" ? D.red
          : entry.health === "DEGRADED" ? D.amber
          : entry.health === "HEALTHY" ? D.green
          : D.grey;
        return (
          <div key={i} style={{
            padding: "8px 12px",
            background: D.bgBase,
            border: `1px solid ${D.border}`,
            borderRadius: 4,
            fontSize: 11,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <span style={{ fontWeight: 600, color: D.textPrimary }}>{entry.agent_name}</span>
              <span style={{
                padding: "1px 6px",
                borderRadius: 2,
                fontSize: 9,
                fontWeight: 700,
                background: `${healthColor}22`,
                color: healthColor,
                fontFamily: D.mono,
              }}>
                {entry.health}
              </span>
              <span style={{ marginLeft: "auto", fontSize: 9, color: D.textMuted, fontFamily: D.mono }}>
                {entry.duration_ms}ms
              </span>
            </div>
            <div style={{ color: D.textSecond }}>{entry.key_finding}</div>
            {entry.control && (
              <div style={{ color: D.textMuted, fontSize: 10, marginTop: 3 }}>
                Control: {entry.control}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface JobDashboardProps {
  jobId: string;
}

export default function JobDashboard({ jobId }: JobDashboardProps) {
  const [summary, setSummary] = useState<RcaDashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [auditOpen, setAuditOpen] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/rca/jobs/${encodeURIComponent(jobId)}/dashboard`);
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
          throw new Error(err.detail ?? `HTTP ${res.status}`);
        }
        setSummary(await res.json());
      } catch (e: unknown) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, [jobId]);

  if (loading) {
    return (
      <div style={{ padding: 40, color: D.textMuted, fontFamily: D.mono, fontSize: 12 }}>
        Loading dashboard for {jobId}...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 40 }}>
        <div style={{
          padding: "12px 16px",
          background: `${D.red}11`,
          border: `1px solid ${D.red}44`,
          borderRadius: 6,
          color: D.red,
          fontSize: 12,
          fontFamily: D.mono,
        }}>
          ERROR: {error}
        </div>
        <div style={{ marginTop: 12 }}>
          <a href="#rca-workspace" style={{ color: D.blue, fontSize: 12 }}>
            Back to RCA Workspace
          </a>
        </div>
      </div>
    );
  }

  if (!summary) return null;

  const card = summary.incident_card_data;
  const healthColor = summary.health_status === "FAILED" ? D.red
    : summary.health_status === "DEGRADED" ? D.amber
    : summary.health_status === "HEALTHY" ? D.green
    : D.grey;

  return (
    <div style={{
      background: D.bgSurface,
      color: D.textPrimary,
      fontFamily: "Inter, system-ui, sans-serif",
      minHeight: "100vh",
      padding: "24px 28px",
      overflow: "auto",
    }}>
      {/* Back link */}
      <div style={{ marginBottom: 16 }}>
        <a href="#rca-workspace" style={{ color: D.blue, fontSize: 11, fontFamily: D.mono }}>
          &lt; Back to RCA Workspace
        </a>
      </div>

      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{
          fontSize: 9, fontWeight: 700, fontFamily: D.mono,
          color: D.textMuted, textTransform: "uppercase", letterSpacing: "0.15em",
          marginBottom: 4,
        }}>
          JOB INVESTIGATION DASHBOARD
        </div>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
          <div>
            <div style={{ fontSize: 22, fontWeight: 800, color: D.textPrimary }}>
              {jobId}
            </div>
            <div style={{ fontSize: 11, color: D.textMuted, marginTop: 3 }}>
              {summary.scenario_name} &middot; {summary.anchor_type}: {summary.anchor_id}
            </div>
          </div>
          <div style={{ marginLeft: "auto" }}>
            <HealthGauge score={summary.health_score} status={summary.health_status} />
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, maxWidth: 1400 }}>

        {/* Incident card */}
        {card && (
          <Card style={{ gridColumn: "1 / -1" }}>
            <SectionTitle title="Incident Card" />
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "8px 20px", fontSize: 12 }}>
              <div>
                <div style={{ color: D.textMuted, fontSize: 10, marginBottom: 2 }}>Job Status</div>
                <span style={{
                  padding: "2px 8px", borderRadius: 3, fontSize: 11, fontWeight: 700,
                  fontFamily: D.mono,
                  background: `${healthColor}22`, color: healthColor,
                  border: `1px solid ${healthColor}44`, textTransform: "uppercase",
                }}>
                  {card.job_status}
                </span>
              </div>
              <div>
                <div style={{ color: D.textMuted, fontSize: 10, marginBottom: 2 }}>Problem Type</div>
                <div style={{ color: D.textSecond }}>{card.problem_type}</div>
              </div>
              <div>
                <div style={{ color: D.textMuted, fontSize: 10, marginBottom: 2 }}>Confidence</div>
                <div style={{ color: D.textSecond }}>{(card.confidence * 100).toFixed(0)}%</div>
              </div>
              {card.control_triggered && (
                <div>
                  <div style={{ color: D.textMuted, fontSize: 10, marginBottom: 2 }}>Control Triggered</div>
                  <div style={{ color: D.amber, fontFamily: D.mono, fontSize: 11 }}>{card.control_triggered}</div>
                </div>
              )}
              {card.failed_node && (
                <div>
                  <div style={{ color: D.textMuted, fontSize: 10, marginBottom: 2 }}>Failed Node</div>
                  <div style={{ color: D.red, fontFamily: D.mono, fontSize: 11 }}>{card.failed_node}</div>
                </div>
              )}
              {card.failure_reason && (
                <div style={{ gridColumn: "1 / -1" }}>
                  <div style={{ color: D.textMuted, fontSize: 10, marginBottom: 2 }}>Failure Reason</div>
                  <div style={{ color: D.textSecond }}>{card.failure_reason}</div>
                </div>
              )}
            </div>

            {card.findings.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <div style={{ color: D.textMuted, fontSize: 10, fontWeight: 600, marginBottom: 5, textTransform: "uppercase" }}>
                  Findings
                </div>
                {card.findings.map((f, i) => (
                  <div key={i} style={{
                    padding: "5px 10px",
                    borderLeft: `2px solid ${D.border}`,
                    color: D.textSecond,
                    fontSize: 12,
                    marginBottom: 4,
                  }}>
                    {f}
                  </div>
                ))}
              </div>
            )}

            {card.recommendations.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <div style={{ color: D.textMuted, fontSize: 10, fontWeight: 600, marginBottom: 5, textTransform: "uppercase" }}>
                  Recommendations
                </div>
                {card.recommendations.map((r, i) => (
                  <div key={i} style={{
                    padding: "5px 10px",
                    borderLeft: `2px solid ${D.blue}55`,
                    color: D.textSecond,
                    fontSize: 12,
                    marginBottom: 4,
                  }}>
                    {r}
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}

        {/* Lineage walk */}
        <Card style={{ gridColumn: "1 / -1" }}>
          <SectionTitle title="Lineage Walk" />
          <LineageWalk nodes={summary.lineage_walk} />
        </Card>

        {/* Findings */}
        <Card>
          <SectionTitle title="Findings" />
          {summary.findings.length === 0 ? (
            <div style={{ fontSize: 11, color: D.textMuted }}>No findings recorded.</div>
          ) : (
            summary.findings.map((f, i) => (
              <div key={i} style={{
                padding: "5px 10px",
                borderLeft: `2px solid ${D.border}`,
                color: D.textSecond,
                fontSize: 12,
                marginBottom: 5,
              }}>
                {f}
              </div>
            ))
          )}
        </Card>

        {/* Agent analysis chain */}
        <Card>
          <SectionTitle title="Agent Analysis Chain" />
          <AgentChainTable entries={summary.agent_analysis_chain} />
        </Card>

        {/* Evidence summary */}
        <Card>
          <SectionTitle title="Evidence Summary" />
          <div style={{ fontSize: 11, color: D.textSecond, marginBottom: 6 }}>
            {summary.evidence_objects.length} evidence object(s) referenced.
          </div>
          {summary.evidence_objects.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {summary.evidence_objects.map((id, i) => (
                <span key={i} style={{
                  fontFamily: D.mono,
                  fontSize: 9,
                  color: D.textMuted,
                  background: D.bgBase,
                  border: `1px solid ${D.border}`,
                  borderRadius: 2,
                  padding: "2px 6px",
                }}>
                  {id.slice(0, 12)}
                </span>
              ))}
            </div>
          )}
          <div style={{ marginTop: 10, fontSize: 11, color: D.textSecond }}>
            {summary.ontology_paths_used.length} ontology path(s) used.
          </div>
        </Card>

        {/* Metadata */}
        <Card>
          <SectionTitle title="Investigation Metadata" />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px", fontSize: 11 }}>
            <div><span style={{ color: D.textMuted }}>Stop reason:</span> {summary.stop_reason ?? "N/A"}</div>
            <div><span style={{ color: D.textMuted }}>Traversal mode:</span> {summary.traversal_mode}</div>
            <div><span style={{ color: D.textMuted }}>Confidence:</span> {(summary.confidence * 100).toFixed(0)}%</div>
            <div><span style={{ color: D.textMuted }}>Generated:</span> {new Date(summary.generated_at).toLocaleString()}</div>
            {summary.session_id && (
              <div style={{ gridColumn: "1 / -1" }}>
                <span style={{ color: D.textMuted }}>Session:</span>{" "}
                <span style={{ fontFamily: D.mono, fontSize: 10, color: D.textSecond }}>
                  {summary.session_id}
                </span>
              </div>
            )}
          </div>
        </Card>

        {/* Audit trace (collapsible) */}
        {summary.audit_trace.length > 0 && (
          <Card style={{ gridColumn: "1 / -1" }}>
            <button
              onClick={() => setAuditOpen((v) => !v)}
              style={{
                background: "transparent",
                border: "none",
                padding: 0,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 6,
                width: "100%",
                textAlign: "left",
              }}
            >
              <span style={{
                fontSize: 9, fontWeight: 700, fontFamily: D.mono,
                color: D.textMuted, textTransform: "uppercase", letterSpacing: "0.12em",
              }}>
                AUDIT TRACE ({summary.audit_trace.length} steps)
              </span>
              <span style={{ color: D.textMuted, fontSize: 11, marginLeft: 4 }}>
                {auditOpen ? "[collapse]" : "[expand]"}
              </span>
            </button>
            {auditOpen && (
              <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 4 }}>
                {summary.audit_trace.map((line, i) => (
                  <div key={i} style={{
                    fontSize: 10,
                    fontFamily: D.mono,
                    color: D.textMuted,
                    padding: "2px 0",
                    borderBottom: `1px solid ${D.border}`,
                  }}>
                    {String(i + 1).padStart(2, "0")}. {line}
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}
