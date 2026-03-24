interface EvidenceBlockProps {
  source: string;
  filename: string;
  language: string;
  defect: string;
  code: string;
}

function highlightCode(code: string): string {
  // Basic syntax highlighting via span replacement — safe, no innerHTML from user data
  return code
    .split('\n')
    .map(line => {
      let safe = line
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

      // COBOL comments (lines starting with * in col 7 area or *>)
      if (/^\d*\s*\*/.test(safe)) {
        return `<span style="color:#64748b">${safe}</span>`;
      }

      // Keywords
      safe = safe.replace(
        /\b(PIC|VALUE|05|SECTION|DIVISION|PERFORM|MOVE|IF|ELSE|END-IF|COMPUTE|DISPLAY)\b/g,
        '<span style="color:#93c5fd">$1</span>'
      );

      // String literals
      safe = safe.replace(
        /('([^']*)')/g,
        '<span style="color:#fbbf24">$1</span>'
      );

      return safe;
    })
    .join('\n');
}

export function EvidenceBlock({ source, filename, language, defect, code }: EvidenceBlockProps) {
  return (
    <div
      style={{
        border: '1px solid #111827',
        borderRadius: '6px',
        overflow: 'hidden',
        fontFamily: 'IBM Plex Mono, monospace',
      }}
    >
      {/* Header */}
      <div
        style={{
          backgroundColor: '#0f172a',
          borderBottom: '1px solid #111827',
          padding: '6px 12px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          flexWrap: 'wrap',
        }}
      >
        <span style={{ fontSize: '10px', color: '#94a3b8', fontWeight: 500 }}>{source}</span>
        <span style={{ color: '#334155', fontSize: '10px' }}>·</span>
        <span style={{ fontSize: '10px', color: '#e2e8f0' }}>{filename}</span>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: '6px' }}>
          <span
            style={{
              fontSize: '9px',
              padding: '1px 5px',
              borderRadius: '3px',
              backgroundColor: '#172554',
              border: '1px solid #1e3a8a',
              color: '#93c5fd',
              letterSpacing: '0.04em',
            }}
          >
            {language}
          </span>
          <span
            style={{
              fontSize: '9px',
              padding: '1px 5px',
              borderRadius: '3px',
              backgroundColor: '#2a1215',
              border: '1px solid #dc2626',
              color: '#fca5a5',
              letterSpacing: '0.04em',
            }}
          >
            {defect}
          </span>
        </div>
      </div>

      {/* Code body */}
      <pre
        style={{
          margin: 0,
          padding: '10px 12px',
          backgroundColor: '#080f1a',
          fontSize: '11px',
          lineHeight: '1.6',
          overflowX: 'auto',
          color: '#e2e8f0',
        }}
        dangerouslySetInnerHTML={{ __html: highlightCode(code) }}
      />
    </div>
  );
}
