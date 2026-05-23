import Head from 'next/head'
import Link from 'next/link'
import {
  AtelierLayout,
  ATELIER,
  Ticker,
  MagicScan,
  PhoneFlow,
  Photo,
  Scene,
  PricingCard,
} from '@/components/atelier'

// JSON-LD structured data — Organization + SoftwareApplication.
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
        {
          '@type': 'Offer',
          name: 'Starter',
          price: '9',
          priceCurrency: 'USD',
          priceSpecification: {
            '@type': 'UnitPriceSpecification',
            price: '9',
            priceCurrency: 'USD',
            unitText: 'MONTH',
          },
        },
        {
          '@type': 'Offer',
          name: 'Pro',
          price: '29',
          priceCurrency: 'USD',
          priceSpecification: {
            '@type': 'UnitPriceSpecification',
            price: '29',
            priceCurrency: 'USD',
            unitText: 'MONTH',
          },
        },
      ],
      featureList: [
        'Face recognition photo matching',
        'Multi-angle scan capture',
        'Guest selfie scanning',
        'Bulk photo download',
        'Custom event retention',
      ],
    },
  ],
}

const STEPS = [
  {
    num: '01',
    title: 'You upload',
    body: 'Drag photos straight from the shoot. We strip GPS and EXIF, encrypt at rest, and index every face overnight.',
    tone: 'sand' as const,
  },
  {
    num: '02',
    title: 'Guests scan',
    body: 'Send a link or print a discreet QR on the menu cards. A selfie on any device — no app, no signup.',
    tone: 'cream' as const,
  },
  {
    num: '03',
    title: 'Photos arrive',
    body: 'In under five seconds, every photo of them is theirs to download. You get the credit. They get the memory.',
    tone: 'mauve' as const,
  },
]

const FEATURES = [
  { n: '01', t: 'On-shoot upload', d: 'Tether straight from Lightroom or upload from your iPad on the drive home.' },
  { n: '02', t: 'Multi-angle scan', d: 'Three-quarter, full-face, profile — we capture every angle for higher recall.' },
  { n: '03', t: 'Math, not faces', d: '512-dim embeddings, never the photo of your face. Stored on hardware we own.' },
  { n: '04', t: 'Self-hosted AI', d: 'CompreFace runs in our data center. No OpenAI, no Anthropic, no third parties.' },
  { n: '05', t: 'Auto-deletes', d: 'Photos and face data purge on the retention date you choose. Backups roll off in seven days.' },
  { n: '06', t: 'Quiet branding', d: 'Picur stays politely out of the frame so your studio is what guests remember.' },
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
    features: ['5 active events', '250 photos each', '6-month retention', 'Guest selfie scan', 'Photo downloads'],
    ctaHref: '/admin/register?plan=starter',
    featured: true,
  },
  {
    name: 'Pro',
    price: '$29',
    period: 'PER MONTH',
    desc: 'For studios managing many events year-round.',
    features: ['20 active events', '500 photos each', '1-year retention', 'Priority indexing', 'Photo downloads'],
    ctaHref: '/admin/register?plan=pro',
  },
]

