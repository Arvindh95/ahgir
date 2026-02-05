import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'
import { Calendar, MapPin, Camera, ArrowRight, Loader2 } from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface EventInfo {
  event_id: string
  name: string
  date: string
  requires_passcode: boolean
}

export default function GuestEventAccess() {
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
      
      // Store event token
      localStorage.setItem('event_token', response.data.event_token)
      localStorage.setItem('event_id', response.data.event_id)
      localStorage.setItem('event_name', response.data.event_name)
      localStorage.setItem('allow_downloads', response.data.allow_downloads)
      
      // Navigate to scanner
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

  if (!eventInfo) {
    return null
  }

  return (
    <div className="min-h-screen bg-black text-white relative overflow-hidden flex flex-col items-center justify-center p-4">
      {/* Background Ambience */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-blue-900/20 rounded-full blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-purple-900/20 rounded-full blur-[120px]" />
      </div>

      <div className="relative z-10 w-full max-w-lg">
        {/* Header / Logo Area */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-white/5 border border-white/10 mb-6 backdrop-blur-md">
            <Camera className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-4xl md:text-5xl font-bold tracking-tight mb-4">
            {eventInfo.name}
          </h1>
          <div className="flex items-center justify-center gap-6 text-gray-400 text-sm md:text-base">
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4" />
              <span>
                {new Date(eventInfo.date).toLocaleDateString('en-US', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric'
                })}
              </span>
            </div>
          </div>
        </div>

        {/* Main Card */}
        <div className="glass-card p-8 rounded-2xl backdrop-blur-xl">
          <div className="mb-8 text-center">
            <h2 className="text-xl font-semibold mb-2">View Your Photos</h2>
            <p className="text-gray-400 text-sm">
              Enter the event details below to access the gallery and find your moments.
            </p>
          </div>

          <form onSubmit={handleAuthenticate} className="space-y-6">
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
                  className="glass-input w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 focus:ring-2 focus:ring-white/20 transition-all placeholder:text-gray-600"
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
                  <span>Access Gallery</span>
                  <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </>
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <div className="mt-12 text-center text-gray-500 text-xs">
          <p>© {new Date().getFullYear()} PicUr. All rights reserved.</p>
        </div>
      </div>
    </div>
  )
}
