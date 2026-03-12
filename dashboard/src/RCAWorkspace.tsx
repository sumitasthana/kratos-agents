/**
 * RCAWorkspace.tsx
 *
 * Chat-driven RCA workspace with a left-panel 5-scenario selector and
 * a right-panel chat interface for job investigation.
 *
 * Accessible at hash #rca-workspace.
 */
import React, { useEffect, useRef, useState } from "react";

// ─── Design tokens (reuse DemoRCA enterprise dark theme) ─────────────────────

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
  violet:       "#8b5cf6",
  teal:         "#14b8a6",
  grey:         "#374151",
} as const;

const COLOR_MAP: Record<string, string> = {
  blue:   D.blue,
  violet: D.violet,
  red:    D.red,
  amber:  D.amber,
  teal:   D.teal,
  green:  D.green,
};

// ─── Types ────────────────────────────────────────────────────────────────────

interface ScenarioUiMetadata {
  color_key: string;
  priority: number;
  short_label: string;
}

interface ScenarioConfig {
  scenario_id: string;
  title: string;
  subtitle: string;
  expected_controls: string[];
  expected_problem_types: string[];
  allowed_analyzers: string[];
  anchor_preference: string;
  ui_metadata: ScenarioUiMetadata;
  dashboard_card_defaults: Record<string, boolean>;
}

interface IncidentCard {
  incident_id: string | null;
  job_id: string;
  scenario_id: string;
  scenario_name: string;
  job_status: string;
  problem_type: string;
  control_triggered: string | null;
  failed_node: string | null;
  failed_node_label: string | null;
  failure_reason: string | null;
  confidence: number;
  health_score: number;
  findings: string[];
  recommendations: string[];
  dashboard_url: string;
  created_at: string;
}

interface ChatRcaResponse {
  session_id: string;
  job_id: string;
  scenario_id: string;
  answer: string;
  summary: Record<string, unknown> | null;
  job_status: string;
  incident_card: IncidentCard | null;
  dashboard_url: string;
  suggested_followups: string[];
  audit_ref: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatRcaResponse;
  timestamp: Date;
}

// ─── Small components ─────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const color = status === "FAILED" ? D.red
    : status === "DEGRADED" ? D.amber
    : status === "SUCCESS" ? D.green
    : D.grey;
  return (
    <span style={{
      padding: "2px 8px",
      borderRadius: 3,
      fontSize: 10,
      fontWeight: 700,
      fontFamily: D.mono,
      background: `${color}22`,
      color,
      border: `1px solid ${color}44`,
      textTransform: "uppercase" as const,
      letterSpacing: "0.05em",
    }}>
      {status}
    </span>
  );
}

