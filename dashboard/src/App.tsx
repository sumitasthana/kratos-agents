import { useState, useCallback } from 'react';
import { useRcaStream } from './hooks/useRcaStream';
import { useIncidents } from './hooks/useIncidents';
import { useTheme } from './hooks/useTheme';
import { ThemeContext } from './ThemeContext';
import { IncidentSidebar } from './components/IncidentSidebar';
import { PhaseIndicator } from './components/PhaseIndicator';
import { MessageStream } from './components/MessageStream';
import { ChatInput } from './components/ChatInput';
import { StatusBar } from './components/StatusBar';
import { ThemeToggle } from './components/ThemeToggle';

type SessionMode = 'rca' | 'chat';

export default function App() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [started, setStarted] = useState(false);
  const [mode, setMode] = useState<SessionMode>('rca');

  const { mode: themeMode, colors, cycleTheme } = useTheme();
  const { incidents } = useIncidents();
  const { messages, isTracing, isConnected, currentPhase, connect, send } = useRcaStream();

  const handleSelectIncident = useCallback((id: string) => {
    setSelectedId(id);
    setStarted(false);
  }, []);

  const startSession = useCallback((m: SessionMode) => {
    if (!selectedId) return;
    setMode(m);
    setStarted(true);
    connect(selectedId, m);
  }, [selectedId, connect]);

  const handleStartRca = useCallback(() => startSession('rca'), [startSession]);
  const handleStartChat = useCallback(() => startSession('chat'), [startSession]);

  // After an RCA pipeline finishes (isTracing goes false while in rca mode),
  // we're already in the server's chat loop — reflect that in the UI.
  const rcaCompleted = mode === 'rca' && started && !isTracing && currentPhase === 'PERSIST';
  const effectiveMode: SessionMode = rcaCompleted ? 'chat' : mode;

  const handleToggleMode = useCallback(() => {
    if (!selectedId) return;
    // If RCA already completed, chat is already active — don't reconnect
    if (rcaCompleted) return;
    const next: SessionMode = mode === 'rca' ? 'chat' : 'rca';
    setMode(next);
    connect(selectedId, next);
  }, [selectedId, mode, rcaCompleted, connect]);

  const handleSend = useCallback((text: string) => {
    send(text);
  }, [send]);

  // Derive evidence count and hop count from messages
  const evidenceCount = messages.filter(
    m => m.type === 'evidence' || (m.type === 'agent' && m.tag === 'evidence')
  ).length;
  const hopCount = messages
    .filter(m => m.type === 'hop')
    .reduce((acc, m) => acc + (m.type === 'hop' ? m.hops.length : 0), 0);

  const selectedIncident = incidents.find(i => i.id === selectedId);
  const showLanding = selectedId && !started;

  return (
    <ThemeContext.Provider value={colors}>
    <div
      style={{
        height: '100vh',
        display: 'flex',
        flexDirection: 'row',
        backgroundColor: colors.bg,
        overflow: 'hidden',
      }}
    >
      {/* Sidebar */}
      <IncidentSidebar
        incidents={incidents}
        selectedId={selectedId}
        collapsed={sidebarCollapsed}
        onSelect={handleSelectIncident}
        onToggle={() => setSidebarCollapsed(c => !c)}
      />

      {/* Main area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Top header bar */}
        <div
          style={{
            flexShrink: 0,
            backgroundColor: colors.bgElevated,
            borderBottom: `1px solid ${colors.border}`,
            padding: '8px 16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <ThemeToggle mode={themeMode} colors={colors} onCycle={cycleTheme} />
            <span
              style={{
                fontFamily: 'IBM Plex Mono, monospace',
                fontSize: '11px',
                color: colors.accent,
                fontWeight: 600,
                letterSpacing: '0.08em',
              }}
            >
              KRATOS
            </span>
            <span style={{ color: colors.textFaint, fontSize: '10px' }}>|</span>
            <span
              style={{
                fontFamily: 'IBM Plex Mono, monospace',
                fontSize: '10px',
                color: colors.textMuted,
              }}
            >
              Root Cause Analysis Terminal
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {/* Status badge */}
            {started && isTracing && (
              <span style={{
                fontFamily: 'IBM Plex Mono, monospace',
                fontSize: '9px',
                letterSpacing: '0.08em',
                padding: '3px 10px',
                borderRadius: '3px',
                backgroundColor: '#172554',
                border: '1px solid #1e3a8a',
                color: '#93c5fd',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}>
                <span className="animate-pulse-dot" style={{ fontSize: '8px' }}>●</span>
                ANALYZING
              </span>
            )}
            {started && !isTracing && currentPhase === 'PERSIST' && (
              <span style={{
                fontFamily: 'IBM Plex Mono, monospace',
                fontSize: '9px',
                letterSpacing: '0.08em',
                padding: '3px 10px',
                borderRadius: '3px',
                backgroundColor: '#052e16',
                border: '1px solid #14532d',
                color: '#22c55e',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}>
                ✓ COMPLETE
              </span>
            )}

            {/* Mode toggle — only visible during an active session */}
            {started && selectedId && (
              <button
                onClick={handleToggleMode}
                disabled={isTracing || rcaCompleted}
                title={rcaCompleted ? 'RCA complete — chat is active' : isTracing ? 'Wait for pipeline to finish' : `Switch to ${mode === 'rca' ? 'Chat' : 'RCA'} mode`}
                style={{
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: '9px',
                  letterSpacing: '0.06em',
                  padding: '3px 10px',
                  borderRadius: '3px',
                  backgroundColor: '#0f172a',
                  border: `1px solid ${(isTracing || rcaCompleted) ? '#1e293b' : '#334155'}`,
                  color: (isTracing || rcaCompleted) ? '#334155' : '#94a3b8',
                  cursor: (isTracing || rcaCompleted) ? 'default' : 'pointer',
                  transition: 'all 0.15s',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
                onMouseEnter={e => {
                  if (!isTracing && !rcaCompleted) {
                    e.currentTarget.style.borderColor = '#3b82f6';
                    e.currentTarget.style.color = '#93c5fd';
                  }
                }}
                onMouseLeave={e => {
                  const disabled = isTracing || rcaCompleted;
                  e.currentTarget.style.borderColor = disabled ? '#1e293b' : '#334155';
                  e.currentTarget.style.color = disabled ? '#334155' : '#94a3b8';
                }}
              >
                {/* Current mode indicator */}
                <span
                  style={{
                    display: 'inline-block',
                    width: '5px',
                    height: '5px',
                    borderRadius: '50%',
                    backgroundColor: effectiveMode === 'chat' ? '#22c55e' : '#3b82f6',
                  }}
                />
                {rcaCompleted ? 'RCA + CHAT' : effectiveMode === 'chat' ? 'CHAT' : 'RCA'}
                {!rcaCompleted && (
                  <>
                    <span style={{ color: '#334155' }}>|</span>
                    <span style={{ color: isTracing ? '#334155' : '#64748b' }}>
                      {effectiveMode === 'chat' ? 'RCA' : 'CHAT'}
                    </span>
                  </>
                )}
              </button>
            )}

            {selectedId && (
              <span
                style={{
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: '10px',
                  color: '#334155',
                }}
              >
                {selectedId}
              </span>
            )}
          </div>
        </div>

        {!selectedId ? (
          /* ── No incident selected ── */
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '12px',
            }}
          >
            <span
              style={{
                fontFamily: 'IBM Plex Mono, monospace',
                fontSize: '12px',
                color: colors.textFaint,
              }}
            >
              Select an incident to begin
            </span>
          </div>
        ) : showLanding ? (
          /* ── Landing panel: incident selected but not started ── */
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '28px',
              padding: '40px',
            }}
          >
            {/* Incident summary */}
            <div style={{ textAlign: 'center', maxWidth: '480px' }}>
              <span
                style={{
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: '10px',
                  color: '#64748b',
                  letterSpacing: '0.08em',
                }}
              >
                SELECTED INCIDENT
              </span>
              <h2
                style={{
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: '16px',
                  color: '#e2e8f0',
                  margin: '8px 0 6px',
                  fontWeight: 600,
                }}
              >
                {selectedId}
              </h2>
              {selectedIncident && (
                <>
                  <p
                    style={{
                      fontFamily: 'IBM Plex Mono, monospace',
                      fontSize: '12px',
                      color: '#94a3b8',
                      margin: '0 0 4px',
                    }}
                  >
                    {selectedIncident.service}
                  </p>
                  <p
                    style={{
                      fontFamily: 'IBM Plex Mono, monospace',
                      fontSize: '11px',
                      color: '#64748b',
                      margin: 0,
                      lineHeight: '1.5',
                    }}
                  >
                    {selectedIncident.error}
                  </p>
                </>
              )}
            </div>

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: '16px' }}>
              <button
                onClick={handleStartRca}
                style={{
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: '12px',
                  padding: '10px 24px',
                  borderRadius: '4px',
                  backgroundColor: '#172554',
                  border: '1px solid #3b82f6',
                  color: '#93c5fd',
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                  letterSpacing: '0.04em',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.backgroundColor = '#1e3a8a';
                  e.currentTarget.style.color = '#bfdbfe';
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.backgroundColor = '#172554';
                  e.currentTarget.style.color = '#93c5fd';
                }}
              >
                Start RCA
              </button>
              <button
                onClick={handleStartChat}
                style={{
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: '12px',
                  padding: '10px 24px',
                  borderRadius: '4px',
                  backgroundColor: '#0f172a',
                  border: '1px solid #1e293b',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                  letterSpacing: '0.04em',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.borderColor = '#3b82f6';
                  e.currentTarget.style.color = '#93c5fd';
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.borderColor = '#1e293b';
                  e.currentTarget.style.color = '#94a3b8';
                }}
              >
                Chat
              </button>
            </div>

            <p
              style={{
                fontFamily: 'IBM Plex Mono, monospace',
                fontSize: '9px',
                color: '#334155',
                margin: 0,
                textAlign: 'center',
                maxWidth: '360px',
                lineHeight: '1.6',
              }}
            >
              Start RCA runs the full 7-phase pipeline. Chat connects directly for follow-up questions.
            </p>
          </div>
        ) : (
          /* ── Active session: pipeline running or completed ── */
          <>
            {/* Phase indicator */}
            <PhaseIndicator currentPhase={currentPhase} />

            {/* Global progress bar */}
            <div style={{
              height: '2px',
              backgroundColor: '#111827',
              overflow: 'hidden',
              flexShrink: 0,
            }}>
              {isTracing && (
                <div className="animate-progress" style={{
                  height: '100%',
                  backgroundColor: '#3b82f6',
                }} />
              )}
              {!isTracing && currentPhase === 'PERSIST' && (
                <div style={{
                  height: '100%',
                  width: '100%',
                  backgroundColor: '#22c55e',
                  transition: 'width 0.5s ease',
                }} />
              )}
            </div>

            {/* Message stream */}
            <MessageStream messages={messages} isTracing={isTracing} currentPhase={currentPhase} />

            {/* Chat input */}
            <ChatInput
              currentPhase={currentPhase}
              isTracing={isTracing}
              isConnected={isConnected}
              onSend={handleSend}
            />

            {/* Status bar */}
            <StatusBar
              isTracing={isTracing}
              currentPhase={currentPhase}
              evidenceCount={evidenceCount}
              hopCount={hopCount}
              incidentId={selectedId}
            />
          </>
        )}
      </div>
    </div>
    </ThemeContext.Provider>
  );
}
