import Head from 'next/head'
import Link from 'next/link'
import {
  LumiereLayout,
  LUMIERE,
  Ticker,
  MagicScan,
  PhoneFlow,
  Scene,
  PricingCard,
  CornerMarks,
} from '@/components/lumiere'

const STRUCTURED_DATA = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'Organization',
      '@id': 'https://picur.my/#org',
      name: 'PicUr',
      url: 'https://picur.my',
      logo: 'https://picur.my/web-app-manifest-512x512.png',
      sameAs: [],
    },
    {
      '@type': 'SoftwareApplication',
      '@id': 'https://picur.my/#app',
      name: 'PicUr',
      description:
        'AI-powered face recognition photo sharing platform for event photographers. Guests find their photos using just a selfie.',
      applicationCategory: 'PhotographyApplication',
      operatingSystem: 'Web',
      offers: [
        { '@type': 'Offer', name: 'Free', price: '0', priceCurrency: 'USD' },
        { '@type': 'Offer', name: 'Starter', price: '9', priceCurrency: 'USD' },
        { '@type': 'Offer', name: 'Pro', price: '29', priceCurrency: 'USD' },
      ],
    },
  ],
}

const STEPS_LEFT = [
  {
    n: '01',
    title: 'You upload',
    body: 'Drag the card straight from the shoot. We strip EXIF, encrypt at rest, and index every face overnight.',
  },
  {
    n: '02',
    title: 'They scan',
    body: 'A selfie. No app, no signup, no friction. Works on any phone with a camera.',
  },
]

const STEPS_RIGHT = [
  {
    n: '03',
    title: 'The magic',
    body: 'Every photo of them — and only them — appears in under five seconds. Your guests text you.',
  },
]

const FEATURES = [
  { t: 'On-shoot upload', d: 'Tether from Lightroom, or sync from your iPad on the drive home.' },
  { t: 'Math, not faces', d: '512-dim embeddings on hardware we own. No third parties. No training sets.' },
  { t: 'Quiet branding', d: 'Your studio name is what guests remember. Picur stays out of the frame.' },
  { t: 'Auto-deletes', d: 'Photos and face vectors purge on the retention date you choose.' },
  { t: 'Multi-angle scan', d: 'Three captures, three angles. Recall climbs from 84% to 99.3%.' },
  { t: 'Bulk download', d: 'Originals in a zip. Streamed on the server. No "we’ll email it" stalling.' },
]

const PRICING_PREVIEW = [
  {
    name: 'Free',
    price: '$0',
    period: 'FOREVER',
    desc: 'For a first taste — try one event, on us.',
    features: ['1 active event', '25 photos', 'Guest selfie scan', '30-day retention'],
    ctaHref: '/admin/register',
  },
  {
    name: 'Starter',
    price: '$9',
    period: 'PER MONTH',
    desc: 'For the photographer with a side gig and a few weddings a year.',
    features: ['5 active events', '250 photos each', '6-month retention', 'Photo downloads'],
    ctaHref: '/admin/register?plan=starter',
    featured: true,
  },
  {
    name: 'Pro',
    price: '$29',
    period: 'PER MONTH',
    desc: 'For studios managing many events year-round.',
    features: ['20 active events', '500 photos each', '1-year retention', 'Priority indexing'],
    ctaHref: '/admin/register?plan=pro',
  },
]

