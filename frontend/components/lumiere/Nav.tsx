import { useState } from 'react'
import Link from 'next/link'
import { Menu, X } from 'lucide-react'
import { LUMIERE } from './theme'

interface NavLink {
  label: string
  href: string
}

const LINKS: NavLink[] = [
  { label: 'Method', href: '/#method' },
  { label: 'Pricing', href: '/pricing' },
  { label: 'Security', href: '/security' },
  { label: 'Contact', href: '/contact' },
]

interface Props {
  sticky?: boolean
}

export default function Nav({ sticky = true }: Props) {
  const t = LUMIERE
  const [open, setOpen] = useState(false)

  return (
    <nav
      style={{
        position: sticky ? 'sticky' : 'static',
        top: 0,
        zIndex: 50,
        background: t.bg,
        borderBottom: `1px solid ${t.border}`,
      }}
    >
      <div
        className="px-6 sm:px-10 lg:px-16"
        style={{
          paddingTop: 18,
          paddingBottom: 18,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 24,
        }}
      >
        <Link
          href="/"
          style={{
            fontFamily: t.displayFont,
            fontStyle: 'italic',
            fontSize: 32,
            lineHeight: 1,
            color: t.ink,
            letterSpacing: '-0.01em',
            textDecoration: 'none',
          }}
        >
          Picur
        </Link>

        <div className="hidden md:flex" style={{ alignItems: 'center', gap: 36 }}>
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              style={{
                fontFamily: t.bodyFont,
                fontSize: 13,
                color: t.inkDim,
                textDecoration: 'none',
              }}
            >
              {l.label}
            </Link>
          ))}
          <Link
            href="/admin/login"
            style={{
              fontFamily: t.bodyFont,
              fontSize: 13,
              color: t.inkDim,
              textDecoration: 'none',
            }}
          >
            Sign in
          </Link>
          <Link
            href="/admin/register"
            style={{
              padding: '10px 22px',
              background: 'transparent',
              color: t.ink,
              border: `1px solid ${t.accent}`,
              fontFamily: t.bodyFont,
              fontSize: 13,
              fontWeight: 500,
              textDecoration: 'none',
              letterSpacing: '0.04em',
            }}
          >
            BEGIN —
          </Link>
        </div>

        <button
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpen((o) => !o)}
          className="md:hidden"
          style={{
            background: 'transparent',
            border: 'none',
            color: t.ink,
            padding: 6,
            cursor: 'pointer',
          }}
        >
          {open ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>

      {open && (
        <div
          className="md:hidden"
          style={{
            borderTop: `1px solid ${t.border}`,
            background: t.bg,
            padding: '12px 24px 24px',
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
          }}
        >
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              style={{
                fontFamily: t.bodyFont,
                fontSize: 15,
                color: t.ink,
                textDecoration: 'none',
                padding: '12px 0',
                borderBottom: `1px solid ${t.border}`,
              }}
            >
              {l.label}
            </Link>
          ))}
          <Link
            href="/admin/login"
            onClick={() => setOpen(false)}
            style={{
              fontFamily: t.bodyFont,
              fontSize: 15,
              color: t.ink,
              textDecoration: 'none',
              padding: '12px 0',
              borderBottom: `1px solid ${t.border}`,
            }}
          >
            Sign in
          </Link>
          <Link
            href="/admin/register"
            onClick={() => setOpen(false)}
            style={{
              marginTop: 14,
              padding: '14px 18px',
              background: t.accent,
              color: t.bg,
              fontFamily: t.bodyFont,
              fontSize: 14,
              fontWeight: 600,
              textDecoration: 'none',
              textAlign: 'center',
              letterSpacing: '0.04em',
            }}
          >
            BEGIN — FREE
          </Link>
        </div>
      )}
    </nav>
  )
}
