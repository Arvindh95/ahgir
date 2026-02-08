import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import axios from 'axios'
import { Calendar, MapPin, Eye, Loader2, ArrowRight } from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface EventInfo {
  event_id: string
  name: string
  date: string
  requires_passcode: boolean
  location?: string
  description?: string
  cover_image_url?: string
}

export default function GuestEventAccess() {
  const router = useRouter()
  const { slug } = router.query

  const [eventInfo, setEventInfo] = useState<EventInfo | null>(null)
  const [passcode, setPasscode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [authenticating, setAuthenticating] = useState(false)
  const [showPasscode, setShowPasscode] = useState(false)

  useEffect(() => {
    if (!slug) return

    const fetchEventInfo = async () => {
      try {
        setLoading(true)
        const response = await axios.get(`${API_URL}/e/${slug}`)
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
      const response = await axios.post(`${API_URL}/e/${slug}/auth`, payload)

      localStorage.setItem('event_token', response.data.event_token)
      localStorage.setItem('event_id', response.data.event_id)
      localStorage.setItem('event_name', response.data.event_name)
      localStorage.setItem('allow_downloads', response.data.allow_downloads)

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
      <div className="min-h-screen bg-black flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-white animate-spin" />
      </div>
    )
  }

  if (error && !eventInfo) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center p-4">
        <div className="glass-card max-w-md w-full p-8 rounded-2xl text-center">
          <h1 className="text-2xl font-bold text-red-500 mb-2">Error</h1>
          <p className="text-gray-300">{error}</p>
        </div>
      </div>
    )
  }

  if (!eventInfo) return null

  const hasCover = !!eventInfo.cover_image_url

  return (
    <div className="min-h-screen relative text-white overflow-hidden">
      <Head><title>Event - PicUr</title></Head>
      {/* Background: cover image or dark gradient */}
      {hasCover ? (
        <>
          <div className="absolute inset-0 bg-black" />
          <img
            src={eventInfo.cover_image_url}
            alt=""
            className="absolute inset-0 w-full h-full object-cover object-center"
          />
          {/* Dark overlay for readability */}
          <div className="absolute inset-0 bg-gradient-to-b from-black/40 via-black/50 to-black/80" />
        </>
      ) : (
        <div className="absolute inset-0 bg-gradient-to-br from-black via-[#0a0a0a] to-[#050505]">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-500/10 rounded-full blur-[120px]" />
        </div>
      )}

      {/* Content */}
      <div className="relative z-10 min-h-screen flex flex-col">
        {/* Top nav placeholder for branding */}
        <nav className="flex items-center justify-between px-6 py-4">
          <div className="w-10 h-10" />
          {/* "View My Photos" button shown after auth would go here */}
        </nav>

        {/* Hero content - centered vertically */}
        <div className="flex-1 flex flex-col items-center justify-center px-4 pb-16">
          {/* Event Title */}
          <h1 className="text-5xl md:text-7xl font-bold text-center leading-tight tracking-tight mb-4 drop-shadow-lg">
            {eventInfo.name}
          </h1>

          {/* Description */}
          {eventInfo.description && (
            <p className="text-lg md:text-xl text-gray-200 text-center max-w-2xl mx-auto mb-6 drop-shadow">
              {eventInfo.description}
            </p>
          )}

          {/* CTA Card */}
          <div className="w-full max-w-md mt-4">
            <div className={`rounded-2xl p-6 md:p-8 ${hasCover ? 'bg-black/60 backdrop-blur-md border border-white/10' : 'glass-card'}`}>
              <form onSubmit={handleAuthenticate} className="space-y-5">
                {eventInfo.requires_passcode && (
                  <div className="space-y-2">
                    <label htmlFor="passcode" className="block text-sm font-medium text-gray-300 ml-1">
                      Event Passcode
                    </label>
                    <input
                      id="passcode"
                      type="password"
                      value={passcode}
                      onChange={(e) => setPasscode(e.target.value)}
                      placeholder="Enter passcode"
                      className="w-full px-4 py-3 rounded-xl bg-white/10 border border-white/15 focus:border-white/40 focus:outline-none text-white placeholder:text-gray-500 transition-all"
                      required
                      disabled={authenticating}
                    />
                  </div>
                )}

                {error && (
                  <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm text-center">
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={authenticating}
                  className="group w-full bg-white text-black font-semibold py-3.5 px-4 rounded-xl hover:bg-gray-100 transition-all active:scale-[0.98] flex items-center justify-center gap-2"
                >
                  {authenticating ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      <span>Verifying...</span>
                    </>
                  ) : (
                    <>
                      <Eye className="w-5 h-5" />
                      <span>Browse My Photos</span>
                      <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                    </>
                  )}
                </button>
              </form>
            </div>
          </div>

          {/* Location & Date footer */}
          <div className="flex items-center justify-center gap-6 mt-8 text-gray-300 text-sm md:text-base">
            {eventInfo.location && (
              <div className="flex items-center gap-2">
                <MapPin className="w-4 h-4" />
                <span>{eventInfo.location}</span>
              </div>
            )}
            {eventInfo.date && (
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4" />
                <span>
                  {new Date(eventInfo.date).toLocaleDateString('en-US', {
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric'
                  })}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="text-center text-gray-500 text-xs pb-4">
          <p>© {new Date().getFullYear()} PicUr. All rights reserved.</p>
        </div>
      </div>
    </div>
  )
}
