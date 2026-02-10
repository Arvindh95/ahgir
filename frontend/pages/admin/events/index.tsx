import { useEffect, useState, useMemo } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import ConfirmModal from '@/components/ConfirmModal'
import { eventService, Event } from '@/lib/events'
import { useToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/errors'
import { Plus, Calendar, Image as ImageIcon, Users, ScanFace, ArrowRight, Search, Check, Trash2 } from 'lucide-react'
import EventCardSkeletonGrid from '@/components/skeletons/EventCardSkeleton'

type SortOption = 'newest' | 'oldest' | 'photos' | 'name'

export default function EventsPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [events, setEvents] = useState<Event[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<SortOption>('newest')
  const [selectedEvents, setSelectedEvents] = useState<Set<string>>(new Set())
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  useEffect(() => {
    loadEvents()
  }, [])

  const loadEvents = async () => {
    try {
      setIsLoading(true)
      const data = await eventService.getEvents()
      setEvents(data)
    } catch (err: any) {
      setError(getErrorMessage(err, 'loading events'))
    } finally {
      setIsLoading(false)
    }
  }

  const filteredEvents = useMemo(() => {
    let result = events

    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter(e =>
        e.name.toLowerCase().includes(q) || e.slug.toLowerCase().includes(q)
      )
    }

    switch (sort) {
      case 'oldest':
        result = [...result].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
        break
      case 'photos':
        result = [...result].sort((a, b) => (b.photo_count || 0) - (a.photo_count || 0))
        break
      case 'name':
        result = [...result].sort((a, b) => a.name.localeCompare(b.name))
        break
      case 'newest':
      default:
        result = [...result].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
        break
    }

    return result
  }, [events, search, sort])

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    })
  }

  const toggleSelect = (eventId: string) => {
    setSelectedEvents(prev => {
      const next = new Set(prev)
      if (next.has(eventId)) next.delete(eventId)
      else next.add(eventId)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedEvents.size === filteredEvents.length) {
      setSelectedEvents(new Set())
    } else {
      setSelectedEvents(new Set(filteredEvents.map(e => e.event_id)))
    }
  }

  const handleBulkDelete = async () => {
    setIsDeleting(true)
    let deleted = 0
    for (const eventId of Array.from(selectedEvents)) {
      try {
        await eventService.deleteEvent(eventId)
        deleted++
      } catch { }
    }
    setIsDeleting(false)
    setShowDeleteConfirm(false)
    setSelectedEvents(new Set())
    toast(`Deleted ${deleted} event${deleted !== 1 ? 's' : ''}`, 'success')
    loadEvents()
  }

  return (
    <ProtectedRoute>
      <Head><title>Events - PicUr</title></Head>
      <AdminLayout>
        <div className="max-w-7xl mx-auto">
          <div className="flex justify-between items-center mb-6">
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

          {!isLoading && events.length > 0 && (
            <div className="flex flex-col sm:flex-row gap-3 mb-6">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type="text"
                  placeholder="Search events..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-white/20 transition-colors"
                />
              </div>
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as SortOption)}
                className="px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:border-white/20 transition-colors"
              >
                <option value="newest" className="bg-black">Newest first</option>
                <option value="oldest" className="bg-black">Oldest first</option>
                <option value="photos" className="bg-black">Most photos</option>
                <option value="name" className="bg-black">Name A-Z</option>
              </select>
            </div>
          )}

          {/* Bulk actions toolbar */}
          {selectedEvents.size > 0 && (
            <div className="mb-6 flex items-center justify-between gap-3 glass-card p-4 rounded-xl">
              <div className="flex items-center gap-4">
                <button onClick={toggleSelectAll} className="flex items-center gap-2 text-sm text-gray-300 hover:text-white transition-colors">
                  {selectedEvents.size === filteredEvents.length ? 'Deselect All' : 'Select All'}
                </button>
                <span className="text-sm text-gray-400">{selectedEvents.size} selected</span>
              </div>
              <button
                onClick={() => setShowDeleteConfirm(true)}
                className="flex items-center gap-2 bg-red-600 text-white px-4 py-2 rounded-lg font-semibold hover:bg-red-700 transition-colors text-sm"
              >
                <Trash2 className="w-4 h-4" />
                Delete Selected
              </button>
            </div>
          )}

          {isLoading ? (
            <EventCardSkeletonGrid />
          ) : events.length === 0 ? (
            <div className="glass-card p-12 text-center rounded-2xl">
              <p className="text-xl text-gray-300 mb-2">No events yet</p>
              <p className="text-gray-500">Create your first event to get started</p>
            </div>
          ) : filteredEvents.length === 0 ? (
            <div className="glass-card p-12 text-center rounded-2xl">
              <p className="text-xl text-gray-300 mb-2">No events match your search</p>
              <p className="text-gray-500">Try a different search term</p>
            </div>
          ) : (
            <>
              {search && (
                <p className="text-sm text-gray-500 mb-4">Showing {filteredEvents.length} of {events.length} events</p>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredEvents.map((event) => (
                  <div
                    key={event.event_id}
                    className="glass-card rounded-2xl hover:bg-white/10 transition-colors group overflow-hidden flex"
                  >
                    {/* Checkbox column — not clickable for navigation */}
                    <div
                      className={`flex items-start pt-6 pl-4 pr-1 cursor-pointer transition-all ${
                        selectedEvents.size > 0 ? 'w-10' : 'w-0 opacity-0 group-hover:w-10 group-hover:opacity-100'
                      }`}
                      onClick={() => toggleSelect(event.event_id)}
                    >
                      <div
                        className={`w-6 h-6 rounded border-2 flex items-center justify-center flex-shrink-0 transition-all ${selectedEvents.has(event.event_id)
                            ? 'bg-blue-600 border-blue-600'
                            : 'border-white/20 hover:border-white/40'
                          }`}
                      >
                        {selectedEvents.has(event.event_id) && <Check className="w-4 h-4 text-white" />}
                      </div>
                    </div>

                    {/* Card content — clickable for navigation */}
                    <div
                      className="flex-1 p-6 cursor-pointer"
                      onClick={() => router.push(`/admin/events/${event.event_id}`)}
                    >
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
            </>
          )}
        </div>

        <ConfirmModal
          open={showDeleteConfirm}
          title="Delete Events"
          message={`Are you sure you want to delete ${selectedEvents.size} event${selectedEvents.size !== 1 ? 's' : ''}? This will permanently remove all photos and data.`}
          confirmLabel="Delete Events"
          variant="danger"
          loading={isDeleting}
          onConfirm={handleBulkDelete}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      </AdminLayout>
    </ProtectedRoute>
  )
}
