import type { PhaseId } from '../types';
import { useColors } from '../ThemeContext';

const PHASES: PhaseId[] = [
  'INTAKE', 'LOGS_FIRST', 'ROUTE', 'BACKTRACK', 'INCIDENT_CARD', 'RECOMMEND', 'PERSIST',
];

const PHASE_LABELS: Record<PhaseId, string> = {
  INTAKE: 'INTAKE', LOGS_FIRST: 'LOGS', ROUTE: 'ROUTE', BACKTRACK: 'BACKTRACK',
  INCIDENT_CARD: 'INCIDENT', RECOMMEND: 'RECOMMEND', PERSIST: 'PERSIST',
};

interface PhaseIndicatorProps {
  currentPhase: PhaseId | null;
}

export function PhaseIndicator({ currentPhase }: PhaseIndicatorProps) {
  const c = useColors();
  const currentIndex = currentPhase ? PHASES.indexOf(currentPhase) : -1;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
        padding: '8px 16px',
        borderBottom: `1px solid ${c.border}`,
        backgroundColor: c.bgElevated,
      }}
    >
      {PHASES.map((phase, i) => {
        const isCompleted = i < currentIndex;
        const isCurrent = i === currentIndex;
        const isPending = i > currentIndex;

        const segColor = isCompleted ? c.success : isCurrent ? c.accent : c.borderSubtle;

        return (
          <div key={phase} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            {i > 0 && (
              <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '9px', color: c.textFaint }}>
                —
              </span>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <div
                style={{
                  width: '8px', height: '8px', borderRadius: '50%',
                  backgroundColor: segColor, flexShrink: 0,
                }}
              />
              <span
                style={{
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: '9px',
                  fontWeight: isCurrent ? 600 : 400,
                  color: isCompleted ? c.success : isCurrent ? c.accentLight : c.textFaint,
                  letterSpacing: '0.05em',
                }}
              >
                {PHASE_LABELS[phase]}
              </span>
            </div>
          </div>
        );
      })}

      {currentPhase && (
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <div
            className="animate-pulse-dot"
            style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: c.accent }}
          />
          <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px', color: c.accentLight }}>
            {currentPhase}
          </span>
        </div>
      )}
    </div>
  );
}
