import { useState, useEffect, useCallback } from 'react';

export type ThemeMode = 'dark' | 'light' | 'system';

export interface ThemeColors {
  bg: string;
  bgElevated: string;
  bgCard: string;
  border: string;
  borderSubtle: string;
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  textFaint: string;
  accent: string;
  accentLight: string;
  success: string;
  error: string;
  warning: string;
}

const DARK: ThemeColors = {
  bg: '#030712',
  bgElevated: '#0f172a',
  bgCard: '#0d1017',
  border: '#111827',
  borderSubtle: '#1e293b',
  textPrimary: '#e2e8f0',
  textSecondary: '#94a3b8',
  textMuted: '#64748b',
  textFaint: '#334155',
  accent: '#3b82f6',
  accentLight: '#93c5fd',
  success: '#22c55e',
  error: '#dc2626',
  warning: '#ea580c',
};

const LIGHT: ThemeColors = {
  bg: '#f8fafc',
  bgElevated: '#ffffff',
  bgCard: '#f1f5f9',
  border: '#e2e8f0',
  borderSubtle: '#cbd5e1',
  textPrimary: '#0f172a',
  textSecondary: '#475569',
  textMuted: '#64748b',
  textFaint: '#94a3b8',
  accent: '#2563eb',
  accentLight: '#3b82f6',
  success: '#16a34a',
  error: '#dc2626',
  warning: '#ea580c',
};

function getSystemPreference(): 'dark' | 'light' {
  if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: light)').matches) {
    return 'light';
  }
  return 'dark';
}

function resolveColors(mode: ThemeMode): ThemeColors {
  if (mode === 'light') return LIGHT;
  if (mode === 'dark') return DARK;
  return getSystemPreference() === 'light' ? LIGHT : DARK;
}

export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem('kratos-theme') as ThemeMode | null;
    return saved ?? 'dark';
  });

  const colors = resolveColors(mode);
  const isDark = colors === DARK;

  const cycleTheme = useCallback(() => {
    setMode(prev => {
      const next: ThemeMode = prev === 'dark' ? 'light' : prev === 'light' ? 'system' : 'dark';
      localStorage.setItem('kratos-theme', next);
      return next;
    });
  }, []);

  // Listen for system preference changes when in 'system' mode
  useEffect(() => {
    if (mode !== 'system') return;
    const mq = window.matchMedia('(prefers-color-scheme: light)');
    const handler = () => setMode('system'); // force re-render
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [mode]);

  // Apply to document for scrollbar styling etc.
  useEffect(() => {
    document.documentElement.style.backgroundColor = colors.bg;
    document.body.style.backgroundColor = colors.bg;
    document.body.style.color = colors.textPrimary;
  }, [colors]);

  return { mode, colors, isDark, cycleTheme };
}
