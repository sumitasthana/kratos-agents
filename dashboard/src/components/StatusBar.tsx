import type { PhaseId } from '../types';

interface StatusBarProps {
  isTracing: boolean;
  currentPhase: PhaseId | null;
  evidenceCount: number;
  hopCount: number;
  incidentId: string | null;
}

export function StatusBar({ isTracing, currentPhase, evidenceCount, hopCount, incidentId }: StatusBarProps) {
  return (
    <div
      style={{
        height: '28px',
        backgroundColor: '#0f172a',
        borderTop: '1px solid #111827',
        display: 'flex',
        alignItems: 'center',
        padding: '0 16px',
        gap: '16px',
        fontFamily: 'IBM Plex Mono, monospace',
        fontSize: '10px',
        color: '#64748b',
        flexShrink: 0,
      }}
    >
      {/* Trace status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
        <span
          style={{
            fontSize: '8px',
            color: isTracing ? '#3b82f6' : currentPhase ? '#22c55e' : '#334155',
          }}
          className={isTracing ? 'animate-pulse-dot' : ''}
        >
          ●
        </span>
        <span style={{ color: isTracing ? '#93c5fd' : currentPhase ? '#22c55e' : '#334155' }}>
          {isTracing ? 'TRACING' : currentPhase ? 'COMPLETE' : 'IDLE'}
        </span>
      </div>

      <span style={{ color: '#1e293b' }}>|</span>

      {/* Incident */}
      {incidentId && (
        <>
          <span style={{ color: '#94a3b8' }}>{incidentId}</span>
          <span style={{ color: '#1e293b' }}>|</span>
        </>
      )}

      {/* Evidence count */}
      <span>
        Evidence:{' '}
        <span style={{ color: '#e2e8f0', fontWeight: 500 }}>{evidenceCount}</span>
      </span>

      <span style={{ color: '#1e293b' }}>|</span>

      {/* Hop count */}
      <span>
        Hops:{' '}
        <span style={{ color: '#e2e8f0', fontWeight: 500 }}>{hopCount}</span>
      </span>

      {currentPhase && (
        <>
          <span style={{ color: '#1e293b' }}>|</span>
          <span>
            Phase:{' '}
            <span style={{ color: '#93c5fd' }}>{currentPhase}</span>
          </span>
        </>
      )}

      {/* Branding */}
      <div style={{ marginLeft: 'auto', color: '#334155', letterSpacing: '0.08em', fontSize: '9px' }}>
        KRATOS RCA ENGINE v2
      </div>
    </div>
  );
}
