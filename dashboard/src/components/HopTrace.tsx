import type { Hop } from '../types';

interface HopTraceProps {
  hops: Hop[];
}

export function HopTrace({ hops }: HopTraceProps) {
  return (
    <div
      style={{
        backgroundColor: '#0f172a',
        border: '1px solid #111827',
        borderRadius: '6px',
        padding: '10px 12px',
        fontFamily: 'IBM Plex Mono, monospace',
      }}
    >
      <div
        style={{
          fontSize: '9px',
          color: '#334155',
          letterSpacing: '0.1em',
          marginBottom: '8px',
          fontWeight: 600,
        }}
      >
        ONTOLOGY TRAVERSAL
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {hops.map((hop, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
            {/* Source node */}
            <span
              style={{
                backgroundColor: '#172554',
                color: '#93c5fd',
                fontSize: '10px',
                padding: '1px 6px',
                borderRadius: '3px',
                border: '1px solid #1e3a8a',
                whiteSpace: 'nowrap',
              }}
            >
              {hop.from}
            </span>

            {/* Edge label */}
            <span
              style={{
                color: '#fbbf24',
                fontSize: '9px',
                letterSpacing: '0.04em',
                whiteSpace: 'nowrap',
              }}
            >
              —[{hop.edge}]→
            </span>

            {/* Target node */}
            <span
              style={{
                backgroundColor: '#022c22',
                color: '#6ee7b7',
                fontSize: '10px',
                padding: '1px 6px',
                borderRadius: '3px',
                border: '1px solid #14532d',
                whiteSpace: 'nowrap',
              }}
            >
              {hop.to}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
