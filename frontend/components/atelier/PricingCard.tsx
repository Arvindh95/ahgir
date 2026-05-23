import Link from 'next/link'
import { ATELIER } from './theme'

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
  const t = ATELIER
  const cta = ctaLabel ?? (featured ? `Start with ${name} →` : `Choose ${name} →`)

  return (
    <div
      style={{
        padding: '36px 32px',
        background: featured ? t.ink : t.paper,
        color: featured ? t.paper : t.ink,
        border: featured ? 'none' : `1px solid ${t.border}`,
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
            letterSpacing: '0.16em',
            color: t.accent,
            textTransform: 'uppercase',
          }}
        >
          · most loved
        </div>
      )}
      <div
        style={{
          fontFamily: t.monoFont,
          fontSize: 10,
          letterSpacing: '0.16em',
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
          letterSpacing: '0.08em',
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
          color: featured ? `${t.paper}cc` : `${t.ink}cc`,
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
              borderTop: `1px solid ${featured ? `${t.paper}22` : `${t.ink}15`}`,
              fontFamily: t.bodyFont,
              fontSize: 13,
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
                background: featured ? t.accent : t.ink,
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
          background: featured ? t.paper : t.ink,
          color: featured ? t.ink : t.paper,
          border: 'none',
          fontFamily: t.bodyFont,
          fontSize: 14,
          fontWeight: 600,
          cursor: 'pointer',
          letterSpacing: '0.02em',
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
