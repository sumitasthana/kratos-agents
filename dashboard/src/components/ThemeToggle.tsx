import { useTheme, type Theme } from '../hooks/useTheme';

const MODES: { value: Theme; label: string; icon: string }[] = [
  { value: 'light',  label: 'Light',  icon: '☀' },
  { value: 'system', label: 'System', icon: '⬡' },
  { value: 'dark',   label: 'Dark',   icon: '☽' },
];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <div
      className="flex items-center gap-px rounded-md border border-slate-700 overflow-hidden"
      style={{ borderColor: 'var(--border-dim)' }}
      title="Theme"
    >
      {MODES.map(({ value, label, icon }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            onClick={() => setTheme(value)}
            title={label}
            aria-label={`${label} mode`}
            aria-pressed={active}
            style={{
              background: active ? 'var(--accent-blue)' : 'transparent',
              color: active ? '#fff' : 'var(--text-muted)',
              padding: '2px 6px',
              fontSize: '11px',
              lineHeight: 1,
              border: 'none',
              cursor: 'pointer',
              transition: 'background 0.15s, color 0.15s',
            }}
          >
            {icon}
          </button>
        );
      })}
    </div>
  );
}
