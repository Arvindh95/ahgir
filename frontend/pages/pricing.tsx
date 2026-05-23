import Head from 'next/head'
import Link from 'next/link'
import { useState } from 'react'
import { AtelierLayout, ATELIER, PricingCard } from '@/components/atelier'

type Interval = 'month' | 'year'

interface Tier {
  key: string
  name: string
  monthlyUSD: number
  yearlyUSD: number
  description: string
  features: string[]
  ctaHref: string
  featured?: boolean
}

const TIERS: Tier[] = [
  {
    key: 'free',
    name: 'Free',
    monthlyUSD: 0,
    yearlyUSD: 0,
    description: 'For a first taste — try one event, on us.',
    features: [
      '1 active event',
      '25 photos per event',
      '30-day retention',
      'Face recognition',
      'Guest scanning',
      'Photo downloads',
    ],
    ctaHref: '/admin/register',
  },
  {
    key: 'starter',
    name: 'Starter',
    monthlyUSD: 9,
    yearlyUSD: 90,
    description: 'For photographers running a few small events at a time.',
    features: [
      '5 active events',
      '250 photos per event',
      '6-month retention',
      'Face recognition',
      'Guest scanning',
      'Photo downloads',
    ],
    ctaHref: '/admin/register?plan=starter',
    featured: true,
  },
  {
    key: 'pro',
    name: 'Pro',
    monthlyUSD: 29,
    yearlyUSD: 290,
    description: 'For studios managing many events year-round.',
    features: [
      '20 active events',
      '500 photos per event',
      '1-year retention',
      'Face recognition',
      'Guest scanning',
      'Photo downloads',
      'Priority indexing',
    ],
    ctaHref: '/admin/register?plan=pro',
  },
]

const COMPARISON: [string, string, string, string][] = [
  ['Active events', '1', '5', '20'],
  ['Photos per event', '25', '250', '500'],
  ['Retention window', '30 days', '6 months', '1 year'],
  ['Face recognition', '✓', '✓', '✓'],
  ['Guest scanning', '✓', '✓', '✓'],
  ['Photo downloads', '✓', '✓', '✓'],
  ['Priority indexing', '—', '—', '✓'],
  ['Email support', '✓', '✓', '✓'],
]

const FAQS = [
  {
    q: 'Do my guests need an app?',
    a: 'No. A web link or QR code works on any phone with a camera. We deliberately avoid app installs.',
  },
  {
    q: 'What happens to face data after the event?',
    a: 'Embeddings (numerical vectors, not photos) auto-delete on the retention date you choose. Encrypted backups roll off within seven days.',
  },
  {
    q: 'Can I run a single one-off event instead of subscribing?',
    a: 'Yes — we offer custom one-time packages tailored to your photo count and retention window. Email support@picur.my with your event details.',
  },
  {
    q: 'What if someone refuses to scan?',
    a: 'They can still browse the full gallery. Face matching is a shortcut, not a gate.',
  },
  {
    q: 'Do you train AI on our photos?',
    a: 'No, ever. We run our own face-embedding model (CompreFace) on hardware we own — your photos never leave our servers, and never enter anyone’s training set.',
  },
]

