import { useState, useCallback } from 'react';
import { useRcaStream } from './hooks/useRcaStream';
import { useIncidents } from './hooks/useIncidents';
import { useTheme, type ThemeColors } from './hooks/useTheme';
import { ThemeContext } from './ThemeContext';
import type { RcaMessage, Incident, PhaseId } from './types';
import { IncidentSidebar } from './components/IncidentSidebar';
import { PhaseIndicator } from './components/PhaseIndicator';
import { MessageStream } from './components/MessageStream';
import { ChatInput } from './components/ChatInput';
import { StatusBar } from './components/StatusBar';
import { ThemeToggle } from './components/ThemeToggle';

type SessionMode = 'rca' | 'chat';

// Constants for phase-specific colors
const PHASE_COMPLETE_COLORS = {
  border: '#14532d',
  text: '#22c55e',
} as const;

// Prop interfaces for sub-components
interface StatusBadgeProps {
  isTracing: boolean;
  currentPhase: PhaseId | null;
  colors: ThemeColors;
}

interface ModeToggleProps {
  effectiveMode: SessionMode;
  disabled: boolean;
  rcaCompleted: boolean;
  colors: ThemeColors;
  onClick: () => void;
}

interface EmptyStateProps {
  colors: ThemeColors;
}

interface LandingPanelProps {
  selectedId: string;
  incident: Incident | undefined;
  colors: ThemeColors;
  onStartRca: () => void;
  onStartChat: () => void;
}

interface SessionViewProps {
  messages: RcaMessage[];
  isTracing: boolean;
  isConnected: boolean;
  currentPhase: PhaseId | null;
  evidenceCount: number;
  hopCount: number;
  incidentId: string;
  colors: ThemeColors;
  onSend: (text: string) => void;
}

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

  const rcaCompleted = mode === 'rca' && started && !isTracing && currentPhase === ('PERSIST' as PhaseId);
  const effectiveMode: SessionMode = rcaCompleted ? 'chat' : mode;

  const handleToggleMode = useCallback(() => {
    if (!selectedId || rcaCompleted) return;
    const next: SessionMode = mode === 'rca' ? 'chat' : 'rca';
    setMode(next);
    connect(selectedId, next);
  }, [selectedId, mode, rcaCompleted, connect]);

  const handleSend = useCallback((text: string) => {
    send(text);
  }, [send]);

  const evidenceCount = messages.filter(
    m => m.type === 'evidence' || (m.type === 'agent' && m.tag === 'evidence')
  ).length;
  const hopCount = messages
    .filter(m => m.type === 'hop')
    .reduce((acc, m) => acc + (m.type === 'hop' ? m.hops.length : 0), 0);

  const selectedIncident = incidents.find(i => i.id === selectedId);
  const showLanding = selectedId && !started;
  const showSession = selectedId && started;

  const modeToggleDisabled = isTracing || rcaCompleted;

  return (
    <ThemeContext.Provider value={colors}>
      <div
        style={{
          height: '100vh',
          display: 'flex',
          flexDirection: 'row',
          backgroundColor: colors.bg,
          overflow: 'hidden',
          fontFamily: 'IBM Plex Mono, monospace',
        }}
      >
        {/* ── Sidebar ── */}
        <IncidentSidebar
          incidents={incidents}
          selectedId={selectedId}
          collapsed={sidebarCollapsed}
          onSelect={handleSelectIncident}
          onToggle={() => setSidebarCollapsed(c => !c)}
        />

        {/* ── Main area ── */}
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            /* KEY FIX: minWidth/minHeight 0 lets this flex child shrink
               below its content size so nothing overflows the viewport */
            minWidth: 0,
            minHeight: 0,
            overflow: 'hidden',
          }}
        >
          {/* ── Top header bar (fixed height) ── */}
          <header
            style={{
              flexShrink: 0,
              backgroundColor: colors.bgElevated,
              borderBottom: `1px solid ${colors.border}`,
              padding: '8px 16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
            }}
          >
            {/* Left cluster */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
              <ThemeToggle mode={themeMode} colors={colors} onCycle={cycleTheme} />
              <span style={{ fontSize: '11px', color: colors.accent, fontWeight: 600, letterSpacing: '0.08em' }}>
                KRATOS
              </span>
              <span style={{ color: colors.textFaint, fontSize: '10px' }}>|</span>
              <span style={{ fontSize: '10px', color: colors.textMuted }}>
                Root Cause Analysis Terminal
              </span>
            </div>

            {/* Right cluster */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexShrink: 0 }}>
              {/* Status badge */}
              {showSession && <StatusBadge isTracing={isTracing} currentPhase={currentPhase} colors={colors} />}

              {/* Mode toggle */}
              {showSession && (
                <ModeToggle
                  effectiveMode={effectiveMode}
                  disabled={modeToggleDisabled}
                  rcaCompleted={rcaCompleted}
                  colors={colors}
                  onClick={handleToggleMode}
                />
              )}

              {selectedId && (
                <span style={{ fontSize: '10px', color: colors.textFaint }}>{selectedId}</span>
              )}
            </div>
          </header>

          {/* ── Body ── */}
          {!selectedId && <EmptyState colors={colors} />}
          {showLanding && (
            <LandingPanel
              selectedId={selectedId!}
              incident={selectedIncident}
              colors={colors}
              onStartRca={handleStartRca}
              onStartChat={handleStartChat}
            />
          )}
          {showSession && (
            <SessionView
              messages={messages}
              isTracing={isTracing}
              isConnected={isConnected}
              currentPhase={currentPhase}
              evidenceCount={evidenceCount}
              hopCount={hopCount}
              incidentId={selectedId!}
              colors={colors}
              onSend={handleSend}
            />
          )}
        </div>
      </div>
    </ThemeContext.Provider>
  );
}

