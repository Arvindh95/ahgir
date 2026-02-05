import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import EventMonitoring from '@/components/EventMonitoring'
import { eventService, EventDetails } from '@/lib/events'

export default function EventDetailsPage() {
  const router = useRouter()
  const { id } = router.query
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [isDeleting, setIsDeleting] = useState(false)

  useEffect(() => {
    if (id && typeof id === 'string') {
      loadEvent(id)
    }
  }, [id])

  const loadEvent = async (eventId: string) => {
    try {
      setIsLoading(true)
      const data = await eventService.getEvent(eventId)
      setEvent(data)
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to load event')
    } finally {
      setIsLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!event || !confirm('Are you sure you want to delete this event? This action cannot be undone.')) {
      return
    }

    try {
      setIsDeleting(true)
      await eventService.deleteEvent(event.event_id)
      router.push('/admin/events')
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to delete event')
      setIsDeleting(false)
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString()
  }

  if (isLoading) {
    return (
      <ProtectedRoute>
        <AdminLayout>
          <p>Loading event...</p>
        </AdminLayout>
      </ProtectedRoute>
    )
  }

  if (error || !event) {
    return (
      <ProtectedRoute>
        <AdminLayout>
          <div style={{ color: 'red', padding: '20px', backgroundColor: '#ffebee', borderRadius: '4px' }}>
            {error || 'Event not found'}
          </div>
        </AdminLayout>
      </ProtectedRoute>
    )
  }

  return (
    <ProtectedRoute>
      <AdminLayout>
        <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px' }}>
            <h1>{event.name}</h1>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={() => router.push(`/admin/events/${event.event_id}/photos`)}
                style={{
                  backgroundColor: '#0070f3',
                  color: 'white',
                  border: 'none',
                  padding: '10px 20px',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                Manage Photos
              </button>
              <button
                onClick={handleDelete}
                disabled={isDeleting}
                style={{
                  backgroundColor: '#dc3545',
                  color: 'white',
                  border: 'none',
                  padding: '10px 20px',
                  borderRadius: '4px',
                  cursor: isDeleting ? 'not-allowed' : 'pointer',
                }}
              >
                {isDeleting ? 'Deleting...' : 'Delete Event'}
              </button>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '30px' }}>
            <div style={{ backgroundColor: 'white', padding: '20px', borderRadius: '8px' }}>
              <h2 style={{ marginTop: 0 }}>Event Details</h2>
              <div style={{ marginBottom: '10px' }}>
                <strong>Date:</strong> {formatDate(event.date)}
              </div>
              <div style={{ marginBottom: '10px' }}>
                <strong>Slug:</strong> {event.slug}
              </div>
              <div style={{ marginBottom: '10px' }}>
                <strong>Guest Link:</strong>{' '}
                <a href={event.guest_link} target="_blank" rel="noopener noreferrer" style={{ color: '#0070f3' }}>
                  {event.guest_link}
                </a>
              </div>
              <div style={{ marginBottom: '10px' }}>
                <strong>Downloads:</strong> {event.allow_downloads ? 'Enabled' : 'Disabled'}
              </div>
              <div style={{ marginBottom: '10px' }}>
                <strong>Retention:</strong> {event.retention_days} days
              </div>
              <div style={{ marginBottom: '10px' }}>
                <strong>Created:</strong> {formatDate(event.created_at)}
              </div>
            </div>

            <div style={{ backgroundColor: 'white', padding: '20px', borderRadius: '8px' }}>
              <h2 style={{ marginTop: 0 }}>QR Code</h2>
              <p style={{ color: '#666', fontSize: '14px', marginBottom: '15px' }}>
                Share this QR code with guests to access the event
              </p>
              <img
                src={eventService.getQRCodeUrl(event.event_id)}
                alt="Event QR Code"
                style={{ maxWidth: '200px', border: '1px solid #ddd', borderRadius: '4px' }}
              />
            </div>
          </div>

          {/* Event Monitoring Dashboard */}
          <EventMonitoring eventId={event.event_id} />
        </div>
      </AdminLayout>
    </ProtectedRoute>
  )
}
