/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['IBM Plex Sans', 'sans-serif'],
        mono: ['IBM Plex Mono', 'monospace'],
      },
      colors: {
        terminal: {
          bg:        '#030712',
          elevated:  '#0f172a',
          code:      '#080f1a',
          border:    '#111827',
          emphasis:  '#1e293b',
          primary:   '#e2e8f0',
          secondary: '#94a3b8',
          muted:     '#64748b',
          faint:     '#334155',
          blue:      '#3b82f6',
          'blue-light': '#93c5fd',
          green:     '#22c55e',
          red:       '#dc2626',
          orange:    '#ea580c',
          yellow:    '#fbbf24',
          amber:     '#ca8a04',
          teal:      '#6ee7b7',
        },
      },
      fontSize: {
        '2xs': ['9px', '1.2'],
        'xs':  ['10px', '1.3'],
        'sm':  ['11px', '1.4'],
        'base':['13px', '1.5'],
        'md':  ['12px', '1.4'],
      },
    },
  },
  plugins: [],
}

