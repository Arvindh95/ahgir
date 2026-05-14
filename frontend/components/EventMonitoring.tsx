import { useEffect, useState } from 'react'
import { eventService, EventDetails } from '@/lib/events'
import { RefreshCcw, Activity, Loader2 } from 'lucide-react'

interface EventMonitoringProps {
  eventId: string
}

export default function EventMonitoring({ eventId }: EventMonitoringProps) {
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [isLoadingEvent, setIsLoadingEvent] = useState(true)
  const [error, setError] = useState('')
  const [isReindexing, setIsReindexing] = useState(false)

  useEffect(() => {
    loadEvent()
  }, [eventId])

  // Auto-poll when there are pending photos
  useEffect(() => {
    if (!event || event.status.pending === 0) return

    const interval = setInterval(() => {
      loadEvent()
    }, 5000)

    return () => clearInterval(interval)
  }, [event?.status.pending, eventId])

  const loadEvent = async () => {
    try {
      setIsLoadingEvent(true)
      const data = await eventService.getEvent(eventId)
      setEvent(data)
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to load event')
    } finally {
      setIsLoadingEvent(false)
    }
  }

  const handleReindex = async () => {
    if (!confirm('Reindex all photos? This will reset the status of all photos.')) {
      return
    }

    try {
      setIsReindexing(true)
      await eventService.reindexEvent(eventId)
      alert('Reindexing started')
      loadEvent()
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to start reindexing')
    } finally {
      setIsReindexing(false)
    }
  }

  if (isLoadingEvent) {
    return (
       <div className="flex justify-center p-8">
          <Loader2 className="w-6 h-6 animate-spin text-white" />
       </div>
    )
  }

  if (error || !event) {
    return (
      <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl">
        {error || 'Failed to load monitoring data'}
      </div>
    )
  }

  return (
    <div>
      {/* Indexing Status Section */}
      <div className="glass-card p-6 rounded-2xl mb-8">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold flex items-center gap-2">
             <Activity className="w-5 h-5" /> Indexing Status
          </h2>
          <button
            onClick={handleReindex}
            disabled={isReindexing}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
               isReindexing 
               ? 'bg-white/5 text-gray-500 cursor-not-allowed' 
               : 'bg-green-600 text-white hover:bg-green-700'
            }`}
          >
            {isReindexing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCcw className="w-4 h-4" />}
            {isReindexing ? 'Reindexing...' : 'Reindex All'}
          </button>
        </div>

        {/* Progress Bar */}
        <div className="mb-8">
          <div className="flex justify-between mb-2 text-sm">
            <span className="font-medium text-gray-300">Progress</span>
            <span className="font-bold">{event.status.indexing_percentage.toFixed(1)}%</span>
          </div>
          <div className="w-full h-3 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-500 ease-out"
              style={{ width: `${event.status.indexing_percentage}%` }}
            />
          </div>
          {event.status.pending > 0 && (
            <div className="flex items-center justify-between mt-2">
              <span className="text-sm text-orange-400 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-orange-400 animate-pulse" />
                Processing {event.status.pending} {event.status.pending === 1 ? 'photo' : 'photos'}...
              </span>
              <span className="text-xs text-gray-500">
                Auto-refreshing every 5s
              </span>
            </div>
          )}
        </div>

        {/* Photo Counts Grid */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <div className="p-4 bg-white/5 rounded-xl text-center border border-white/5">
            <div className="text-2xl font-bold mb-1">{event.status.total_photos}</div>
            <div className="text-xs text-gray-400 uppercase tracking-wider">Total Photos</div>
          </div>
          <div className="p-4 bg-green-500/10 rounded-xl text-center border border-green-500/20">
            <div className="text-2xl font-bold mb-1 text-green-400">{event.status.indexed}</div>
            <div className="text-xs text-green-500/70 uppercase tracking-wider">Indexed</div>
          </div>
          <div className="p-4 bg-orange-500/10 rounded-xl text-center border border-orange-500/20">
            <div className="text-2xl font-bold mb-1 text-orange-400">{event.status.pending}</div>
            <div className="text-xs text-orange-500/70 uppercase tracking-wider">Pending</div>
          </div>
          <div className="p-4 bg-white/5 rounded-xl text-center border border-white/5">
            <div className="text-2xl font-bold mb-1 text-gray-300">{event.status.no_faces}</div>
            <div className="text-xs text-gray-500 uppercase tracking-wider">No Faces</div>
          </div>
          <div className="p-4 bg-red-500/10 rounded-xl text-center border border-red-500/20">
            <div className="text-2xl font-bold mb-1 text-red-400">{event.status.failed}</div>
            <div className="text-xs text-red-500/70 uppercase tracking-wider">Failed</div>
          </div>
          <div className="p-4 bg-blue-500/10 rounded-xl text-center border border-blue-500/20">
            <div className="text-2xl font-bold mb-1 text-blue-400">{event.status.total_faces}</div>
            <div className="text-xs text-blue-500/70 uppercase tracking-wider">Total Faces</div>
          </div>
        </div>
      </div>

    </div>
  )
}
