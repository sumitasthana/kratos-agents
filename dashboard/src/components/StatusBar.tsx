import type { PhaseId } from '../types';
import { useColors } from '../ThemeContext';

interface StatusBarProps {
  isTracing: boolean;
  currentPhase: PhaseId | null;
  evidenceCount: number;
  hopCount: number;
  incidentId: string | null;
}

export function StatusBar({ isTracing, currentPhase, evidenceCount, hopCount, incidentId }: StatusBarProps) {
  const c = useColors();
  return (
    <div
      style={{
        height: '28px',
        backgroundColor: c.bgElevated,
        borderTop: `1px solid ${c.border}`,
        display: 'flex',
        alignItems: 'center',
        padding: '0 16px',
        gap: '16px',
        fontFamily: 'IBM Plex Mono, monospace',
        fontSize: '10px',
        color: c.textMuted,
        flexShrink: 0,
      }}
    >
      {/* Trace status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
        <span
          style={{
            fontSize: '8px',
            color: isTracing ? c.accent : currentPhase ? c.success : c.textFaint,
          }}
          className={isTracing ? 'animate-pulse-dot' : ''}
        >
          ●
        </span>
        <span style={{ color: isTracing ? c.accentLight : currentPhase ? c.success : c.textFaint }}>
          {isTracing ? 'TRACING' : currentPhase ? 'COMPLETE' : 'IDLE'}
        </span>
      </div>

      <span style={{ color: c.border }}>|</span>

      {/* Incident */}
      {incidentId && (
        <>
          <span style={{ color: c.textSecondary }}>{incidentId}</span>
          <span style={{ color: c.border }}>|</span>
        </>
      )}

      {/* Evidence count */}
      <span>
        Evidence:{' '}
        <span style={{ color: c.textPrimary, fontWeight: 500 }}>{evidenceCount}</span>
      </span>

      <span style={{ color: c.border }}>|</span>

      {/* Hop count */}
      <span>
        Hops:{' '}
        <span style={{ color: c.textPrimary, fontWeight: 500 }}>{hopCount}</span>
      </span>

      {currentPhase && (
        <>
          <span style={{ color: c.border }}>|</span>
          <span>
            Phase:{' '}
            <span style={{ color: c.accentLight }}>{currentPhase}</span>
          </span>
        </>
      )}

      {/* Branding */}
      <div style={{ marginLeft: 'auto', color: c.textFaint, letterSpacing: '0.08em', fontSize: '9px' }}>
        KRATOS RCA ENGINE v2
      </div>
    </div>
  );
}
