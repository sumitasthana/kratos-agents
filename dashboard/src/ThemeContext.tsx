import { createContext, useContext } from 'react';
import type { ThemeColors } from './hooks/useTheme';

// Default to dark theme colors
const DEFAULT: ThemeColors = {
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

export const ThemeContext = createContext<ThemeColors>(DEFAULT);

export function useColors(): ThemeColors {
  return useContext(ThemeContext);
}
