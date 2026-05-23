import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import api from '@/lib/api'
import { Loader2 } from 'lucide-react'
import { ATELIER, Scene } from '@/components/atelier'

interface EventInfo {
  event_id: string
  name: string
  date: string
  requires_passcode: boolean
  location?: string
  description?: string
  cover_image_url?: string
}

// Split "Maria & David" into a first + rest pair so we can italicize the
// post-ampersand half the way the mockup does. Falls back to a single line
// if the name doesn't follow that pattern.
function splitName(name: string): { head: string; tail?: string } {
  const m = name.match(/^(.+?)\s*([&×x])\s*(.+)$/i)
  if (!m) return { head: name }
  return { head: m[1].trim(), tail: `${m[2]} ${m[3].trim()}` }
}

function formatDate(iso?: string): { day: string; full: string } | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const full = d.toLocaleDateString('en-US', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
  return { day: full, full }
}

export default function GuestEventAccess() {
  const t = ATELIER
  const router = useRouter()
  const { slug } = router.query

  const [eventInfo, setEventInfo] = useState<EventInfo | null>(null)
  const [passcode, setPasscode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [authenticating, setAuthenticating] = useState(false)

  useEffect(() => {
    if (!slug) return
    const fetchEventInfo = async () => {
      try {
        setLoading(true)
        const response = await api.get(`/e/${slug}`)
        setEventInfo(response.data)
        setError('')
      } catch (err: any) {
        if (err.response?.status === 404) {
          setError('Event not found')
        } else {
          setError('Failed to load event information')
        }
      } finally {
        setLoading(false)
      }
    }
    fetchEventInfo()
  }, [slug])

  const handleAuthenticate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!eventInfo) return
    try {
      setAuthenticating(true)
      setError('')
      const payload = eventInfo.requires_passcode ? { passcode } : {}
      // Token comes back as an HttpOnly cookie set by the backend (picur_event),
      // not in the response body. The non-sensitive metadata that downstream
      // pages render lives in sessionStorage — per-tab, cleared on close.
      const response = await api.post(`/e/${slug}/auth`, payload)
      sessionStorage.setItem('event_id', response.data.event_id)
      sessionStorage.setItem('event_name', response.data.event_name)
      sessionStorage.setItem('allow_downloads', String(response.data.allow_downloads))
      router.push(`/e/${slug}/scan`)
    } catch (err: any) {
      if (err.response?.status === 401) {
        setError('Invalid passcode')
      } else {
        setError('Authentication failed. Please try again.')
      }
    } finally {
      setAuthenticating(false)
    }
  }

  if (loading) {
    return (
      <div
        className="atelier"
        style={{
          minHeight: '100vh',
          background: t.bg,
          color: t.ink,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Loader2 className="animate-spin" size={32} style={{ color: t.accent }} />
      </div>
    )
  }

  if (error && !eventInfo) {
    return (
      <div
        className="atelier px-6"
        style={{
          minHeight: '100vh',
          background: t.bg,
          color: t.ink,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            maxWidth: 480,
            padding: '40px',
            background: t.paper,
            border: `1px solid ${t.border}`,
            textAlign: 'center',
          }}
        >
          <div
            style={{
              fontFamily: t.monoFont,
              fontSize: 11,
              letterSpacing: '0.16em',
              color: t.accent,
              marginBottom: 12,
              textTransform: 'uppercase',
            }}
          >
            · WE COULDN&apos;T FIND THAT EVENT
          </div>
          <h1
            style={{
              fontFamily: t.displayFont,
              fontWeight: 400,
              fontSize: 48,
              lineHeight: 1,
              margin: 0,
              letterSpacing: '-0.02em',
            }}
          >
            <span style={{ fontStyle: 'italic' }}>Not found.</span>
          </h1>
          <p
            style={{
              marginTop: 16,
              fontFamily: t.bodyFont,
              fontSize: 14,
              color: `${t.ink}aa`,
            }}
          >
            {error}
          </p>
        </div>
      </div>
    )
  }

  if (!eventInfo) return null

  const { head, tail } = splitName(eventInfo.name)
  const dateFmt = formatDate(eventInfo.date)

  return (
    <div
      className="atelier"
      style={{
        minHeight: '100vh',
        background: t.bg,
        color: t.ink,
        fontFamily: t.bodyFont,
        overflow: 'hidden',
      }}
    >
      <Head>
        <title>{eventInfo.name} — PicUr</title>
      </Head>

      <style>{`
        .atelier-event-grid {
          display: grid;
          grid-template-columns: 1fr;
          min-height: 100vh;
        }
        @media (min-width: 900px) {
          .atelier-event-grid {
            grid-template-columns: 1.1fr 1fr;
          }
        }
        .atelier-event-name { font-size: clamp(56px, 12vw, 96px); line-height: 0.95; letter-spacing: -0.025em; }
      `}</style>

      <div className="atelier-event-grid">
        {/* ========== LEFT: COVER PHOTO ========== */}
        <div style={{ position: 'relative', minHeight: 320 }}>
          {eventInfo.cover_image_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={eventInfo.cover_image_url}
              alt=""
              style={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                objectFit: 'cover',
              }}
            />
          ) : (
            <Scene
              tone="cream"
              aspect="auto"
              style={{ height: '100%', aspectRatio: 'auto', position: 'absolute', inset: 0 }}
            />
          )}
          <div
            style={{
              position: 'absolute',
              top: 28,
              left: 28,
              fontFamily: t.displayFont,
              fontStyle: 'italic',
              fontSize: 28,
              color: t.paper,
              textShadow: `0 2px 16px ${t.ink}88`,
            }}
          >
            Picur
          </div>
          <div
            style={{
              position: 'absolute',
              bottom: 24,
              left: 28,
              right: 28,
              display: 'flex',
              flexWrap: 'wrap',
              gap: 18,
              fontFamily: t.monoFont,
              fontSize: 10,
              letterSpacing: '0.14em',
              color: t.paper,
              textTransform: 'uppercase',
              textShadow: `0 2px 6px ${t.ink}88`,
            }}
          >
            {eventInfo.location && <span>· {eventInfo.location}</span>}
            {dateFmt && <span>· {dateFmt.full}</span>}
          </div>
        </div>

        {/* ========== RIGHT: INVITATION CARD ========== */}
        <div
          className="px-6 sm:px-10 lg:px-16 py-12 lg:py-16"
          style={{
            background: t.paper,
            backgroundImage: `repeating-linear-gradient(0deg, ${t.border}22 0 1px, transparent 1px 28px)`,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            gap: 32,
          }}
        >
          <div>
            <div
              style={{
                fontFamily: t.monoFont,
                fontSize: 10,
                letterSpacing: '0.22em',
                color: t.accent,
                marginBottom: 28,
                textTransform: 'uppercase',
              }}
            >
              · YOU ARE INVITED TO COLLECT
            </div>
            <div
              style={{
                fontFamily: t.displayFont,
                fontWeight: 400,
                fontSize: 22,
                color: t.muted,
                fontStyle: 'italic',
                marginBottom: 14,
              }}
            >
              the photographs from
            </div>
            <h1
              className="atelier-event-name"
              style={{
                fontFamily: t.displayFont,
                fontWeight: 400,
                margin: 0,
              }}
            >
              {head}
              {tail && (
                <>
                  <br />
                  <span style={{ fontStyle: 'italic' }}>{tail}</span>
                </>
              )}
            </h1>

            {(eventInfo.location || dateFmt) && (
              <div
                className="flex flex-wrap gap-x-9 gap-y-4"
                style={{
                  marginTop: 32,
                  marginBottom: 32,
                  padding: '18px 0',
                  borderTop: `1px solid ${t.ink}22`,
                  borderBottom: `1px solid ${t.ink}22`,
                }}
              >
                {dateFmt && (
                  <div>
                    <div
                      style={{
                        fontFamily: t.monoFont,
                        fontSize: 10,
                        letterSpacing: '0.16em',
                        color: t.muted,
                        marginBottom: 6,
                        textTransform: 'uppercase',
                      }}
                    >
                      DATE
                    </div>
                    <div style={{ fontFamily: t.displayFont, fontStyle: 'italic', fontSize: 22 }}>
                      {dateFmt.full}
                    </div>
                  </div>
                )}
                {eventInfo.location && (
                  <div>
                    <div
                      style={{
                        fontFamily: t.monoFont,
                        fontSize: 10,
                        letterSpacing: '0.16em',
                        color: t.muted,
                        marginBottom: 6,
                        textTransform: 'uppercase',
                      }}
                    >
                      PLACE
                    </div>
                    <div style={{ fontFamily: t.displayFont, fontStyle: 'italic', fontSize: 22 }}>
                      {eventInfo.location}
                    </div>
                  </div>
                )}
              </div>
            )}

            <p
              style={{
                fontFamily: t.displayFont,
                fontStyle: 'italic',
                fontSize: 'clamp(18px, 2.2vw, 22px)',
                lineHeight: 1.4,
                color: `${t.ink}cc`,
                maxWidth: 460,
                margin: '0 0 24px',
              }}
            >
              {eventInfo.description ||
                'Take a quick selfie below and every photo of you, captured that day, will be yours to keep.'}
            </p>
          </div>

          <form onSubmit={handleAuthenticate}>
            {eventInfo.requires_passcode && (
              <div style={{ marginBottom: 18 }}>
                <label
                  htmlFor="passcode"
                  style={{
                    fontFamily: t.monoFont,
                    fontSize: 10,
                    letterSpacing: '0.16em',
                    color: t.muted,
                    display: 'block',
                    marginBottom: 8,
                    textTransform: 'uppercase',
                  }}
                >
                  EVENT PASSCODE
                </label>
                <input
                  id="passcode"
                  type="password"
                  value={passcode}
                  onChange={(e) => setPasscode(e.target.value)}
                  placeholder="• • • • • •"
                  required
                  disabled={authenticating}
                  style={{
                    width: '100%',
                    padding: '16px 18px',
                    background: t.bg,
                    border: `1px solid ${t.border}`,
                    fontFamily: t.bodyFont,
                    fontSize: 16,
                    color: t.ink,
                    outline: 'none',
                    letterSpacing: '0.04em',
                  }}
                />
              </div>
            )}

            {error && (
              <div
                style={{
                  marginBottom: 16,
                  padding: '12px 16px',
                  background: `${t.accent}15`,
                  border: `1px solid ${t.accent}55`,
                  color: t.accent,
                  fontFamily: t.bodyFont,
                  fontSize: 13,
                  textAlign: 'center',
                }}
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={authenticating}
              style={{
                width: '100%',
                padding: '20px',
                background: t.ink,
                color: t.paper,
                border: 'none',
                fontFamily: t.bodyFont,
                fontWeight: 600,
                fontSize: 16,
                cursor: authenticating ? 'wait' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 12,
                opacity: authenticating ? 0.7 : 1,
              }}
            >
              {authenticating ? (
                <>
                  <Loader2 className="animate-spin" size={18} />
                  <span>Verifying…</span>
                </>
              ) : (
                <>
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: t.accent,
                    }}
                  />
                  Take selfie &amp; find my photos →
                </>
              )}
            </button>
            <div
              className="flex justify-between flex-wrap gap-y-2"
              style={{
                marginTop: 18,
                fontFamily: t.monoFont,
                fontSize: 9,
                letterSpacing: '0.14em',
                color: t.muted,
                textTransform: 'uppercase',
              }}
            >
              <span>· No app required</span>
              <span>· Photos auto-delete after the event</span>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
