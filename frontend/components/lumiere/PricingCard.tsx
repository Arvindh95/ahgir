import Link from 'next/link'
import { LUMIERE } from './theme'

interface Props {
  name: string
  price: string
  period: string
  desc: string
  features: string[]
  featured?: boolean
  ctaHref?: string
  ctaLabel?: string
}

export default function PricingCard({
  name,
  price,
  period,
  desc,
  features,
  featured,
  ctaHref = '/admin/register',
  ctaLabel,
}: Props) {
  const t = LUMIERE
  const cta = ctaLabel ?? (featured ? `BEGIN — ${name.toUpperCase()}` : `CHOOSE ${name.toUpperCase()}`)
  const bg = featured ? t.paper : t.bg
  const borderColor = featured ? t.accent : t.border

  return (
    <div
      style={{
        padding: '36px 32px',
        background: bg,
        color: t.ink,
        border: `1px solid ${borderColor}`,
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        minHeight: 440,
      }}
    >
      {featured && (
        <div
          style={{
            position: 'absolute',
            top: 16,
            right: 16,
            fontFamily: t.monoFont,
            fontSize: 9,
            letterSpacing: '0.18em',
            color: t.accent,
            textTransform: 'uppercase',
          }}
        >
          · MOST LOVED
        </div>
      )}
      <div
        style={{
          fontFamily: t.monoFont,
          fontSize: 10,
          letterSpacing: '0.18em',
          color: t.muted,
          textTransform: 'uppercase',
          marginBottom: 18,
        }}
      >
        {name}
      </div>
      <div
        style={{
          fontFamily: t.displayFont,
          fontStyle: 'italic',
          fontSize: 64,
          lineHeight: 1,
          color: featured ? t.accent : t.ink,
          marginBottom: 4,
        }}
      >
        {price}
      </div>
      <div
        style={{
          fontFamily: t.monoFont,
          fontSize: 11,
          color: t.muted,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          marginBottom: 24,
        }}
      >
        {period}
      </div>
      <div
        style={{
          fontFamily: t.bodyFont,
          fontSize: 14,
          lineHeight: 1.5,
          color: t.inkDim,
          marginBottom: 28,
          fontStyle: 'italic',
        }}
      >
        {desc}
      </div>
      <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 28px', flex: 1 }}>
        {features.map((f) => (
          <li
            key={f}
            style={{
              padding: '10px 0',
              borderTop: `1px solid ${t.border}`,
              fontFamily: t.bodyFont,
              fontSize: 13,
              color: t.inkDim,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
            }}
          >
            <span
              style={{
                width: 4,
                height: 4,
                borderRadius: '50%',
                background: t.accent,
                flex: '0 0 auto',
              }}
            />
            {f}
          </li>
        ))}
      </ul>
      <Link
        href={ctaHref}
        style={{
          padding: '14px 20px',
          background: featured ? t.accent : 'transparent',
          color: featured ? t.bg : t.ink,
          border: featured ? 'none' : `1px solid ${t.ink}55`,
          fontFamily: t.bodyFont,
          fontSize: 13,
          fontWeight: 600,
          letterSpacing: '0.04em',
          textDecoration: 'none',
          textAlign: 'center',
          display: 'block',
        }}
      >
        {cta}
      </Link>
    </div>
  )
}
