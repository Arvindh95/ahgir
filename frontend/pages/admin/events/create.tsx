import { useState, FormEvent } from 'react'
import { useRouter } from 'next/router'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import { eventService } from '@/lib/events'

export default function CreateEventPage() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [date, setDate] = useState('')
  const [passcode, setPasscode] = useState('')
  const [allowDownloads, setAllowDownloads] = useState(true)
  const [retentionDays, setRetentionDays] = useState(90)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const validateForm = (): boolean => {
    if (!name || !date) {
      setError('Name and date are required')
      return false
    }

    if (retentionDays < 1 || retentionDays > 365) {
      setError('Retention days must be between 1 and 365')
      return false
    }

    return true
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')

    if (!validateForm()) {
      return
    }

    setIsLoading(true)

    try {
      const event = await eventService.createEvent({
        name,
        date,
        passcode: passcode || undefined,
        allow_downloads: allowDownloads,
        retention_days: retentionDays,
      })
      router.push(`/admin/events/${event.event_id}`)
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to create event')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <ProtectedRoute>
      <AdminLayout>
        <div style={{ maxWidth: '600px', margin: '0 auto' }}>
          <h1>Create Event</h1>

          <form onSubmit={handleSubmit} style={{ backgroundColor: 'white', padding: '30px', borderRadius: '8px' }}>
            <div style={{ marginBottom: '20px' }}>
              <label htmlFor="name" style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                Event Name *
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Smith Wedding"
                style={{ width: '100%', padding: '10px', fontSize: '14px', border: '1px solid #ddd', borderRadius: '4px' }}
                disabled={isLoading}
              />
            </div>

            <div style={{ marginBottom: '20px' }}>
              <label htmlFor="date" style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                Event Date *
              </label>
              <input
                id="date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                style={{ width: '100%', padding: '10px', fontSize: '14px', border: '1px solid #ddd', borderRadius: '4px' }}
                disabled={isLoading}
              />
            </div>

            <div style={{ marginBottom: '20px' }}>
              <label htmlFor="passcode" style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                Passcode (optional)
              </label>
              <input
                id="passcode"
                type="text"
                value={passcode}
                onChange={(e) => setPasscode(e.target.value)}
                placeholder="Leave empty for no passcode"
                style={{ width: '100%', padding: '10px', fontSize: '14px', border: '1px solid #ddd', borderRadius: '4px' }}
                disabled={isLoading}
              />
              <small style={{ color: '#666' }}>Guests will need this passcode to access the event</small>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={allowDownloads}
                  onChange={(e) => setAllowDownloads(e.target.checked)}
                  style={{ marginRight: '10px' }}
                  disabled={isLoading}
                />
                <span style={{ fontWeight: 'bold' }}>Allow guests to download photos</span>
              </label>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <label htmlFor="retentionDays" style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                Retention Days
              </label>
              <input
                id="retentionDays"
                type="number"
                value={retentionDays}
                onChange={(e) => setRetentionDays(parseInt(e.target.value))}
                min="1"
                max="365"
                style={{ width: '100%', padding: '10px', fontSize: '14px', border: '1px solid #ddd', borderRadius: '4px' }}
                disabled={isLoading}
              />
              <small style={{ color: '#666' }}>Number of days to keep event data (1-365)</small>
            </div>

            {error && (
              <div style={{ color: 'red', marginBottom: '20px', padding: '10px', backgroundColor: '#ffebee', borderRadius: '4px' }}>
                {error}
              </div>
            )}

            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                type="submit"
                disabled={isLoading}
                style={{
                  flex: 1,
                  padding: '12px',
                  backgroundColor: '#0070f3',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: isLoading ? 'not-allowed' : 'pointer',
                  fontSize: '16px',
                }}
              >
                {isLoading ? 'Creating...' : 'Create Event'}
              </button>
              <button
                type="button"
                onClick={() => router.push('/admin/events')}
                disabled={isLoading}
                style={{
                  padding: '12px 20px',
                  backgroundColor: '#f5f5f5',
                  color: '#333',
                  border: '1px solid #ddd',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '16px',
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      </AdminLayout>
    </ProtectedRoute>
  )
}
