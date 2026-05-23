// Lumière — warm cinematic dark. Single source of truth.
// Mirrors the CSS vars in globals.css (`--lumiere-*`).
export const LUMIERE = {
  bg: '#0e0b08',
  paper: '#181410',
  ink: '#efe3cb',
  inkDim: '#c9bca0',
  muted: '#7e705b',
  accent: '#d4a574',
  accent2: '#8b6f4e',
  border: '#2a211a',
  displayFont: 'var(--font-display)',
  bodyFont: 'var(--font-body)',
  monoFont: 'var(--font-mono)',
} as const

export type LumiereTheme = typeof LUMIERE