function IncidentCardPanel({ card, onDashboard }: { card: IncidentCard; onDashboard: () => void }) {
  return (
    <div style={{
      marginTop: 12,
      padding: "12px 14px",
      background: D.bgBase,
      border: `1px solid ${D.border}`,
      borderRadius: 6,
      fontSize: 12,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span style={{ color: D.textPrimary, fontWeight: 700, fontSize: 11 }}>INCIDENT CARD</span>
        <StatusBadge status={card.job_status} />
        <span style={{ marginLeft: "auto", color: D.textMuted, fontFamily: D.mono, fontSize: 10 }}>
          confidence {(card.confidence * 100).toFixed(0)}%
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px", color: D.textSecond }}>
        <div><span style={{ color: D.textMuted }}>Scenario:</span> {card.scenario_name}</div>
        <div><span style={{ color: D.textMuted }}>Problem:</span> {card.problem_type}</div>
        {card.control_triggered && (
          <div><span style={{ color: D.textMuted }}>Control:</span> {card.control_triggered}</div>
        )}
        {card.failed_node && (
          <div><span style={{ color: D.textMuted }}>Failed node:</span> {card.failed_node}</div>
        )}
        {card.failure_reason && (
          <div style={{ gridColumn: "1 / -1" }}>
            <span style={{ color: D.textMuted }}>Reason:</span> {card.failure_reason}
          </div>
        )}
      </div>

      {card.findings.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div style={{ color: D.textMuted, fontSize: 10, fontWeight: 600, marginBottom: 3, textTransform: "uppercase" }}>
            Key findings
          </div>
          {card.findings.slice(0, 3).map((f, i) => (
            <div key={i} style={{ color: D.textSecond, fontSize: 11, marginBottom: 2 }}>
              - {f}
            </div>
          ))}
        </div>
      )}

      <button
        onClick={onDashboard}
        style={{
          marginTop: 10,
          padding: "5px 12px",
          background: "transparent",
          border: `1px solid ${D.blue}`,
          color: D.blue,
          borderRadius: 3,
          fontSize: 11,
          fontWeight: 600,
          cursor: "pointer",
          fontFamily: D.mono,
          letterSpacing: "0.04em",
        }}
      >
        View Dashboard
      </button>
    </div>
  );
}

function SuggestedFollowups({
  followups,
  onSelect,
}: {
  followups: string[];
  onSelect: (q: string) => void;
}) {
  if (!followups.length) return null;
  return (
    <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
      {followups.map((f, i) => (
        <button
          key={i}
          onClick={() => onSelect(f)}
          style={{
            padding: "3px 10px",
            background: "transparent",
            border: `1px solid ${D.border}`,
            color: D.textSecond,
            borderRadius: 3,
            fontSize: 10,
            cursor: "pointer",
            fontFamily: D.mono,
          }}
        >
          {f}
        </button>
      ))}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function RCAWorkspace() {
  const [scenarios, setScenarios] = useState<ScenarioConfig[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<ScenarioConfig | null>(null);
  const [jobId, setJobId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingScenarios, setLoadingScenarios] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load scenario list on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/rca/scenarios");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const list: ScenarioConfig[] = data.scenarios ?? [];
        setScenarios(list);
        if (list.length > 0) setSelectedScenario(list[0]);
      } catch (e: unknown) {
        setError(`Could not load scenarios: ${(e as Error).message}`);
      } finally {
        setLoadingScenarios(false);
      }
    })();
  }, []);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const addMessage = (msg: Omit<ChatMessage, "id" | "timestamp">) => {
    setMessages((prev) => [
      ...prev,
      { ...msg, id: `${Date.now()}-${Math.random()}`, timestamp: new Date() },
    ]);
  };

  const handleSend = async (overrideText?: string) => {
    const query = overrideText ?? inputText.trim();
    if (!selectedScenario) {
      setError("Select a scenario first.");
      return;
    }
    const effectiveJobId = jobId.trim();
    if (!effectiveJobId) {
      setError("Enter a job ID to investigate.");
      return;
    }

    setError(null);
    setInputText("");
    addMessage({ role: "user", text: query || `Investigate job ${effectiveJobId}` });
    setIsLoading(true);

    try {
      const body = {
        scenario_id: selectedScenario.scenario_id,
        job_id: effectiveJobId,
        user_query: query,
        mode: "normal",
        max_hops: 3,
        refresh: false,
        session_id: sessionId,
      };

      const res = await fetch("/api/rca/chat/investigate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(errData.detail ?? `HTTP ${res.status}`);
      }

      const data: ChatRcaResponse = await res.json();
      setSessionId(data.session_id);
      addMessage({ role: "assistant", text: data.answer, response: data });
    } catch (e: unknown) {
      const msg = (e as Error).message ?? "Request failed";
      addMessage({ role: "assistant", text: `Error: ${msg}` });
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const navigateToDashboard = (url: string) => {
    if (url.startsWith("#")) {
      window.location.hash = url.slice(1);
    }
  };

  return (
    <div style={{
      display: "flex",
      height: "100vh",
      background: D.bgSurface,
      color: D.textPrimary,
      fontFamily: "Inter, system-ui, sans-serif",
    }}>

      {/* ── LEFT PANEL: Scenario selector ────────────────────────────── */}
      <div style={{
        width: 300,
        borderRight: `1px solid ${D.border}`,
        background: D.bgBase,
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
      }}>
        <div style={{
          padding: "16px 14px 12px",
          borderBottom: `1px solid ${D.border}`,
        }}>
          <div style={{
            fontSize: 9,
            fontWeight: 700,
            fontFamily: D.mono,
            color: D.textMuted,
            textTransform: "uppercase",
            letterSpacing: "0.15em",
            marginBottom: 4,
          }}>
            CONTROL SCENARIOS
          </div>
          <div style={{ fontSize: 10, color: D.textMuted }}>
            Select a scenario to scope the investigation
          </div>
        </div>

        <div style={{ flex: 1, overflow: "auto", padding: "8px 8px" }}>
          {loadingScenarios ? (
            <div style={{ fontSize: 11, color: D.textMuted, padding: "12px 6px" }}>
              Loading scenarios...
            </div>
          ) : (
            scenarios.map((sc) => {
              const accentColor = COLOR_MAP[sc.ui_metadata.color_key] ?? D.blue;
              const isSelected = selectedScenario?.scenario_id === sc.scenario_id;
              return (
                <button
                  key={sc.scenario_id}
                  onClick={() => setSelectedScenario(sc)}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    padding: "10px 12px",
                    marginBottom: 4,
                    background: isSelected ? `${accentColor}14` : "transparent",
                    border: "none",
                    borderLeft: `3px solid ${isSelected ? accentColor : "transparent"}`,
                    borderRadius: "0 4px 4px 0",
                    cursor: "pointer",
                    color: isSelected ? D.textPrimary : D.textSecond,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                    <span style={{
                      width: 6, height: 6, borderRadius: "50%",
                      background: accentColor, flexShrink: 0,
                    }} />
                    <span style={{ fontSize: 12, fontWeight: isSelected ? 600 : 400 }}>
                      {sc.title}
                    </span>
                    <span style={{
                      marginLeft: "auto",
                      fontSize: 9,
                      color: D.textMuted,
                      fontFamily: D.mono,
                    }}>
                      {sc.anchor_preference}
                    </span>
                  </div>
                  <div style={{
                    fontSize: 10, color: D.textMuted, paddingLeft: 12,
                    lineHeight: 1.4,
                  }}>
                    {sc.subtitle}
                  </div>
                  {isSelected && sc.expected_controls.length > 0 && (
                    <div style={{ paddingLeft: 12, marginTop: 6, display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {sc.expected_controls.slice(0, 2).map((ctrl) => (
                        <span key={ctrl} style={{
                          fontSize: 9, padding: "1px 5px",
                          background: `${accentColor}22`,
                          color: accentColor,
                          fontFamily: D.mono,
                          borderRadius: 2,
                        }}>
                          {ctrl}
                        </span>
                      ))}
                    </div>
                  )}
                </button>
              );
            })
          )}
        </div>

        {selectedScenario && (
          <div style={{
            padding: "10px 14px",
            borderTop: `1px solid ${D.border}`,
            fontSize: 10,
            color: D.textMuted,
          }}>
            <span style={{ fontWeight: 600, color: D.textSecond }}>Active: </span>
            {selectedScenario.ui_metadata.short_label}
            <span style={{ marginLeft: 6 }}>
              {selectedScenario.allowed_analyzers.join(", ")}
            </span>
          </div>
        )}
      </div>

      {/* ── RIGHT PANEL: Chat ──────────────────────────────────────────── */}
      <div style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}>

        {/* Job ID input bar */}
        <div style={{
          padding: "12px 20px",
          borderBottom: `1px solid ${D.border}`,
          background: D.bgCard,
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}>
          <div style={{ fontSize: 11, color: D.textMuted, fontFamily: D.mono, flexShrink: 0 }}>
            Job ID
          </div>
          <input
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
            placeholder="e.g. JOB-12345 or ETL-FAIL-001"
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSend();
            }}
            style={{
              flex: 1,
              padding: "6px 10px",
              background: D.bgBase,
              border: `1px solid ${D.border}`,
              borderRadius: 4,
              color: D.textPrimary,
              fontSize: 12,
              fontFamily: D.mono,
              outline: "none",
            }}
          />
          <button
            onClick={() => handleSend()}
            disabled={isLoading || !jobId.trim()}
            style={{
              padding: "6px 16px",
              background: isLoading || !jobId.trim() ? D.grey : D.blue,
              border: "none",
              borderRadius: 4,
              color: "#fff",
              fontSize: 12,
              fontWeight: 600,
              cursor: isLoading || !jobId.trim() ? "not-allowed" : "pointer",
              fontFamily: D.mono,
              letterSpacing: "0.03em",
            }}
          >
            {isLoading ? "Investigating..." : "Investigate"}
          </button>
          {sessionId && (
            <div style={{ fontSize: 9, color: D.textMuted, fontFamily: D.mono, flexShrink: 0 }}>
              session: {sessionId.slice(0, 8)}
            </div>
          )}
        </div>

        {error && (
          <div style={{
            padding: "8px 20px",
            background: `${D.red}11`,
            borderBottom: `1px solid ${D.red}33`,
            color: D.red,
            fontSize: 11,
            fontFamily: D.mono,
          }}>
            {error}
          </div>
        )}

        {/* Messages area */}
        <div style={{
          flex: 1,
          overflow: "auto",
          padding: "16px 20px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}>
          {messages.length === 0 ? (
            <div style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: D.textMuted,
              fontSize: 12,
              textAlign: "center",
            }}>
              <div>
                <div style={{ marginBottom: 8, fontSize: 14, color: D.textSecond }}>
                  {selectedScenario ? selectedScenario.title : "Select a scenario"}
                </div>
                <div style={{ fontSize: 11 }}>
                  Enter a job ID above and click Investigate to start an RCA session.
                  <br />
                  Then ask follow-up questions in the input below.
                </div>
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: msg.role === "user" ? "flex-end" : "flex-start",
                  maxWidth: "80%",
                  alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                }}
              >
                <div style={{
                  padding: "8px 12px",
                  borderRadius: msg.role === "user" ? "8px 8px 2px 8px" : "8px 8px 8px 2px",
                  background: msg.role === "user" ? D.blue : D.bgCard,
                  border: msg.role === "assistant" ? `1px solid ${D.border}` : "none",
                  color: D.textPrimary,
                  fontSize: 13,
                  lineHeight: 1.5,
                  whiteSpace: "pre-wrap",
                  maxWidth: "100%",
                }}>
                  {msg.text}
                </div>

                {msg.response?.incident_card && (
                  <div style={{ width: "100%", marginTop: 0 }}>
                    <IncidentCardPanel
                      card={msg.response.incident_card}
                      onDashboard={() => navigateToDashboard(msg.response!.dashboard_url)}
                    />
                  </div>
                )}

                {msg.response?.suggested_followups && msg.response.suggested_followups.length > 0 && (
                  <SuggestedFollowups
                    followups={msg.response.suggested_followups}
                    onSelect={(q) => {
                      setInputText(q);
                      handleSend(q);
                    }}
                  />
                )}

                <div style={{ fontSize: 9, color: D.textMuted, marginTop: 3, fontFamily: D.mono }}>
                  {msg.timestamp.toLocaleTimeString()}
                </div>
              </div>
            ))
          )}
          {isLoading && (
            <div style={{
              alignSelf: "flex-start",
              padding: "8px 12px",
              background: D.bgCard,
              border: `1px solid ${D.border}`,
              borderRadius: "8px 8px 8px 2px",
              color: D.textMuted,
              fontSize: 12,
              fontFamily: D.mono,
            }}>
              Running investigation...
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Chat input */}
        <div style={{
          padding: "12px 20px",
          borderTop: `1px solid ${D.border}`,
          background: D.bgCard,
          display: "flex",
          gap: 8,
        }}>
          <input
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a follow-up question, e.g. 'Why did it fail?' or 'What control was triggered?'"
            disabled={isLoading}
            style={{
              flex: 1,
              padding: "7px 12px",
              background: D.bgBase,
              border: `1px solid ${D.border}`,
              borderRadius: 4,
              color: D.textPrimary,
              fontSize: 12,
              outline: "none",
            }}
          />
          <button
            onClick={() => handleSend()}
            disabled={isLoading || !inputText.trim()}
            style={{
              padding: "7px 16px",
              background: isLoading || !inputText.trim() ? D.grey : D.blue,
              border: "none",
              borderRadius: 4,
              color: "#fff",
              fontSize: 12,
              fontWeight: 600,
              cursor: isLoading || !inputText.trim() ? "not-allowed" : "pointer",
              fontFamily: D.mono,
            }}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
