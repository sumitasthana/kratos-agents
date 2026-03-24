import type { RecommendationItem, Priority } from '../types';

const PRIORITY_STYLE: Record<Priority, { bg: string; border: string; text: string; label: string }> = {
  P1: { bg: '#2a1215', border: '#dc2626', text: '#fca5a5', label: 'Critical' },
  P2: { bg: '#271507', border: '#ea580c', text: '#fdba74', label: 'High' },
  P3: { bg: '#1a1a06', border: '#ca8a04', text: '#fde047', label: 'Medium' },
  P4: { bg: '#0a1a14', border: '#16a34a', text: '#86efac', label: 'Low' },
};

interface RecommendationCardProps {
  items: RecommendationItem[];
}

function PriorityBadge({ priority }: { priority: Priority }) {
  const s = PRIORITY_STYLE[priority];
  return (
    <span
      style={{
        fontFamily: 'IBM Plex Mono, monospace',
        fontSize: '9px',
        padding: '2px 6px',
        borderRadius: '3px',
        backgroundColor: s.bg,
        border: `1px solid ${s.border}`,
        color: s.text,
        flexShrink: 0,
        letterSpacing: '0.04em',
      }}
    >
      {priority} {s.label}
    </span>
  );
}

export function RecommendationCard({ items }: RecommendationCardProps) {
  return (
    <div
      style={{
        border: '1px solid #111827',
        borderRadius: '6px',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          backgroundColor: '#0f172a',
          borderBottom: '1px solid #111827',
          padding: '7px 12px',
        }}
      >
        <span
          style={{
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: '9px',
            color: '#94a3b8',
            letterSpacing: '0.1em',
            fontWeight: 600,
          }}
        >
          RECOMMENDATIONS
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {items.map((item, i) => (
          <div
            key={i}
            style={{
              padding: '10px 12px',
              borderBottom: i < items.length - 1 ? '1px solid #111827' : 'none',
              backgroundColor: '#030712',
            }}
          >
            {/* Priority + action */}
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', marginBottom: '6px' }}>
              <PriorityBadge priority={item.priority} />
              <span style={{ fontSize: '12px', color: '#e2e8f0', lineHeight: '1.5' }}>
                {item.action}
              </span>
            </div>

            {/* Meta row */}
            <div
              style={{
                display: 'flex',
                gap: '12px',
                flexWrap: 'wrap',
                fontFamily: 'IBM Plex Mono, monospace',
                fontSize: '10px',
                color: '#64748b',
              }}
            >
              <span>Owner: <span style={{ color: '#94a3b8' }}>{item.owner}</span></span>
              <span>Effort: <span style={{ color: '#94a3b8' }}>{item.effort}</span></span>
              {item.regulation && (
                <span
                  style={{
                    color: '#93c5fd',
                    backgroundColor: '#172554',
                    border: '1px solid #1e3a8a',
                    padding: '0px 5px',
                    borderRadius: '3px',
                  }}
                >
                  {item.regulation}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
