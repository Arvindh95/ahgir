// Atelier — cream editorial palette. Single source of truth for the theme.
// Values mirror the CSS vars in globals.css (`--atelier-*`) so JS callers can
// pass them as inline-style colors and CSS callers can use the vars.
export const ATELIER = {
  bg: '#f4ecdc',
  paper: '#faf5e7',
  ink: '#1f1813',
  muted: '#857560',
  accent: '#b85a3c',
  accent2: '#5c6e4a',
  border: '#d8c9ae',
  displayFont: 'var(--font-display)',
  bodyFont: 'var(--font-body)',
  monoFont: 'var(--font-mono)',
} as const

export type AtelierTheme = typeof ATELIER
