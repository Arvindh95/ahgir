import Link from 'next/link'
import { LUMIERE } from './theme'

interface FooterCol {
  h: string
  items: { label: string; href: string }[]
}

const COLS: FooterCol[] = [
  {
    h: 'PRODUCT',
    items: [
      { label: 'Method', href: '/#method' },
      { label: 'Pricing', href: '/pricing' },
      { label: 'Security', href: '/security' },
    ],
  },
  {
    h: 'COMPANY',
    items: [
      { label: 'Contact', href: '/contact' },
      { label: 'Get started', href: '/admin/register' },
      { label: 'Sign in', href: '/admin/login' },
    ],
  },
  {
    h: 'LEGAL',
    items: [
      { label: 'Privacy', href: '/privacy' },
      { label: 'Terms', href: '/terms' },
    ],
  },
]

export default function Footer() {
  const t = LUMIERE
  const year = new Date().getFullYear()

  return (
    <footer
      className="px-6 sm:px-10 lg:px-16"
      style={{
        paddingTop: 64,
        paddingBottom: 32,
        borderTop: `1px solid ${t.border}`,
        background: t.bg,
        color: t.ink,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          gap: 60,
          marginBottom: 60,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ maxWidth: 360, flex: '1 1 280px' }}>
          <div
            style={{
              fontFamily: t.displayFont,
              fontStyle: 'italic',
              fontSize: 44,
              lineHeight: 1,
              marginBottom: 16,
            }}
          >
            Picur
          </div>
          <p
            style={{
              fontFamily: t.bodyFont,
              fontSize: 14,
              lineHeight: 1.6,
              color: t.inkDim,
              margin: 0,
              fontStyle: 'italic',
            }}
          >
            A quiet little tool that delivers wedding photos to the people in them — and only the people in them.
          </p>
        </div>
        <div
          className="grid grid-cols-2 sm:grid-cols-3"
          style={{ gap: 40, flex: '1 1 360px' }}
        >
          {COLS.map((col) => (
            <div key={col.h}>
              <div
                style={{
                  fontFamily: t.monoFont,
                  fontSize: 10,
                  letterSpacing: '0.22em',
                  color: t.accent,
                  marginBottom: 18,
                }}
              >
                {col.h}
              </div>
              <ul
                style={{
                  listStyle: 'none',
                  padding: 0,
                  margin: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                }}
              >
                {col.items.map((it) => (
                  <li key={it.label}>
                    <Link
                      href={it.href}
                      style={{
                        fontFamily: t.bodyFont,
                        fontSize: 14,
                        color: t.inkDim,
                        textDecoration: 'none',
                      }}
                    >
                      {it.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
      <div
        style={{
          paddingTop: 24,
          borderTop: `1px solid ${t.border}`,
          display: 'flex',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
          fontFamily: t.monoFont,
          fontSize: 10,
          letterSpacing: '0.16em',
          color: t.muted,
          textTransform: 'uppercase',
        }}
      >
        <span>© {year} PICUR · A QUIET LITTLE TOOL</span>
        <a
          href="mailto:support@picur.my"
          style={{ color: t.muted, textDecoration: 'none' }}
        >
          SUPPORT@PICUR.MY
        </a>
      </div>
    </footer>
  )
}