/* ─────────────────────────────────────────────
   Extracted sub-components to reduce App noise
   ───────────────────────────────────────────── */

function StatusBadge({ isTracing, currentPhase, colors }: StatusBadgeProps) {
  if (isTracing) {
    return (
      <span
        style={{
          fontSize: '9px',
          letterSpacing: '0.08em',
          padding: '3px 10px',
          borderRadius: '3px',
          backgroundColor: colors.bgElevated,
          border: `1px solid ${colors.accent}`,
          color: colors.accent,
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}
      >
        <span className="animate-pulse-dot" style={{ fontSize: '8px' }}>●</span>
        ANALYZING
      </span>
    );
  }
  if (currentPhase === ('PERSIST' as PhaseId)) {
    return (
      <span
        style={{
          fontSize: '9px',
          letterSpacing: '0.08em',
          padding: '3px 10px',
          borderRadius: '3px',
          backgroundColor: colors.bgElevated,
          border: `1px solid ${PHASE_COMPLETE_COLORS.border}`,
          color: PHASE_COMPLETE_COLORS.text,
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}
      >
        ✓ COMPLETE
      </span>
    );
  }
  return null;
}

function ModeToggle({
  effectiveMode, disabled, rcaCompleted, colors, onClick,
}: ModeToggleProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        fontFamily: 'inherit',
        fontSize: '9px',
        letterSpacing: '0.06em',
        padding: '3px 10px',
        borderRadius: '3px',
        backgroundColor: colors.bgElevated,
        border: `1px solid ${disabled ? colors.border : colors.textFaint}`,
        color: disabled ? colors.textFaint : colors.textMuted,
        cursor: disabled ? 'default' : 'pointer',
        transition: 'all 0.15s',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
      }}
    >
      <span
        style={{
          display: 'inline-block',
          width: 5,
          height: 5,
          borderRadius: '50%',
          backgroundColor: effectiveMode === 'chat' ? PHASE_COMPLETE_COLORS.text : colors.accent,
        }}
      />
      {rcaCompleted ? 'RCA + CHAT' : effectiveMode === 'chat' ? 'CHAT' : 'RCA'}
      {!rcaCompleted && (
        <>
          <span style={{ color: colors.border }}>|</span>
          <span style={{ color: disabled ? colors.textFaint : colors.textMuted }}>
            {effectiveMode === 'chat' ? 'RCA' : 'CHAT'}
          </span>
        </>
      )}
    </button>
  );
}

function EmptyState({ colors }: EmptyStateProps) {
  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <span style={{ fontSize: '12px', color: colors.textFaint }}>
        Select an incident to begin
      </span>
    </div>
  );
}

