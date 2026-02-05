import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import { eventService, Event } from '@/lib/events'

export default function EventsPage() {
  const router = useRouter()
  const [events, setEvents] = useState<Event[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    loadEvents()
  }, [])

  const loadEvents = async () => {
    try {
      setIsLoading(true)
      const data = await eventService.getEvents()
      setEvents(data)
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to load events')
    } finally {
      setIsLoading(false)
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString()
  }

  return (
    <ProtectedRoute>
      <AdminLayout>
        <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px' }}>
            <h1>My Events</h1>
            <button
              onClick={() => router.push('/admin/events/create')}
              style={{
                backgroundColor: '#0070f3',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '16px',
              }}
            >
              Create Event
            </button>
          </div>

          {error && (
            <div style={{ color: 'red', marginBottom: '20px', padding: '10px', backgroundColor: '#ffebee', borderRadius: '4px' }}>
              {error}
            </div>
          )}

          {isLoading ? (
            <p>Loading events...</p>
          ) : events.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', backgroundColor: 'white', borderRadius: '8px' }}>
              <p style={{ fontSize: '18px', color: '#666' }}>No events yet</p>
              <p style={{ color: '#999' }}>Create your first event to get started</p>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '20px' }}>
              {events.map((event) => (
                <div
                  key={event.event_id}
                  onClick={() => router.push(`/admin/events/${event.event_id}`)}
                  style={{
                    backgroundColor: 'white',
                    padding: '20px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                    transition: 'box-shadow 0.2s',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.boxShadow = '0 4px 8px rgba(0,0,0,0.15)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.boxShadow = '0 2px 4px rgba(0,0,0,0.1)'
                  }}
                >
                  <h3 style={{ marginTop: 0, marginBottom: '10px' }}>{event.name}</h3>
                  <p style={{ color: '#666', fontSize: '14px', marginBottom: '5px' }}>
                    Date: {formatDate(event.date)}
                  </p>
                  <p style={{ color: '#666', fontSize: '14px', marginBottom: '5px' }}>
                    Slug: {event.slug}
                  </p>
                  {event.photo_count !== undefined && (
                    <div style={{ marginTop: '15px', paddingTop: '15px', borderTop: '1px solid #eee' }}>
                      <p style={{ fontSize: '14px', marginBottom: '5px' }}>
                        Photos: {event.photo_count}
                      </p>
                      <p style={{ fontSize: '14px', marginBottom: '5px' }}>
                        Indexed: {event.indexed_count}
                      </p>
                      <p style={{ fontSize: '14px', marginBottom: '0' }}>
                        Faces: {event.face_count}
                      </p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </AdminLayout>
    </ProtectedRoute>
  )
}
