import Head from 'next/head'
import { Mail, Clock } from 'lucide-react'
import { LumiereLayout, LUMIERE } from '@/components/lumiere'

export default function Contact() {
  const t = LUMIERE
  return (
    <LumiereLayout>
      <Head>
        <meta
          name="description"
          content="Contact PicUr — get in touch with our team for questions, feedback, or beta access."
        />
      </Head>

      <style>{`
        .lumiere-contact-h1 { font-size: clamp(40px, 7vw, 88px); line-height: 0.95; letter-spacing: -0.02em; }
      `}</style>

      <section className="px-6 sm:px-10 lg:px-14 py-16 lg:py-24">
        <div className="max-w-[1100px] mx-auto">
          <div
            style={{
              fontFamily: t.monoFont,
              fontSize: 11,
              letterSpacing: '0.26em',
              color: t.accent,
              marginBottom: 16,
              textTransform: 'uppercase',
            }}
          >
            — GET IN TOUCH —
          </div>
          <h1
            className="lumiere-contact-h1"
            style={{ fontFamily: t.displayFont, fontWeight: 400, margin: 0, color: t.ink }}
          >
            We&apos;d love to <span style={{ fontStyle: 'italic', color: t.accent }}>hear from you.</span>
          </h1>
          <p
            style={{
              fontFamily: t.displayFont,
              fontStyle: 'italic',
              fontSize: 'clamp(18px, 2.2vw, 24px)',
              color: t.inkDim,
              maxWidth: 620,
              marginTop: 24,
              lineHeight: 1.4,
            }}
          >
            Questions, feedback, beta access, custom event quotes — write to us and we&apos;ll write back personally.
          </p>
        </div>
      </section>

      <section className="px-6 sm:px-10 lg:px-14 pb-20 lg:pb-28">
        <div className="max-w-[1100px] mx-auto grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16">
          <div>
            <div
              style={{
                fontFamily: t.monoFont,
                fontSize: 11,
                letterSpacing: '0.22em',
                color: t.accent,
                marginBottom: 16,
                textTransform: 'uppercase',
              }}
            >
              · ABOUT PICUR
            </div>
            <div
              style={{
                fontFamily: t.bodyFont,
                fontSize: 16,
                lineHeight: 1.65,
                color: t.inkDim,
              }}
            >
              <p style={{ margin: '0 0 18px' }}>
                PicUr is an AI-powered photo sharing platform built for events — weddings, conferences, family reunions. Photographers upload, guests find themselves with a selfie.
              </p>
              <p style={{ margin: '0 0 18px' }}>
                Built private from the start. Face recognition runs on hardware we own, embeddings are math not photos, and every event auto-deletes on a timer you choose.
              </p>
              <p style={{ margin: 0 }}>
                We&apos;re a small team. Emails land in a real inbox, not a ticketing maze.
              </p>
            </div>
          </div>

          <div
            style={{
              padding: '36px',
              background: t.paper,
              border: `1px solid ${t.border}`,
            }}
          >
            <div
              style={{
                fontFamily: t.monoFont,
                fontSize: 11,
                letterSpacing: '0.22em',
                color: t.accent,
                marginBottom: 24,
                textTransform: 'uppercase',
              }}
            >
              · WAYS TO REACH US
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
              <div style={{ display: 'flex', gap: 20 }}>
                <div
                  style={{
                    width: 44,
                    height: 44,
                    background: `${t.accent}1a`,
                    border: `1px solid ${t.accent}55`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flex: '0 0 auto',
                  }}
                >
                  <Mail size={20} color={t.accent} />
                </div>
                <div>
                  <div
                    style={{
                      fontFamily: t.monoFont,
                      fontSize: 10,
                      letterSpacing: '0.18em',
                      color: t.muted,
                      textTransform: 'uppercase',
                      marginBottom: 4,
                    }}
                  >
                    EMAIL
                  </div>
                  <a
                    href="mailto:support@picur.my"
                    style={{
                      fontFamily: t.displayFont,
                      fontStyle: 'italic',
                      fontSize: 22,
                      color: t.ink,
                      textDecoration: 'none',
                    }}
                  >
                    support@picur.my
                  </a>
                  <p
                    style={{
                      fontFamily: t.bodyFont,
                      fontSize: 13,
                      color: t.muted,
                      marginTop: 6,
                      marginBottom: 0,
                    }}
                  >
                    General questions, beta access, custom quotes.
                  </p>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 20 }}>
                <div
                  style={{
                    width: 44,
                    height: 44,
                    background: `${t.accent}1a`,
                    border: `1px solid ${t.accent}55`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flex: '0 0 auto',
                  }}
                >
                  <Clock size={20} color={t.accent} />
                </div>
                <div>
                  <div
                    style={{
                      fontFamily: t.monoFont,
                      fontSize: 10,
                      letterSpacing: '0.18em',
                      color: t.muted,
                      textTransform: 'uppercase',
                      marginBottom: 4,
                    }}
                  >
                    RESPONSE TIME
                  </div>
                  <div
                    style={{
                      fontFamily: t.displayFont,
                      fontStyle: 'italic',
                      fontSize: 22,
                      color: t.ink,
                    }}
                  >
                    Within 24 hours
                  </div>
                  <p
                    style={{
                      fontFamily: t.bodyFont,
                      fontSize: 13,
                      color: t.muted,
                      marginTop: 6,
                      marginBottom: 0,
                    }}
                  >
                    Usually much faster. We read every email.
                  </p>
                </div>
              </div>
            </div>

            <a
              href="mailto:support@picur.my"
              style={{
                display: 'block',
                marginTop: 32,
                padding: '16px 20px',
                background: t.accent,
                color: t.bg,
                fontFamily: t.bodyFont,
                fontSize: 15,
                fontWeight: 600,
                letterSpacing: '0.04em',
                textAlign: 'center',
                textDecoration: 'none',
              }}
            >
              SEND US AN EMAIL →
            </a>
          </div>
        </div>
      </section>
    </LumiereLayout>
  )
}
