import type { Incident, Priority } from '../types';
import { useColors } from '../ThemeContext';

const PRIORITY_STYLE: Record<Priority, { bg: string; border: string; text: string; label: string }> = {
  P1: { bg: '#2a1215', border: '#dc2626', text: '#fca5a5', label: 'P1' },
  P2: { bg: '#271507', border: '#ea580c', text: '#fdba74', label: 'P2' },
  P3: { bg: '#1a1a06', border: '#ca8a04', text: '#fde047', label: 'P3' },
  P4: { bg: '#0a1a14', border: '#16a34a', text: '#86efac', label: 'P4' },
};

interface IncidentSidebarProps {
  incidents: Incident[];
  selectedId: string | null;
  collapsed: boolean;
  onSelect: (id: string) => void;
  onToggle: () => void;
}

const FALLBACK_STYLE = { bg: '#1a1a2e', border: '#6366f1', text: '#a5b4fc', label: '??' };

function SeverityBadge({ severity }: { severity: Priority }) {
  const s = PRIORITY_STYLE[severity] ?? FALLBACK_STYLE;
  return (
    <span
      style={{
        fontFamily: 'IBM Plex Mono, monospace',
        fontSize: '9px',
        padding: '1px 5px',
        borderRadius: '3px',
        backgroundColor: s.bg,
        border: `1px solid ${s.border}`,
        color: s.text,
        flexShrink: 0,
        letterSpacing: '0.04em',
      }}
    >
      {s.label}
    </span>
  );
}

export function IncidentSidebar({
  incidents,
  selectedId,
  collapsed,
  onSelect,
  onToggle,
}: IncidentSidebarProps) {
  const c = useColors();
  const activeCount = incidents.filter(i => i.status === 'active').length;

  if (collapsed) {
    return (
      <div
        style={{
          width: '32px',
          flexShrink: 0,
          borderRight: `1px solid ${c.border}`,
          backgroundColor: c.bgElevated,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          paddingTop: '12px',
        }}
      >
        <button
          onClick={onToggle}
          title="Expand sidebar"
          style={{
            background: 'none',
            border: 'none',
            color: '#64748b',
            cursor: 'pointer',
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: '12px',
            padding: '4px',
          }}
        >
          ▸
        </button>
      </div>
    );
  }

  return (
    <div
      style={{
        width: '280px',
        flexShrink: 0,
        borderRight: `1px solid ${c.border}`,
        backgroundColor: c.bgElevated,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '10px 14px',
          borderBottom: `1px solid ${c.border}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
          <span
            className="animate-pulse-dot"
            style={{ color: c.accent, fontSize: '8px' }}
          >
            ●
          </span>
          <span
            style={{
              fontFamily: 'IBM Plex Mono, monospace',
              fontSize: '9px',
              color: c.textSecondary,
              letterSpacing: '0.1em',
              fontWeight: 600,
            }}
          >
            INCIDENTS
          </span>
        </div>
        <button
          onClick={onToggle}
          title="Collapse sidebar"
          style={{
            background: 'none',
            border: 'none',
            color: c.textMuted,
            cursor: 'pointer',
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: '12px',
            padding: '2px 4px',
          }}
        >
          ◂
        </button>
      </div>

      {/* Incident list */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {incidents.map(incident => {
          const isSelected = incident.id === selectedId;
          return (
            <button
              key={incident.id}
              onClick={() => onSelect(incident.id)}
              style={{
                width: '100%',
                textAlign: 'left',
                background: isSelected ? c.bg : 'none',
                border: 'none',
                borderBottom: `1px solid ${c.border}`,
                borderLeft: isSelected ? `2px solid ${c.accent}` : '2px solid transparent',
                padding: '10px 12px',
                cursor: 'pointer',
                display: 'block',
              }}
            >
              {/* Service + badge */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: '4px',
                }}
              >
                <span
                  style={{
                    fontFamily: 'IBM Plex Mono, monospace',
                    fontSize: '10px',
                    color: isSelected ? c.textPrimary : c.textSecondary,
                    fontWeight: isSelected ? 600 : 400,
                  }}
                >
                  {incident.service}
                </span>
                <SeverityBadge severity={incident.severity} />
              </div>

              {/* Error text */}
              <p
                style={{
                  margin: '0 0 5px 0',
                  fontSize: '11px',
                  color: c.textMuted,
                  lineHeight: '1.4',
                  overflow: 'hidden',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                }}
              >
                {incident.error}
              </p>

              {/* Control ID + status */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: '9px',
                  color: c.textFaint,
                }}
              >
                <span>{incident.control_id || incident.id.slice(0, 12)}</span>
                <span style={{ color: incident.status === 'active' ? c.error : c.textFaint }}>
                  {incident.status}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Footer */}
      <div
        style={{
          padding: '7px 14px',
          borderTop: `1px solid ${c.border}`,
          display: 'flex',
          justifyContent: 'space-between',
          fontFamily: 'IBM Plex Mono, monospace',
          fontSize: '9px',
          color: c.textFaint,
        }}
      >
        <span>Total: {incidents.length}</span>
        <span style={{ color: activeCount > 0 ? c.error : c.textFaint }}>
          Active: {activeCount}
        </span>
      </div>
    </div>
  );
}
