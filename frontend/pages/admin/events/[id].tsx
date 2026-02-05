import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import EventMonitoring from '@/components/EventMonitoring'
import { eventService, EventDetails } from '@/lib/events'
import { Loader2, ArrowLeft, Image as ImageIcon, Trash2, Calendar, Link as LinkIcon, Download, Clock, QrCode } from 'lucide-react'

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
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    })
  }

  if (isLoading) {
    return (
      <ProtectedRoute>
        <AdminLayout>
          <div className="flex items-center justify-center h-64">
            <Loader2 className="w-8 h-8 text-white animate-spin" />
          </div>
        </AdminLayout>
      </ProtectedRoute>
    )
  }

  if (error || !event) {
    return (
      <ProtectedRoute>
        <AdminLayout>
           <div className="max-w-4xl mx-auto p-4 bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl text-center">
            {error || 'Event not found'}
          </div>
        </AdminLayout>
      </ProtectedRoute>
    )
  }

  return (
    <ProtectedRoute>
      <AdminLayout>
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
            <div className="flex items-center gap-4">
              <button 
                onClick={() => router.push('/admin/events')}
                className="p-2 rounded-lg hover:bg-white/10 transition-colors"
               >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <h1 className="text-3xl font-bold">{event.name}</h1>
            </div>
            
            <div className="flex gap-3">
              <button
                onClick={() => router.push(`/admin/events/${event.event_id}/photos`)}
                className="flex items-center gap-2 bg-white text-black px-4 py-2 rounded-lg font-semibold hover:bg-gray-200 transition-colors"
              >
                <ImageIcon className="w-4 h-4" />
                Manage Photos
              </button>
              <button
                onClick={handleDelete}
                disabled={isDeleting}
                className="flex items-center gap-2 bg-red-500/10 text-red-500 border border-red-500/20 px-4 py-2 rounded-lg font-semibold hover:bg-red-500/20 transition-colors disabled:opacity-50"
              >
                 {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                {isDeleting ? 'Deleting...' : 'Delete Event'}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
            <div className="lg:col-span-2 glass-card p-6 rounded-2xl">
              <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
                 Details
              </h2>
              <div className="space-y-4">
                <div className="flex items-center justify-between p-3 rounded-xl bg-white/5">
                  <span className="text-gray-400 flex items-center gap-2"><Calendar className="w-4 h-4" /> Date</span>
                  <span className="font-medium">{formatDate(event.date)}</span>
                </div>
                <div className="flex items-center justify-between p-3 rounded-xl bg-white/5">
                  <span className="text-gray-400 flex items-center gap-2"><LinkIcon className="w-4 h-4" /> Slug</span>
                  <span className="font-mono">{event.slug}</span>
                </div>
                 <div className="flex flex-col gap-2 p-3 rounded-xl bg-white/5">
                  <span className="text-gray-400 flex items-center gap-2"><LinkIcon className="w-4 h-4" /> Guest Link</span>
                  <a href={event.guest_link} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 break-all transition-colors">
                    {event.guest_link}
                  </a>
                </div>
                <div className="flex items-center justify-between p-3 rounded-xl bg-white/5">
                  <span className="text-gray-400 flex items-center gap-2"><Download className="w-4 h-4" /> Downloads</span>
                  <span className={`px-2 py-0.5 rounded text-sm ${event.allow_downloads ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                     {event.allow_downloads ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
                <div className="flex items-center justify-between p-3 rounded-xl bg-white/5">
                  <span className="text-gray-400 flex items-center gap-2"><Clock className="w-4 h-4" /> Retention</span>
                  <span>{event.retention_days} days</span>
                </div>
              </div>
            </div>

            <div className="glass-card p-6 rounded-2xl flex flex-col items-center justify-center text-center">
              <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
                 <QrCode className="w-5 h-5" /> QR Code
              </h2>
              <div className="bg-white p-4 rounded-xl mb-4">
                 <img
                  src={eventService.getQRCodeUrl(event.event_id)}
                  alt="Event QR Code"
                  className="w-48 h-48 object-contain"
                />
              </div>
              <p className="text-sm text-gray-400">
                Share this QR code with guests to access the event
              </p>
            </div>
          </div>

          {/* Event Monitoring Dashboard */}
          <EventMonitoring eventId={event.event_id} />
        </div>
      </AdminLayout>
    </ProtectedRoute>
  )
}
