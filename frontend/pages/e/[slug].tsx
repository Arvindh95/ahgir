import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'

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
      <div style={styles.container}>
        <div style={styles.card}>
          <p>Loading event...</p>
        </div>
      </div>
    )
  }

  if (error && !eventInfo) {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <h1 style={styles.title}>Error</h1>
          <p style={styles.error}>{error}</p>
        </div>
      </div>
    )
  }

  if (!eventInfo) {
    return null
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>{eventInfo.name}</h1>
        <p style={styles.date}>
          {new Date(eventInfo.date).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
          })}
        </p>
        
        <div style={styles.divider} />
        
        <p style={styles.description}>
          Welcome! Scan your face to find photos from this event.
        </p>

        <form onSubmit={handleAuthenticate} style={styles.form}>
          {eventInfo.requires_passcode && (
            <div style={styles.inputGroup}>
              <label htmlFor="passcode" style={styles.label}>
                Event Passcode
              </label>
              <input
                id="passcode"
                type="password"
                value={passcode}
                onChange={(e) => setPasscode(e.target.value)}
                placeholder="Enter passcode"
                style={styles.input}
                required
                disabled={authenticating}
              />
            </div>
          )}

          {error && <p style={styles.error}>{error}</p>}

          <button
            type="submit"
            style={styles.button}
            disabled={authenticating}
          >
            {authenticating ? 'Authenticating...' : 'Continue to Scanner'}
          </button>
        </form>
      </div>
    </div>
  )
}

const styles = {
  container: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: '100vh',
    backgroundColor: '#f5f5f5',
    padding: '20px',
  } as React.CSSProperties,
  card: {
    backgroundColor: 'white',
    borderRadius: '8px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
    padding: '40px',
    maxWidth: '500px',
    width: '100%',
  } as React.CSSProperties,
  title: {
    fontSize: '28px',
    fontWeight: 'bold',
    marginBottom: '8px',
    textAlign: 'center',
    color: '#333',
  } as React.CSSProperties,
  date: {
    fontSize: '16px',
    color: '#666',
    textAlign: 'center',
    marginBottom: '20px',
  } as React.CSSProperties,
  divider: {
    height: '1px',
    backgroundColor: '#e0e0e0',
    margin: '20px 0',
  } as React.CSSProperties,
  description: {
    fontSize: '16px',
    color: '#555',
    textAlign: 'center',
    marginBottom: '30px',
    lineHeight: '1.5',
  } as React.CSSProperties,
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
  } as React.CSSProperties,
  inputGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  } as React.CSSProperties,
  label: {
    fontSize: '14px',
    fontWeight: '500',
    color: '#333',
  } as React.CSSProperties,
  input: {
    padding: '12px',
    fontSize: '16px',
    border: '1px solid #ddd',
    borderRadius: '4px',
    outline: 'none',
  } as React.CSSProperties,
  button: {
    padding: '14px',
    fontSize: '16px',
    fontWeight: '600',
    color: 'white',
    backgroundColor: '#007bff',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  } as React.CSSProperties,
  error: {
    color: '#dc3545',
    fontSize: '14px',
    textAlign: 'center',
    margin: '0',
  } as React.CSSProperties,
}
