import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: '#0f172a',
        panel: '#111827',
        panelAlt: '#172033',
        accent: '#38bdf8',
        positive: '#22c55e',
        negative: '#ef4444',
        warning: '#f59e0b',
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(56, 189, 248, 0.14), 0 18px 40px rgba(15, 23, 42, 0.45)',
      },
    },
  },
  plugins: [],
} satisfies Config;