export default function Home() {
  const t = ATELIER
  return (
    <AtelierLayout>
      <Head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED_DATA) }}
        />
      </Head>

      {/* Responsive helper styles for hero typography */}
      <style>{`
        .atelier-h1 { font-size: clamp(56px, 11vw, 124px); line-height: 0.92; letter-spacing: -0.025em; }
        .atelier-h2 { font-size: clamp(40px, 7vw, 88px); line-height: 0.95; letter-spacing: -0.02em; }
        .atelier-h2-sm { font-size: clamp(36px, 6vw, 76px); line-height: 0.95; letter-spacing: -0.02em; }
        .atelier-h3 { font-size: clamp(28px, 4vw, 38px); line-height: 1.0; letter-spacing: -0.02em; }
        .atelier-cta-h2 { font-size: clamp(48px, 11vw, 116px); line-height: 0.92; letter-spacing: -0.025em; }
        .atelier-lead { font-size: clamp(18px, 2.1vw, 26px); line-height: 1.4; }
      `}</style>

      {/* ========== HERO ========== */}
      <section
        className="px-6 sm:px-10 lg:px-16 pt-10 pb-12 lg:pt-12 lg:pb-16"
      >
        <div className="grid grid-cols-1 lg:grid-cols-[1.2fr_1fr] gap-12 lg:gap-14 items-center max-w-[1280px] mx-auto">
          <div>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 10,
                padding: '6px 12px 6px 6px',
                background: t.paper,
                border: `1px solid ${t.border}`,
                borderRadius: 999,
                marginBottom: 28,
              }}
            >
              <span
                style={{
                  padding: '4px 10px',
                  background: t.accent,
                  color: t.paper,
                  fontFamily: t.monoFont,
                  fontSize: 9,
                  letterSpacing: '0.16em',
                  borderRadius: 999,
                }}
              >
                VOL. 04
              </span>
              <span
                style={{
                  fontFamily: t.monoFont,
                  fontSize: 11,
                  color: t.muted,
                  letterSpacing: '0.08em',
                }}
              >
                BETA · NOW BOOKING WINTER
              </span>
            </div>
            <h1
              className="atelier-h1"
              style={{
                fontFamily: t.displayFont,
                fontWeight: 400,
                margin: 0,
                color: t.ink,
              }}
            >
              Your photos
              <br />
              <span style={{ fontStyle: 'italic', color: t.accent }}>find you.</span>
            </h1>
            <p
              className="atelier-lead"
              style={{
                fontFamily: t.displayFont,
                fontStyle: 'italic',
                color: `${t.ink}cc`,
                marginTop: 28,
                marginBottom: 32,
                maxWidth: 480,
              }}
            >
              A quiet little tool for wedding photographers. Guests take a selfie, and every photo of them — every single one — finds its way home.
            </p>
            <div className="flex flex-wrap items-center gap-4">
              <Link
                href="/admin/register"
                style={{
                  padding: '16px 28px',
                  background: t.ink,
                  color: t.paper,
                  fontFamily: t.bodyFont,
                  fontSize: 14,
                  fontWeight: 600,
                  letterSpacing: '0.02em',
                  textDecoration: 'none',
                }}
              >
                Create your first event →
              </Link>
              <Link
                href="#how-it-works"
                style={{
                  padding: '16px 22px',
                  background: 'transparent',
                  color: t.ink,
                  border: `1px solid ${t.ink}`,
                  fontFamily: t.bodyFont,
                  fontSize: 14,
                  fontWeight: 600,
                  textDecoration: 'none',
                }}
              >
                See how it works
              </Link>
            </div>
            <div
              className="flex flex-wrap items-center gap-x-9 gap-y-2"
              style={{
                marginTop: 32,
                fontFamily: t.monoFont,
                fontSize: 10,
                color: t.muted,
                letterSpacing: '0.14em',
                textTransform: 'uppercase',
              }}
            >
              <span>· No app required</span>
              <span>· Auto-deletes with your event</span>
              <span>· Self-hosted AI</span>
            </div>
          </div>

          {/* Right: phone + collage. Hidden on mobile to keep hero focused */}
          <div className="relative hidden lg:block" style={{ height: 640 }}>
            <div
              style={{
                position: 'absolute',
                right: 0,
                top: 20,
                width: 320,
                transform: 'rotate(3deg)',
                border: `10px solid ${t.paper}`,
                boxShadow: `0 30px 60px ${t.ink}22`,
              }}
            >
              <Scene tone="cream" aspect="3/4" label="ATELIER/PRESS 02" src="/atelier/hero-1.jpg" />
            </div>
            <div
              style={{
                position: 'absolute',
                right: 280,
                top: 380,
                width: 180,
                transform: 'rotate(-6deg)',
                border: `8px solid ${t.paper}`,
                boxShadow: `0 20px 40px ${t.ink}22`,
                zIndex: 1,
              }}
            >
              <Photo tone="sand" aspect="3/4" label="MAY 24" src="/atelier/hero-2.jpg" />
            </div>
            <div style={{ position: 'absolute', left: -20, top: 30, zIndex: 2 }}>
              <PhoneFlow tone="sand" />
            </div>
          </div>

          {/* Mobile: just a phone, centered */}
          <div className="flex justify-center lg:hidden mt-4">
            <PhoneFlow tone="sand" scale={0.85} />
          </div>
        </div>
      </section>

      <Ticker />

      {/* ========== SECTION I · THE METHOD ========== */}
      <section
        id="how-it-works"
        className="px-6 sm:px-10 lg:px-16 py-20 lg:py-28 scroll-mt-20"
      >
        <div className="max-w-[1280px] mx-auto">
          <div
            className="flex flex-col lg:flex-row lg:justify-between lg:items-baseline gap-6"
            style={{
              marginBottom: 56,
              borderBottom: `1px solid ${t.ink}`,
              paddingBottom: 18,
            }}
          >
            <div>
              <div
                style={{
                  fontFamily: t.monoFont,
                  fontSize: 11,
                  letterSpacing: '0.18em',
                  color: t.muted,
                  marginBottom: 12,
                  textTransform: 'uppercase',
                }}
              >
                SECTION I · THE METHOD
              </div>
              <h2
                className="atelier-h2"
                style={{
                  fontFamily: t.displayFont,
                  fontWeight: 400,
                  margin: 0,
                }}
              >
                How <span style={{ fontStyle: 'italic' }}>it works</span>
              </h2>
            </div>
            <div
              style={{
                maxWidth: 360,
                fontFamily: t.displayFont,
                fontStyle: 'italic',
                fontSize: 20,
                lineHeight: 1.4,
                color: `${t.ink}cc`,
              }}
            >
              Three steps, one moment of delight. No app, no friction, no &ldquo;check your email in six weeks.&rdquo;
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-10 lg:gap-12">
            {STEPS.map((step) => (
              <div key={step.num}>
                <Photo
                  tone={step.tone}
                  aspect="4/5"
                  label={`STEP ${step.num}`}
                  src={`/atelier/step-${step.num}.jpg`}
                />
                <div
                  style={{
                    marginTop: 20,
                    fontFamily: t.monoFont,
                    fontSize: 11,
                    letterSpacing: '0.16em',
                    color: t.accent,
                  }}
                >
                  {step.num} —
                </div>
                <h3
                  className="atelier-h3"
                  style={{
                    fontFamily: t.displayFont,
                    fontWeight: 400,
                    margin: '6px 0 12px',
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
                    color: `${t.ink}cc`,
                    margin: 0,
                  }}
                >
                  {step.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ========== SECTION II · THE MAGIC ========== */}
      <section
        className="px-6 sm:px-10 lg:px-16 py-20 lg:py-28"
        style={{ background: t.paper, position: 'relative' }}
      >
        <div className="max-w-[1100px] mx-auto">
          <div
            style={{
              fontFamily: t.monoFont,
              fontSize: 11,
              letterSpacing: '0.18em',
              color: t.muted,
              textAlign: 'center',
              marginBottom: 20,
              textTransform: 'uppercase',
            }}
          >
            SECTION II · THE MAGIC
          </div>
          <h2
            className="atelier-h2 text-center"
            style={{
              fontFamily: t.displayFont,
              fontWeight: 400,
              margin: 0,
              marginBottom: 16,
            }}
          >
            One selfie. <span style={{ fontStyle: 'italic' }}>Every photo.</span>
          </h2>
          <p
            className="text-center mx-auto"
            style={{
              fontFamily: t.displayFont,
              fontStyle: 'italic',
              fontSize: 'clamp(18px, 2.2vw, 24px)',
              lineHeight: 1.4,
              color: `${t.ink}aa`,
              maxWidth: 560,
              margin: '0 auto 60px',
            }}
          >
            Watch it happen. Below is exactly what your guests see.
          </p>
          <MagicScan tone="sand" />
        </div>
      </section>

      {/* ========== SECTION III · THE TOOLKIT ========== */}
      <section className="px-6 sm:px-10 lg:px-16 py-20 lg:py-28">
        <div className="max-w-[1280px] mx-auto">
          <div
            className="flex flex-col lg:flex-row lg:justify-between lg:items-baseline gap-6"
            style={{ marginBottom: 40 }}
          >
            <div>
              <div
                style={{
                  fontFamily: t.monoFont,
                  fontSize: 11,
                  letterSpacing: '0.18em',
                  color: t.muted,
                  marginBottom: 12,
                  textTransform: 'uppercase',
                }}
              >
                SECTION III · THE TOOLKIT
              </div>
              <h2
                className="atelier-h2-sm"
                style={{
                  fontFamily: t.displayFont,
                  fontWeight: 400,
                  margin: 0,
                }}
              >
                Made for <span style={{ fontStyle: 'italic' }}>professionals</span>
              </h2>
            </div>
          </div>
          <div
            className="grid grid-cols-1 md:grid-cols-2"
            style={{ borderTop: `1px solid ${t.ink}` }}
          >
            {FEATURES.map((f, i) => {
              const isFirstCol = i % 2 === 0
              return (
                <div
                  key={f.n}
                  className="flex gap-7"
                  style={{
                    padding: '32px 0',
                    borderBottom: `1px solid ${t.ink}22`,
                    paddingRight: isFirstCol ? 28 : 0,
                    paddingLeft: !isFirstCol ? 28 : 0,
                    borderRight: 'none',
                  }}
                >
                  <div
                    style={{
                      fontFamily: t.monoFont,
                      fontSize: 11,
                      letterSpacing: '0.16em',
                      color: t.accent,
                      paddingTop: 6,
                      flex: '0 0 auto',
                    }}
                  >
                    {f.n}
                  </div>
                  <div>
                    <h3
                      style={{
                        fontFamily: t.displayFont,
                        fontWeight: 400,
                        fontSize: 'clamp(24px, 2.4vw, 32px)',
                        lineHeight: 1.05,
                        margin: '0 0 10px',
                        letterSpacing: '-0.01em',
                      }}
                    >
                      {f.t}
                    </h3>
                    <p
                      style={{
                        fontFamily: t.bodyFont,
                        fontSize: 14.5,
                        lineHeight: 1.55,
                        color: `${t.ink}aa`,
                        margin: 0,
                      }}
                    >
                      {f.d}
                    </p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* ========== MANIFESTO PULL-QUOTE (no fake testimonial) ========== */}
      <section
        className="px-6 sm:px-10 lg:px-16 py-20 lg:py-28"
        style={{ background: t.ink, color: t.paper }}
      >
        <div className="max-w-[1100px] mx-auto">
          <div
            style={{
              fontFamily: t.displayFont,
              fontSize: 220,
              lineHeight: 0.5,
              color: t.accent,
              height: 60,
              marginBottom: 20,
            }}
          >
            &ldquo;
          </div>
          <blockquote
            style={{
              fontFamily: t.displayFont,
              fontStyle: 'italic',
              fontSize: 'clamp(28px, 4.8vw, 52px)',
              lineHeight: 1.15,
              margin: 0,
              letterSpacing: '-0.015em',
              maxWidth: 980,
            }}
          >
            The best wedding photo is the one that finds the person it&apos;s of — before they&apos;ve forgotten the colour of the napkins.
          </blockquote>
          <div
            style={{
              marginTop: 36,
              fontFamily: ATELIER.monoFont,
              fontSize: 10,
              letterSpacing: '0.18em',
              color: `${t.paper}99`,
              textTransform: 'uppercase',
            }}
          >
            · WHY WE BUILT PICUR
          </div>
        </div>
      </section>

      {/* ========== SECTION IV · THE PRICE ========== */}
      <section className="px-6 sm:px-10 lg:px-16 py-20 lg:py-28">
        <div className="max-w-[1280px] mx-auto">
          <div className="flex flex-col lg:flex-row lg:justify-between lg:items-baseline gap-6 mb-12">
            <div>
              <div
                style={{
                  fontFamily: t.monoFont,
                  fontSize: 11,
                  letterSpacing: '0.18em',
                  color: t.muted,
                  marginBottom: 12,
                  textTransform: 'uppercase',
                }}
              >
                SECTION IV · THE PRICE
              </div>
              <h2
                className="atelier-h2-sm"
                style={{
                  fontFamily: t.displayFont,
                  fontWeight: 400,
                  margin: 0,
                }}
              >
                Honest <span style={{ fontStyle: 'italic' }}>pricing</span>
              </h2>
            </div>
            <Link
              href="/pricing"
              style={{
                fontFamily: t.bodyFont,
                fontSize: 14,
                color: t.accent,
                borderBottom: `1px solid ${t.accent}`,
                paddingBottom: 2,
                textDecoration: 'none',
                alignSelf: 'flex-start',
              }}
            >
              See full pricing →
            </Link>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3">
            {PRICING_PREVIEW.map((p) => (
              <PricingCard key={p.name} {...p} />
            ))}
          </div>

          {/* One-off banner */}
          <div
            className="flex flex-col md:flex-row md:items-center justify-between gap-6"
            style={{
              marginTop: 56,
              padding: '32px 40px',
              background: t.paper,
              border: `1px solid ${t.border}`,
            }}
          >
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
                · FOR A SINGLE EVENT
              </div>
              <h3
                style={{
                  fontFamily: t.displayFont,
                  fontWeight: 400,
                  fontSize: 'clamp(24px, 3vw, 32px)',
                  margin: 0,
                  letterSpacing: '-0.01em',
                }}
              >
                One-off <span style={{ fontStyle: 'italic' }}>packages</span> — tell us what you need
              </h3>
              <p
                style={{
                  fontFamily: t.bodyFont,
                  fontSize: 14,
                  color: `${t.ink}aa`,
                  margin: '8px 0 0',
                  maxWidth: 480,
                  lineHeight: 1.5,
                }}
              >
                Shooting a single wedding or one big event? We&apos;ll quote a one-off package sized to your photo count and retention window.
              </p>
            </div>
            <a
              href="mailto:support@picur.my?subject=One-time%20event%20package"
              style={{
                padding: '14px 22px',
                background: t.ink,
                color: t.paper,
                fontFamily: t.bodyFont,
                fontWeight: 600,
                fontSize: 14,
                textDecoration: 'none',
                flex: '0 0 auto',
              }}
            >
              Request a quote →
            </a>
          </div>
        </div>
      </section>

      {/* ========== FINAL CTA ========== */}
      <section
        className="px-6 sm:px-10 lg:px-16 py-20 lg:py-28"
        style={{ background: t.accent, color: t.paper }}
      >
        <div className="max-w-[1280px] mx-auto flex flex-col lg:flex-row lg:justify-between lg:items-end gap-10">
          <h2
            className="atelier-cta-h2"
            style={{
              fontFamily: t.displayFont,
              fontWeight: 400,
              margin: 0,
              flex: 1,
            }}
          >
            Make
            <br />
            <span style={{ fontStyle: 'italic' }}>them feel</span>
            <br />
            seen.
          </h2>
          <div style={{ flex: '0 0 auto' }}>
            <Link
              href="/admin/register"
              style={{
                display: 'inline-block',
                padding: '20px 32px',
                background: t.paper,
                color: t.ink,
                fontFamily: t.bodyFont,
                fontSize: 15,
                fontWeight: 600,
                textDecoration: 'none',
              }}
            >
              Start free, no card →
            </Link>
            <div
              style={{
                marginTop: 16,
                fontFamily: t.monoFont,
                fontSize: 10,
                letterSpacing: '0.14em',
                color: `${t.paper}cc`,
                textTransform: 'uppercase',
              }}
            >
              · Setup in under 90 seconds
            </div>
          </div>
        </div>
      </section>
    </AtelierLayout>
  )
}
