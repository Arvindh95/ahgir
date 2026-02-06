import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import { eventService, Event } from '@/lib/events'
import { Plus, Calendar, Image as ImageIcon, Users, ScanFace, ArrowRight } from 'lucide-react'
import EventCardSkeletonGrid from '@/components/skeletons/EventCardSkeleton'

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
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    })
  }

  return (
    <ProtectedRoute>
      <AdminLayout>
        <div className="max-w-7xl mx-auto">
          <div className="flex justify-between items-center mb-8">
            <h1 className="text-3xl font-bold">My Events</h1>
            <button
              onClick={() => router.push('/admin/events/create')}
              className="flex items-center gap-2 bg-white text-black px-4 py-2 rounded-lg font-semibold hover:bg-gray-200 transition-colors"
            >
              <Plus className="w-5 h-5" />
              Create Event
            </button>
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl">
              {error}
            </div>
          )}

          {isLoading ? (
            <EventCardSkeletonGrid />
          ) : events.length === 0 ? (
            <div className="glass-card p-12 text-center rounded-2xl">
              <p className="text-xl text-gray-300 mb-2">No events yet</p>
              <p className="text-gray-500">Create your first event to get started</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {events.map((event) => (
                <div
                  key={event.event_id}
                  onClick={() => router.push(`/admin/events/${event.event_id}`)}
                  className="glass-card p-6 rounded-2xl cursor-pointer hover:bg-white/10 transition-colors group relative overflow-hidden"
                >
                  <div className="relative z-10">
                    <div className="flex justify-between items-start mb-4">
                      <h3 className="text-xl font-bold truncate pr-4">{event.name}</h3>
                      <ArrowRight className="w-5 h-5 text-gray-500 group-hover:text-white transition-colors group-hover:translate-x-1 transform" />
                    </div>
                    
                    <div className="space-y-2 mb-6">
                      <div className="flex items-center gap-2 text-gray-400 text-sm">
                        <Calendar className="w-4 h-4" />
                        <span>{formatDate(event.date)}</span>
                      </div>
                      <div className="flex items-center gap-2 text-gray-400 text-sm">
                        <span className="font-mono bg-white/5 px-2 py-0.5 rounded text-xs">/{event.slug}</span>
                      </div>
                    </div>

                    {event.photo_count !== undefined && (
                      <div className="grid grid-cols-3 gap-2 border-t border-white/10 pt-4 mt-4">
                        <div className="text-center">
                           <div className="flex items-center justify-center gap-1 text-gray-400 text-xs mb-1">
                              <ImageIcon className="w-3 h-3" /> Photos
                           </div>
                           <span className="font-semibold">{event.photo_count}</span>
                        </div>
                        <div className="text-center border-l border-white/10">
                           <div className="flex items-center justify-center gap-1 text-gray-400 text-xs mb-1">
                              <ScanFace className="w-3 h-3" /> Indexed
                           </div>
                           <span className="font-semibold">{event.indexed_count}</span>
                        </div>
                        <div className="text-center border-l border-white/10">
                           <div className="flex items-center justify-center gap-1 text-gray-400 text-xs mb-1">
                              <Users className="w-3 h-3" /> Faces
                           </div>
                           <span className="font-semibold">{event.face_count}</span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </AdminLayout>
    </ProtectedRoute>
  )
}