function LandingPanel({
  selectedId, incident, colors, onStartRca, onStartChat,
}: LandingPanelProps) {
  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '28px',
        padding: '40px',
        overflow: 'auto',
      }}
    >
      <div style={{ textAlign: 'center', maxWidth: 480 }}>
        <span style={{ fontSize: '10px', color: colors.textMuted, letterSpacing: '0.08em' }}>
          SELECTED INCIDENT
        </span>
        <h2 style={{ fontSize: '16px', color: colors.textPrimary, margin: '8px 0 6px', fontWeight: 600 }}>
          {selectedId}
        </h2>
        {incident && (
          <>
            <p style={{ fontSize: '12px', color: colors.textMuted, margin: '0 0 4px' }}>
              {incident.service}
            </p>
            <p style={{ fontSize: '11px', color: colors.textFaint, margin: 0, lineHeight: 1.5 }}>
              {incident.error}
            </p>
          </>
        )}
      </div>

      <div style={{ display: 'flex', gap: '16px' }}>
        <button
          onClick={onStartRca}
          style={{
            fontFamily: 'inherit',
            fontSize: '12px',
            padding: '10px 24px',
            borderRadius: '4px',
            backgroundColor: colors.bgElevated,
            border: `1px solid ${colors.accent}`,
            color: colors.accent,
            cursor: 'pointer',
            letterSpacing: '0.04em',
          }}
        >
          Start RCA
        </button>
        <button
          onClick={onStartChat}
          style={{
            fontFamily: 'inherit',
            fontSize: '12px',
            padding: '10px 24px',
            borderRadius: '4px',
            backgroundColor: colors.bgElevated,
            border: `1px solid ${colors.border}`,
            color: colors.textMuted,
            cursor: 'pointer',
            letterSpacing: '0.04em',
          }}
        >
          Chat
        </button>
      </div>

      <p style={{ fontSize: '9px', color: colors.textFaint, margin: 0, textAlign: 'center', maxWidth: 360, lineHeight: 1.6 }}>
        Start RCA runs the full 7-phase pipeline. Chat connects directly for follow-up questions.
      </p>
    </div>
  );
}

/**
 * SessionView — the active pipeline / chat area.
 *
 * Layout fix: this is a flex column that fills the remaining space.
 * - PhaseIndicator + progress bar: flexShrink 0 (fixed)
 * - MessageStream: flex 1 + minHeight 0 + overflow auto (scrollable)
 * - ChatInput + StatusBar: flexShrink 0 (fixed at bottom)
 *
 * This prevents the message list from pushing the input off-screen.
 */
function SessionView({
  messages, isTracing, isConnected, currentPhase,
  evidenceCount, hopCount, incidentId, colors, onSend,
}: SessionViewProps) {
  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        /* Critical: allow this container to shrink so children
           don't overflow the viewport */
        minHeight: 0,
        overflow: 'hidden',
      }}
    >
      {/* Phase indicator (fixed) */}
      <div style={{ flexShrink: 0 }}>
        <PhaseIndicator currentPhase={currentPhase} />
      </div>

      {/* Progress bar (fixed) */}
      <div style={{ height: 2, backgroundColor: colors.border, overflow: 'hidden', flexShrink: 0 }}>
        {isTracing && <div className="animate-progress" style={{ height: '100%', backgroundColor: colors.accent }} />}
        {!isTracing && currentPhase === ('PERSIST' as PhaseId) && (
          <div style={{ height: '100%', width: '100%', backgroundColor: PHASE_COMPLETE_COLORS.text, transition: 'width 0.5s ease' }} />
        )}
      </div>

      {/* Message stream (scrollable, takes remaining space) */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <MessageStream messages={messages} isTracing={isTracing} currentPhase={currentPhase} />
      </div>

      {/* Chat input (fixed at bottom) */}
      <div style={{ flexShrink: 0 }}>
        <ChatInput
          currentPhase={currentPhase}
          isTracing={isTracing}
          isConnected={isConnected}
          onSend={onSend}
        />
      </div>

      {/* Status bar (fixed at bottom) */}
      <div style={{ flexShrink: 0 }}>
        <StatusBar
          isTracing={isTracing}
          currentPhase={currentPhase}
          evidenceCount={evidenceCount}
          hopCount={hopCount}
          incidentId={incidentId}
        />
      </div>
    </div>
  );
}