export default function Home() {
  const t = LUMIERE
  return (
    <LumiereLayout>
      <Head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED_DATA) }}
        />
      </Head>

      <style>{`
        .lumiere-h1 { font-size: clamp(56px, 13vw, 160px); line-height: 0.88; letter-spacing: -0.03em; }
        .lumiere-h2 { font-size: clamp(36px, 7vw, 96px); line-height: 0.95; letter-spacing: -0.025em; }
        .lumiere-h2-sm { font-size: clamp(32px, 6vw, 80px); line-height: 0.95; letter-spacing: -0.02em; }
        .lumiere-fig-h { font-size: clamp(32px, 5vw, 64px); line-height: 1; letter-spacing: -0.02em; }
        .lumiere-cta-h { font-size: clamp(48px, 11vw, 124px); line-height: 0.88; letter-spacing: -0.025em; }
        .lumiere-lead { font-size: clamp(18px, 2.4vw, 26px); line-height: 1.3; }
      `}</style>

      {/* ========== HERO: full-bleed cinematic ========== */}
      <section
        style={{
          position: 'relative',
          minHeight: 'clamp(560px, 90vh, 820px)',
          overflow: 'hidden',
        }}
      >
        <div style={{ position: 'absolute', inset: 0 }}>
          <Scene
            tone="dusk"
            aspect="auto"
            style={{ height: '100%', aspectRatio: 'auto', borderRadius: 0 }}
            src="/lumiere/hero.jpg"
          />
        </div>
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: `linear-gradient(180deg, ${t.bg}aa 0%, ${t.bg}55 30%, ${t.bg}99 80%, ${t.bg} 100%)`,
          }}
        />
        <div
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage: `repeating-linear-gradient(135deg, rgba(255,255,255,.02) 0 2px, transparent 2px 6px)`,
            pointerEvents: 'none',
          }}
        />
        <CornerMarks inset={32} size={18} opacity={0.5} />

        <div
          className="px-6 sm:px-12 lg:px-20 py-12 lg:py-20"
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            gap: 24,
          }}
        >
          {/* Top metadata */}
          <div
            className="flex flex-wrap items-center gap-x-3 gap-y-1"
            style={{
              fontFamily: t.monoFont,
              fontSize: 10,
              letterSpacing: '0.22em',
              color: t.accent,
              textTransform: 'uppercase',
            }}
          >
            <span style={{ display: 'inline-block', width: 32, height: 1, background: t.accent }} />
            REEL 04 · SCENE 01
            <span style={{ color: t.muted }}>· INT · NOW BOOKING WINTER</span>
          </div>

          {/* Bottom: headline + CTA */}
          <div>
            <h1
              className="lumiere-h1"
              style={{
                fontFamily: t.displayFont,
                fontWeight: 400,
                margin: 0,
                color: t.ink,
                maxWidth: 1180,
              }}
            >
              Every photograph
              <br />
              <span style={{ fontStyle: 'italic', color: t.accent }}>finds its face.</span>
            </h1>
            <div
              className="flex flex-col md:flex-row md:items-end md:justify-between gap-8"
              style={{ marginTop: 40 }}
            >
              <p
                className="lumiere-lead"
                style={{
                  fontFamily: t.displayFont,
                  fontStyle: 'italic',
                  color: t.inkDim,
                  margin: 0,
                  maxWidth: 520,
                }}
              >
                A face-recognition photo gallery so fast and so quiet your guests think it&apos;s magic. (It is.)
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <Link
                  href="/admin/register"
                  style={{
                    padding: '18px 28px',
                    background: t.accent,
                    color: t.bg,
                    fontFamily: t.bodyFont,
                    fontSize: 14,
                    fontWeight: 600,
                    letterSpacing: '0.06em',
                    textDecoration: 'none',
                  }}
                >
                  BEGIN —
                </Link>
                <Link
                  href="#method"
                  style={{
                    padding: '18px 22px',
                    background: 'transparent',
                    color: t.ink,
                    border: `1px solid ${t.ink}55`,
                    fontFamily: t.bodyFont,
                    fontSize: 14,
                    fontWeight: 500,
                    textDecoration: 'none',
                  }}
                >
                  Watch the demo
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      <Ticker />

      {/* ========== I · THE METHOD ========== */}
      <section
        id="method"
        className="px-6 sm:px-10 lg:px-14 py-20 lg:py-28 scroll-mt-20"
      >
        <div className="max-w-[1280px] mx-auto">
          <div className="text-center" style={{ marginBottom: 64 }}>
            <div
              style={{
                fontFamily: t.monoFont,
                fontSize: 11,
                letterSpacing: '0.26em',
                color: t.accent,
                marginBottom: 18,
                textTransform: 'uppercase',
              }}
            >
              — I · THE METHOD —
            </div>
            <h2
              className="lumiere-h2"
              style={{ fontFamily: t.displayFont, fontWeight: 400, margin: 0, color: t.ink }}
            >
              Three steps,{' '}
              <span style={{ fontStyle: 'italic', color: t.accent }}>one moment.</span>
            </h2>
          </div>

          <style>{`
            .lumiere-method-grid {
              display: grid;
              grid-template-columns: 1fr;
              gap: 56px;
              align-items: center;
            }
            @media (min-width: 1024px) {
              .lumiere-method-grid {
                grid-template-columns: 1fr auto 1fr;
                gap: 64px;
              }
            }
            .lumiere-step-left { text-align: left; }
            @media (min-width: 1024px) {
              .lumiere-step-left { text-align: right; }
              .lumiere-step-left p { margin-left: auto; }
            }
          `}</style>

          <div className="lumiere-method-grid">
            {/* left column — steps 01, 02 */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 36 }}>
              {STEPS_LEFT.map((step) => (
                <div key={step.n} className="lumiere-step-left">
                  <div
                    style={{
                      fontFamily: t.monoFont,
                      fontSize: 10,
                      letterSpacing: '0.22em',
                      color: t.accent,
                      marginBottom: 10,
                    }}
                  >
                    — {step.n}
                  </div>
                  <h3
                    style={{
                      fontFamily: t.displayFont,
                      fontWeight: 400,
                      fontSize: 'clamp(28px, 3.6vw, 44px)',
                      lineHeight: 1,
                      margin: '0 0 12px',
                      letterSpacing: '-0.015em',
                      color: t.ink,
                    }}
                  >
                    {step.title.split(' ')[0]}{' '}
                    <span style={{ fontStyle: 'italic' }}>
                      {step.title.split(' ').slice(1).join(' ')}
                    </span>
                  </h3>
                  <p
                    style={{
                      fontFamily: t.bodyFont,
                      fontSize: 15,
                      lineHeight: 1.55,
                      color: t.inkDim,
                      margin: 0,
                      maxWidth: 360,
                    }}
                  >
                    {step.body}
                  </p>
                </div>
              ))}
            </div>

            {/* center — phone */}
            <div className="flex justify-center">
              <PhoneFlow tone="dusk" />
            </div>

            {/* right column — step 03 + stat */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 36 }}>
              {STEPS_RIGHT.map((step) => (
                <div key={step.n}>
                  <div
                    style={{
                      fontFamily: t.monoFont,
                      fontSize: 10,
                      letterSpacing: '0.22em',
                      color: t.accent,
                      marginBottom: 10,
                    }}
                  >
                    — {step.n}
                  </div>
                  <h3
                    style={{
                      fontFamily: t.displayFont,
                      fontWeight: 400,
                      fontSize: 'clamp(28px, 3.6vw, 44px)',
                      lineHeight: 1,
                      margin: '0 0 12px',
                      letterSpacing: '-0.015em',
                      color: t.ink,
                    }}
                  >
                    {step.title.split(' ')[0]}{' '}
                    <span style={{ fontStyle: 'italic' }}>
                      {step.title.split(' ').slice(1).join(' ')}
                    </span>
                  </h3>
                  <p
                    style={{
                      fontFamily: t.bodyFont,
                      fontSize: 15,
                      lineHeight: 1.55,
                      color: t.inkDim,
                      margin: 0,
                      maxWidth: 360,
                    }}
                  >
                    {step.body}
                  </p>
                </div>
              ))}
              <div
                style={{
                  padding: 24,
                  border: `1px solid ${t.border}`,
                  background: t.paper,
                  maxWidth: 320,
                }}
              >
                <div
                  style={{
                    fontFamily: t.monoFont,
                    fontSize: 10,
                    letterSpacing: '0.2em',
                    color: t.accent,
                    marginBottom: 8,
                  }}
                >
                  · TARGET
                </div>
                <div
                  style={{
                    fontFamily: t.displayFont,
                    fontStyle: 'italic',
                    fontSize: 60,
                    lineHeight: 1,
                    color: t.ink,
                  }}
                >
                  &lt; 5s
                </div>
                <div
                  style={{
                    color: t.inkDim,
                    fontSize: 13,
                    lineHeight: 1.5,
                    marginTop: 8,
                  }}
                >
                  from selfie to first matched photo, on a good connection.
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ========== MAGIC DEMO inset ========== */}
      <section className="px-6 sm:px-10 lg:px-14 pb-20 lg:pb-28">
        <div
          className="max-w-[1280px] mx-auto"
          style={{
            position: 'relative',
            background: t.paper,
            border: `1px solid ${t.border}`,
            padding: 'clamp(40px, 8vw, 100px) clamp(20px, 6vw, 80px)',
          }}
        >
          <div
            style={{
              position: 'absolute',
              top: 24,
              left: 24,
              fontFamily: t.monoFont,
              fontSize: 10,
              letterSpacing: '0.22em',
              color: t.muted,
              textTransform: 'uppercase',
            }}
          >
            FIG. 02 · THE MOMENT
          </div>
          <div
            className="lumiere-fig-h text-center"
            style={{
              fontFamily: t.displayFont,
              fontWeight: 400,
              marginBottom: 12,
              marginTop: 24,
              color: t.ink,
            }}
          >
            One selfie. <span style={{ fontStyle: 'italic', color: t.accent }}>Every photo.</span>
          </div>
          <div
            className="text-center"
            style={{
              fontFamily: t.displayFont,
              fontStyle: 'italic',
              fontSize: 'clamp(16px, 2vw, 22px)',
              color: t.inkDim,
              marginBottom: 56,
            }}
          >
            This is exactly what your guests see.
          </div>
          <MagicScan tone="dusk" />
        </div>
      </section>

      {/* ========== II · THE TOOLKIT ========== */}
      <section className="px-6 sm:px-10 lg:px-14 pb-20 lg:pb-28">
        <div className="max-w-[1280px] mx-auto">
          <div style={{ marginBottom: 48 }}>
            <div
              style={{
                fontFamily: t.monoFont,
                fontSize: 11,
                letterSpacing: '0.24em',
                color: t.accent,
                marginBottom: 12,
                textTransform: 'uppercase',
              }}
            >
              — II · THE TOOLKIT —
            </div>
            <h2
              className="lumiere-h2-sm"
              style={{ fontFamily: t.displayFont, fontWeight: 400, margin: 0, color: t.ink }}
            >
              Made <span style={{ fontStyle: 'italic', color: t.accent }}>for the craft.</span>
            </h2>
          </div>
          <div
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3"
            style={{ gap: 1, background: t.border }}
          >
            {FEATURES.map((f, i) => (
              <div
                key={i}
                style={{
                  background: t.bg,
                  padding: '32px 28px',
                }}
              >
                <div
                  style={{
                    fontFamily: t.monoFont,
                    fontSize: 10,
                    letterSpacing: '0.18em',
                    color: t.accent,
                    marginBottom: 14,
                  }}
                >
                  {String(i + 1).padStart(2, '0')} —
                </div>
                <h3
                  style={{
                    fontFamily: t.displayFont,
                    fontWeight: 400,
                    fontSize: 'clamp(22px, 2.4vw, 30px)',
                    lineHeight: 1.05,
                    margin: '0 0 10px',
                    letterSpacing: '-0.015em',
                    color: t.ink,
                  }}
                >
                  {f.t.split(' ')[0]}{' '}
                  <span style={{ fontStyle: 'italic' }}>
                    {f.t.split(' ').slice(1).join(' ')}
                  </span>
                </h3>
                <p
                  style={{
                    fontFamily: t.bodyFont,
                    fontSize: 14,
                    lineHeight: 1.55,
                    color: t.inkDim,
                    margin: 0,
                  }}
                >
                  {f.d}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ========== III · THE PRICE ========== */}
      <section className="px-6 sm:px-10 lg:px-14 pb-20 lg:pb-28">
        <div className="max-w-[1280px] mx-auto">
          <div className="text-center" style={{ marginBottom: 48 }}>
            <div
              style={{
                fontFamily: t.monoFont,
                fontSize: 11,
                letterSpacing: '0.24em',
                color: t.accent,
                marginBottom: 12,
                textTransform: 'uppercase',
              }}
            >
              — III · THE PRICE —
            </div>
            <h2
              className="lumiere-h2-sm"
              style={{ fontFamily: t.displayFont, fontWeight: 400, margin: 0, color: t.ink }}
            >
              Honest <span style={{ fontStyle: 'italic', color: t.accent }}>numbers.</span>
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3">
            {PRICING_PREVIEW.map((p) => (
              <PricingCard key={p.name} {...p} />
            ))}
          </div>
          <div className="text-center" style={{ marginTop: 32 }}>
            <Link
              href="/pricing"
              style={{
                fontFamily: t.bodyFont,
                fontSize: 13,
                color: t.accent,
                borderBottom: `1px solid ${t.accent}55`,
                paddingBottom: 2,
                textDecoration: 'none',
              }}
            >
              See full pricing →
            </Link>
          </div>
        </div>
      </section>

      {/* ========== CTA ========== */}
      <section
        className="px-6 sm:px-10 lg:px-14 py-20 lg:py-28"
        style={{ background: t.accent, color: t.bg }}
      >
        <div className="max-w-[1280px] mx-auto flex flex-col lg:flex-row lg:justify-between lg:items-end gap-10">
          <h2
            className="lumiere-cta-h"
            style={{
              fontFamily: t.displayFont,
              fontWeight: 400,
              margin: 0,
              flex: 1,
            }}
          >
            Now showing.
            <br />
            <span style={{ fontStyle: 'italic' }}>Indefinitely.</span>
          </h2>
          <div style={{ flex: '0 0 auto' }}>
            <Link
              href="/admin/register"
              style={{
                display: 'inline-block',
                padding: '22px 36px',
                background: t.bg,
                color: t.accent,
                fontFamily: t.bodyFont,
                fontSize: 15,
                fontWeight: 600,
                letterSpacing: '0.06em',
                textDecoration: 'none',
              }}
            >
              BEGIN — FREE
            </Link>
            <div
              style={{
                marginTop: 16,
                fontFamily: t.monoFont,
                fontSize: 10,
                letterSpacing: '0.18em',
                color: `${t.bg}cc`,
                textTransform: 'uppercase',
              }}
            >
              · Setup in under 90 seconds
            </div>
          </div>
        </div>
      </section>
    </LumiereLayout>
  )
}