export default function Pricing() {
  const t = ATELIER
  const [billing, setBilling] = useState<Interval>('month')

  const cardsData = TIERS.map((tier) => ({
    name: tier.name,
    price: tier.key === 'free' ? '$0' : billing === 'year' ? `$${tier.yearlyUSD}` : `$${tier.monthlyUSD}`,
    period: tier.key === 'free' ? 'FOREVER' : billing === 'year' ? 'PER YEAR' : 'PER MONTH',
    desc: tier.description,
    features: tier.features,
    featured: tier.featured,
    ctaHref: tier.ctaHref,
  }))

  return (
    <AtelierLayout>
      <Head>
        <meta
          name="description"
          content="PicUr Pricing — simple, transparent plans for event photographers. Free, $9/mo Starter, $29/mo Pro."
        />
      </Head>

      <style>{`
        .atelier-pricing-h1 { font-size: clamp(48px, 10vw, 132px); line-height: 0.92; letter-spacing: -0.025em; }
        .atelier-pricing-h2 { font-size: clamp(32px, 5vw, 64px); line-height: 0.95; letter-spacing: -0.02em; }
      `}</style>

      {/* ========== HERO ========== */}
      <section className="px-6 sm:px-10 lg:px-16 pt-16 pb-8 lg:pt-20 text-center">
        <div className="max-w-[1100px] mx-auto">
          <div
            style={{
              fontFamily: t.monoFont,
              fontSize: 11,
              letterSpacing: '0.22em',
              color: t.accent,
              marginBottom: 18,
              textTransform: 'uppercase',
            }}
          >
            · PRICING · NO STARS · NO ASTERISKS
          </div>
          <h1
            className="atelier-pricing-h1"
            style={{ fontFamily: t.displayFont, fontWeight: 400, margin: 0 }}
          >
            Plans built for the
            <br />
            <span style={{ fontStyle: 'italic' }}>working photographer.</span>
          </h1>
          <p
            className="mx-auto"
            style={{
              fontFamily: t.displayFont,
              fontStyle: 'italic',
              fontSize: 'clamp(18px, 2.2vw, 24px)',
              color: `${t.ink}aa`,
              maxWidth: 620,
              margin: '28px auto 0',
              lineHeight: 1.4,
            }}
          >
            Start free. Upgrade when you book your next wedding. Downgrade anytime. We don&apos;t hold your photos hostage.
          </p>
        </div>
      </section>

      {/* ========== BETA BANNER ========== */}
      <section className="px-6 sm:px-10 lg:px-16">
        <div
          className="max-w-[820px] mx-auto"
          style={{
            padding: '24px 28px',
            background: t.paper,
            border: `1px solid ${t.border}`,
          }}
        >
          <div className="flex flex-col sm:flex-row sm:items-start gap-4">
            <span
              style={{
                flex: '0 0 auto',
                padding: '6px 12px',
                background: t.accent,
                color: t.paper,
                fontFamily: t.monoFont,
                fontSize: 10,
                letterSpacing: '0.16em',
                fontWeight: 600,
                borderRadius: 999,
              }}
            >
              BETA · ON US
            </span>
            <div>
              <div
                style={{
                  fontFamily: t.displayFont,
                  fontStyle: 'italic',
                  fontSize: 22,
                  color: t.ink,
                  marginBottom: 6,
                }}
              >
                We&apos;re in beta — your event is on us.
              </div>
              <p
                style={{
                  fontFamily: t.bodyFont,
                  fontSize: 14,
                  color: `${t.ink}aa`,
                  lineHeight: 1.55,
                  margin: '0 0 8px',
                }}
              >
                PicUr is currently in beta while we test the platform under real event traffic. During this period we offer free tailor-made event packages in exchange for honest feedback. Tell us what you need.
              </p>
              <Link
                href="/contact"
                style={{
                  fontFamily: t.bodyFont,
                  fontSize: 14,
                  color: t.accent,
                  borderBottom: `1px solid ${t.accent}`,
                  paddingBottom: 1,
                  textDecoration: 'none',
                }}
              >
                Contact us for free beta access →
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ========== BILLING TOGGLE + TIERS ========== */}
      <section className="px-6 sm:px-10 lg:px-16 pt-12 pb-20 lg:pb-24">
        <div className="max-w-[1280px] mx-auto">
          <div className="flex justify-center mb-12">
            <div
              style={{
                display: 'inline-flex',
                background: t.paper,
                border: `1px solid ${t.border}`,
                borderRadius: 999,
                padding: 4,
              }}
            >
              <button
                onClick={() => setBilling('month')}
                style={{
                  padding: '10px 20px',
                  background: billing === 'month' ? t.ink : 'transparent',
                  color: billing === 'month' ? t.paper : t.muted,
                  border: 'none',
                  borderRadius: 999,
                  fontFamily: t.bodyFont,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Monthly
              </button>
              <button
                onClick={() => setBilling('year')}
                style={{
                  padding: '10px 20px',
                  background: billing === 'year' ? t.ink : 'transparent',
                  color: billing === 'year' ? t.paper : t.muted,
                  border: 'none',
                  borderRadius: 999,
                  fontFamily: t.bodyFont,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                Yearly
                <span
                  style={{
                    fontFamily: t.monoFont,
                    fontSize: 10,
                    color: billing === 'year' ? t.accent : t.muted,
                    letterSpacing: '0.08em',
                  }}
                >
                  SAVE ~17%
                </span>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3">
            {cardsData.map((p) => (
              <PricingCard key={p.name} {...p} />
            ))}
          </div>
        </div>
      </section>

      {/* ========== COMPARISON TABLE ========== */}
      <section className="px-6 sm:px-10 lg:px-16 py-16 lg:py-20">
        <div className="max-w-[1100px] mx-auto">
          <h2
            className="atelier-pricing-h2"
            style={{
              fontFamily: t.displayFont,
              fontWeight: 400,
              margin: '0 0 32px',
            }}
          >
            Compare <span style={{ fontStyle: 'italic' }}>everything</span>
          </h2>
          <div style={{ overflowX: 'auto' }}>
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                fontFamily: t.bodyFont,
                fontSize: 14,
                minWidth: 520,
              }}
            >
              <thead>
                <tr style={{ borderBottom: `2px solid ${t.ink}` }}>
                  {['', 'FREE', 'STARTER', 'PRO'].map((h) => (
                    <th
                      key={h}
                      style={{
                        textAlign: 'left',
                        padding: '14px 12px',
                        fontFamily: t.monoFont,
                        fontSize: 10,
                        letterSpacing: '0.16em',
                        color: t.muted,
                        fontWeight: 500,
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPARISON.map((row, i) => (
                  <tr key={i} style={{ borderBottom: `1px solid ${t.ink}15` }}>
                    {row.map((cell, j) => (
                      <td
                        key={j}
                        style={{
                          padding: '16px 12px',
                          fontFamily: j === 0 ? t.displayFont : t.bodyFont,
                          fontStyle: j === 0 ? 'italic' : 'normal',
                          fontSize: j === 0 ? 18 : 14,
                          color: cell === '—' ? t.muted : t.ink,
                        }}
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ========== CUSTOM ONE-OFF CTA ========== */}
      <section className="px-6 sm:px-10 lg:px-16 pb-16">
        <div
          className="max-w-[1100px] mx-auto"
          style={{
            padding: '40px 40px',
            border: `1px solid ${t.ink}`,
            background: t.paper,
            display: 'flex',
            flexDirection: 'column',
            gap: 20,
          }}
        >
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6">
            <div>
              <div
                style={{
                  fontFamily: t.monoFont,
                  fontSize: 10,
                  letterSpacing: '0.16em',
                  color: t.accent,
                  marginBottom: 8,
                  textTransform: 'uppercase',
                }}
              >
                · NEED MORE THAN 500 PHOTOS?
              </div>
              <h3
                style={{
                  fontFamily: t.displayFont,
                  fontWeight: 400,
                  fontSize: 'clamp(28px, 3.6vw, 40px)',
                  margin: '0 0 8px',
                  letterSpacing: '-0.015em',
                }}
              >
                Custom <span style={{ fontStyle: 'italic' }}>event packages</span>
              </h3>
              <p
                style={{
                  fontFamily: t.bodyFont,
                  fontSize: 14,
                  color: `${t.ink}aa`,
                  margin: 0,
                  maxWidth: 560,
                  lineHeight: 1.55,
                }}
              >
                Weddings, large conferences, and full-day shoots usually run past 500 photos. Tell us your event size, photo count, and how long you need access — we&apos;ll send a tailored quote (one-time or recurring).
              </p>
            </div>
            <a
              href="mailto:support@picur.my?subject=Custom%20event%20package&body=Hi%2C%20I%27d%20like%20a%20quote%20for%20a%20custom%20event.%0A%0AEvent%20date%3A%0AEstimated%20guest%20count%3A%0AEstimated%20photo%20count%3A%0AAccess%20duration%20needed%3A"
              style={{
                padding: '14px 22px',
                background: t.ink,
                color: t.paper,
                fontFamily: t.bodyFont,
                fontWeight: 600,
                fontSize: 14,
                textDecoration: 'none',
                flex: '0 0 auto',
                alignSelf: 'flex-start',
              }}
            >
              Request a quote →
            </a>
          </div>
        </div>
      </section>

      {/* ========== FAQ ========== */}
      <section
        className="px-6 sm:px-10 lg:px-16 py-20 lg:py-24"
        style={{ background: t.paper }}
      >
        <div className="max-w-[1280px] mx-auto grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-12 lg:gap-20">
          <div>
            <div
              style={{
                fontFamily: t.monoFont,
                fontSize: 11,
                letterSpacing: '0.18em',
                color: t.muted,
                marginBottom: 16,
                textTransform: 'uppercase',
              }}
            >
              · FREQUENTLY ASKED
            </div>
            <h2
              style={{
                fontFamily: t.displayFont,
                fontWeight: 400,
                fontSize: 'clamp(40px, 6vw, 64px)',
                lineHeight: 0.95,
                margin: 0,
                letterSpacing: '-0.02em',
              }}
            >
              You might
              <br />
              <span style={{ fontStyle: 'italic' }}>wonder…</span>
            </h2>
          </div>
          <div>
            {FAQS.map((f, i) => (
              <details
                key={i}
                style={{
                  borderBottom: `1px solid ${t.ink}22`,
                  padding: '20px 0',
                }}
              >
                <summary
                  style={{
                    cursor: 'pointer',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    fontFamily: t.displayFont,
                    fontSize: 'clamp(20px, 2.4vw, 26px)',
                    fontStyle: i === 0 ? 'italic' : 'normal',
                    listStyle: 'none',
                  }}
                >
                  {f.q}
                  <span
                    style={{
                      fontFamily: t.displayFont,
                      fontStyle: 'italic',
                      color: t.accent,
                      marginLeft: 16,
                      flex: '0 0 auto',
                    }}
                  >
                    +
                  </span>
                </summary>
                <p
                  style={{
                    fontFamily: t.bodyFont,
                    fontSize: 15,
                    lineHeight: 1.6,
                    color: `${t.ink}cc`,
                    margin: '14px 0 0',
                    maxWidth: 640,
                  }}
                >
                  {f.a}
                </p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <section className="px-6 sm:px-10 lg:px-16 py-12 text-center">
        <p
          style={{
            fontFamily: t.bodyFont,
            fontSize: 13,
            color: t.muted,
          }}
        >
          Questions?{' '}
          <a
            href="mailto:support@picur.my"
            style={{
              color: t.accent,
              borderBottom: `1px solid ${t.accent}66`,
              textDecoration: 'none',
            }}
          >
            support@picur.my
          </a>
        </p>
      </section>
    </AtelierLayout>
  )
}
