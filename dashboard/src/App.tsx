import { useState, useCallback } from 'react';
import { useRcaStream } from './hooks/useRcaStream';
import { useIncidents } from './hooks/useIncidents';
import { IncidentSidebar } from './components/IncidentSidebar';
import { PhaseIndicator } from './components/PhaseIndicator';
import { MessageStream } from './components/MessageStream';
import { ChatInput } from './components/ChatInput';
import { StatusBar } from './components/StatusBar';

export default function App() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const { incidents } = useIncidents();
  const { messages, isTracing, currentPhase, connect } = useRcaStream();

  const handleSelectIncident = useCallback(
    (id: string) => {
      setSelectedId(id);
      connect(id);
    },
    [connect]
  );

  const handleSend = useCallback((text: string) => {
    // Forward to WS or log for now
    console.log('[ChatInput]', text);
  }, []);

  // Derive evidence count and hop count from messages
  const evidenceCount = messages.filter(
    m => m.type === 'evidence' || (m.type === 'agent' && m.tag === 'evidence')
  ).length;
  const hopCount = messages
    .filter(m => m.type === 'hop')
    .reduce((acc, m) => acc + (m.type === 'hop' ? m.hops.length : 0), 0);

  return (
    <div
      style={{
        height: '100vh',
        display: 'flex',
        flexDirection: 'row',
        backgroundColor: '#030712',
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
            backgroundColor: '#0f172a',
            borderBottom: '1px solid #111827',
            padding: '8px 16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span
              style={{
                fontFamily: 'IBM Plex Mono, monospace',
                fontSize: '11px',
                color: '#3b82f6',
                fontWeight: 600,
                letterSpacing: '0.08em',
              }}
            >
              KRATOS
            </span>
            <span style={{ color: '#1e293b', fontSize: '10px' }}>|</span>
            <span
              style={{
                fontFamily: 'IBM Plex Mono, monospace',
                fontSize: '10px',
                color: '#64748b',
              }}
            >
              Root Cause Analysis Terminal
            </span>
          </div>
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

        {/* Phase indicator */}
        <PhaseIndicator currentPhase={currentPhase} />

        {/* Message stream */}
        <MessageStream messages={messages} isTracing={isTracing} />

        {/* Chat input */}
        <ChatInput
          currentPhase={currentPhase}
          isTracing={isTracing}
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
      </div>
    </div>
  );
}
