import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import api from '@/lib/api'
import { Loader2 } from 'lucide-react'
import { LUMIERE, Scene, CornerMarks } from '@/components/lumiere'

interface EventInfo {
  event_id: string
  name: string
  date: string
  requires_passcode: boolean
  location?: string
  description?: string
  cover_image_url?: string
}

function splitName(name: string): { head: string; tail?: string } {
  const m = name.match(/^(.+?)\s*([&×x])\s*(.+)$/i)
  if (!m) return { head: name }
  return { head: m[1].trim(), tail: `${m[2]} ${m[3].trim()}` }
}

function formatDate(iso?: string): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString('en-US', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

export default function GuestEventAccess() {
  const t = LUMIERE
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
      // not in the response body. Non-sensitive metadata for downstream pages
      // lives in sessionStorage — per-tab, cleared on close.
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
        className="lumiere"
        style={{
          minHeight: '100vh',
          background: t.bg,
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
        className="lumiere px-6"
        style={{
          minHeight: '100vh',
          background: t.bg,
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
              letterSpacing: '0.22em',
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
              color: t.ink,
            }}
          >
            <span style={{ fontStyle: 'italic' }}>Not found.</span>
          </h1>
          <p
            style={{
              marginTop: 16,
              fontFamily: t.bodyFont,
              fontSize: 14,
              color: t.inkDim,
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
      className="lumiere"
      style={{
        minHeight: '100vh',
        position: 'relative',
        overflow: 'hidden',
        background: t.bg,
        color: t.ink,
        fontFamily: t.bodyFont,
      }}
    >
      <Head>
        <title>{eventInfo.name} — PicUr</title>
      </Head>

      <style>{`
        .lumiere-event-name { font-size: clamp(56px, 14vw, 168px); line-height: 0.88; letter-spacing: -0.03em; }
      `}</style>

      {/* full-bleed cinematic backdrop */}
      <div style={{ position: 'absolute', inset: 0 }}>
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
            tone="dusk"
            aspect="auto"
            style={{ height: '100%', aspectRatio: 'auto', position: 'absolute', inset: 0, borderRadius: 0 }}
          />
        )}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: `linear-gradient(180deg, ${t.bg}88 0%, ${t.bg}44 40%, ${t.bg}dd 100%)`,
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
      </div>

      <CornerMarks inset={28} size={18} opacity={1} />

      <div
        className="px-6 sm:px-12 lg:px-20"
        style={{
          position: 'relative',
          minHeight: '100vh',
          paddingTop: 40,
          paddingBottom: 48,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Top metadata bar */}
        <div className="flex justify-between items-center gap-4 flex-wrap">
          <div
            style={{
              fontFamily: t.displayFont,
              fontStyle: 'italic',
              fontSize: 28,
              color: t.ink,
            }}
          >
            Picur
          </div>
          <div
            style={{
              fontFamily: t.monoFont,
              fontSize: 10,
              letterSpacing: '0.22em',
              color: t.accent,
              textTransform: 'uppercase',
            }}
          >
            REEL 02 · CONFIDENTIAL
          </div>
        </div>

        {/* Main content bottom-aligned */}
        <div style={{ marginTop: 'auto', maxWidth: 880, paddingTop: 48 }}>
          <div
            style={{
              fontFamily: t.monoFont,
              fontSize: 11,
              letterSpacing: '0.24em',
              color: t.accent,
              marginBottom: 24,
              textTransform: 'uppercase',
            }}
          >
            — YOU ARE INVITED TO COLLECT —
          </div>
          <h1
            className="lumiere-event-name"
            style={{
              fontFamily: t.displayFont,
              fontWeight: 400,
              margin: 0,
              color: t.ink,
            }}
          >
            {head}
            {tail && (
              <>
                <br />
                <span style={{ fontStyle: 'italic', color: t.accent }}>{tail}</span>
              </>
            )}
          </h1>
          {(eventInfo.location || dateFmt) && (
            <div
              className="flex flex-wrap gap-x-7 gap-y-2"
              style={{
                marginTop: 24,
                fontFamily: t.monoFont,
                fontSize: 11,
                letterSpacing: '0.2em',
                color: t.inkDim,
                textTransform: 'uppercase',
              }}
            >
              {dateFmt && <span>· {dateFmt}</span>}
              {eventInfo.location && <span>· {eventInfo.location}</span>}
            </div>
          )}

          {eventInfo.description && (
            <p
              style={{
                marginTop: 28,
                fontFamily: t.displayFont,
                fontStyle: 'italic',
                fontSize: 'clamp(18px, 2.2vw, 22px)',
                lineHeight: 1.4,
                color: t.inkDim,
                maxWidth: 560,
              }}
            >
              {eventInfo.description}
            </p>
          )}

          {/* passcode bar */}
          <form
            onSubmit={handleAuthenticate}
            style={{
              marginTop: 40,
              background: `${t.paper}dd`,
              border: `1px solid ${t.accent}66`,
              backdropFilter: 'blur(8px)',
              WebkitBackdropFilter: 'blur(8px)',
              padding: 20,
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
            }}
          >
            <div className="flex flex-col sm:flex-row sm:items-center gap-4">
              {eventInfo.requires_passcode ? (
                <div style={{ flex: 1 }}>
                  <div
                    style={{
                      fontFamily: t.monoFont,
                      fontSize: 9,
                      letterSpacing: '0.22em',
                      color: t.muted,
                      marginBottom: 6,
                      textTransform: 'uppercase',
                    }}
                  >
                    · EVENT PASSCODE
                  </div>
                  <input
                    id="passcode"
                    type="password"
                    value={passcode}
                    onChange={(e) => setPasscode(e.target.value)}
                    placeholder="enter passcode…"
                    required
                    disabled={authenticating}
                    style={{
                      width: '100%',
                      padding: 0,
                      border: 'none',
                      background: 'transparent',
                      fontFamily: t.displayFont,
                      fontSize: 24,
                      fontStyle: 'italic',
                      color: t.ink,
                      outline: 'none',
                    }}
                  />
                </div>
              ) : (
                <div style={{ flex: 1 }}>
                  <div
                    style={{
                      fontFamily: t.monoFont,
                      fontSize: 9,
                      letterSpacing: '0.22em',
                      color: t.muted,
                      marginBottom: 6,
                      textTransform: 'uppercase',
                    }}
                  >
                    · NO PASSCODE NEEDED
                  </div>
                  <div
                    style={{
                      fontFamily: t.displayFont,
                      fontSize: 22,
                      fontStyle: 'italic',
                      color: t.ink,
                    }}
                  >
                    just a selfie
                  </div>
                </div>
              )}
              <button
                type="submit"
                disabled={authenticating}
                style={{
                  padding: '18px 28px',
                  background: t.accent,
                  color: t.bg,
                  border: 'none',
                  fontFamily: t.bodyFont,
                  fontWeight: 600,
                  fontSize: 14,
                  letterSpacing: '0.06em',
                  cursor: authenticating ? 'wait' : 'pointer',
                  flex: '0 0 auto',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 10,
                  opacity: authenticating ? 0.7 : 1,
                }}
              >
                {authenticating ? (
                  <>
                    <Loader2 className="animate-spin" size={16} />
                    VERIFYING…
                  </>
                ) : (
                  'FIND ME →'
                )}
              </button>
            </div>
            {error && (
              <div
                style={{
                  padding: '10px 14px',
                  background: `${t.accent}1a`,
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
          </form>
          <div
            className="flex justify-between flex-wrap gap-y-2"
            style={{
              marginTop: 18,
              fontFamily: t.monoFont,
              fontSize: 9,
              letterSpacing: '0.2em',
              color: t.muted,
              textTransform: 'uppercase',
            }}
          >
            <span>· no app · just a selfie</span>
            <span>· photos auto-delete after the event</span>
          </div>
        </div>
      </div>
    </div>
  )
}
