interface TriangulationCardProps {
  confidence: number;
  rootCause: string;
  regulation: string;
  defect: string;
}

export function TriangulationCard({ confidence, rootCause, regulation, defect }: TriangulationCardProps) {
  const pct = Math.round(confidence * 100);

  return (
    <div
      style={{
        backgroundColor: '#052e16',
        border: '1px solid #14532d',
        borderRadius: '6px',
        padding: '12px 14px',
        fontFamily: 'IBM Plex Sans, sans-serif',
      }}
    >
      {/* Title row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '10px',
        }}
      >
        <span
          style={{
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: '9px',
            color: '#22c55e',
            letterSpacing: '0.1em',
            fontWeight: 600,
          }}
        >
          ROOT CAUSE TRIANGULATION
        </span>
        <span
          style={{
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: '12px',
            color: '#22c55e',
            fontWeight: 600,
          }}
        >
          {pct}%
        </span>
      </div>

      {/* Confidence bar */}
      <div
        style={{
          height: '3px',
          backgroundColor: '#14532d',
          borderRadius: '2px',
          marginBottom: '12px',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${pct}%`,
            backgroundColor: '#22c55e',
            borderRadius: '2px',
          }}
        />
      </div>

      {/* Root cause */}
      <p
        style={{
          fontSize: '12px',
          color: '#e2e8f0',
          lineHeight: '1.6',
          margin: '0 0 10px 0',
        }}
      >
        {rootCause}
      </p>

      {/* Badges */}
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
        <span
          style={{
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: '9px',
            padding: '2px 7px',
            borderRadius: '3px',
            backgroundColor: '#172554',
            border: '1px solid #1e3a8a',
            color: '#93c5fd',
          }}
        >
          {regulation}
        </span>
        <span
          style={{
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: '9px',
            padding: '2px 7px',
            borderRadius: '3px',
            backgroundColor: '#2a1215',
            border: '1px solid #dc2626',
            color: '#fca5a5',
          }}
        >
          {defect}
        </span>
      </div>
    </div>
  );
}
