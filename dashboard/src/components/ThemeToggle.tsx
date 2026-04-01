import type { ThemeMode, ThemeColors } from '../hooks/useTheme';

interface ThemeToggleProps {
  mode: ThemeMode;
  colors: ThemeColors;
  onCycle: () => void;
}

const ICONS: Record<ThemeMode, string> = {
  dark: '🌙',
  light: '☀️',
  system: '💻',
};

const LABELS: Record<ThemeMode, string> = {
  dark: 'Dark',
  light: 'Light',
  system: 'System',
};

export function ThemeToggle({ mode, colors, onCycle }: ThemeToggleProps) {
  return (
    <button
      onClick={onCycle}
      title={`Theme: ${LABELS[mode]} (click to cycle)`}
      style={{
        fontFamily: 'IBM Plex Mono, monospace',
        fontSize: '10px',
        padding: '4px 8px',
        borderRadius: '4px',
        backgroundColor: colors.bgCard,
        border: `1px solid ${colors.border}`,
        color: colors.textSecondary,
        cursor: 'pointer',
        transition: 'all 0.15s',
        display: 'flex',
        alignItems: 'center',
        gap: '5px',
        flexShrink: 0,
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = colors.accent;
        e.currentTarget.style.color = colors.accentLight;
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = colors.border;
        e.currentTarget.style.color = colors.textSecondary;
      }}
    >
      <span style={{ fontSize: '12px' }}>{ICONS[mode]}</span>
      <span>{LABELS[mode]}</span>
    </button>
  );
}
