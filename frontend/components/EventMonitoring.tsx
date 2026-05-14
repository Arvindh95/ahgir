import { useEffect, useState } from 'react'
import { eventService, EventDetails } from '@/lib/events'
import { auditService, AuditLog } from '@/lib/audit'
import { RefreshCcw, Activity, Upload, Trash2, ScanFace, Search, Loader2 } from 'lucide-react'

interface EventMonitoringProps {
  eventId: string
}

export default function EventMonitoring({ eventId }: EventMonitoringProps) {
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([])
  const [isLoadingEvent, setIsLoadingEvent] = useState(true)
  const [isLoadingLogs, setIsLoadingLogs] = useState(true)
  const [error, setError] = useState('')
  const [actionFilter, setActionFilter] = useState<string>('admin_only')
  const [isReindexing, setIsReindexing] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date())
  const logsPerPage = 20

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

  useEffect(() => {
    loadAuditLogs()
  }, [eventId, actionFilter, page])

  const loadEvent = async () => {
    try {
      setIsLoadingEvent(true)
      const data = await eventService.getEvent(eventId)
      setEvent(data)
      setLastUpdated(new Date())
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to load event')
    } finally {
      setIsLoadingEvent(false)
    }
  }

  const loadAuditLogs = async () => {
    try {
      setIsLoadingLogs(true)
      // Translate the UI filter into separate backend params. Previously we
      // pulled only one page and applied admin_only/guest_only locally,
      // which meant admin actions on page 2+ vanished and the total stayed
      // at the unfiltered page count — both misleading to ops.
      let action: string | undefined = undefined
      let actorType: 'admin' | 'guest' | undefined = undefined
      if (actionFilter === 'admin_only') {
        actorType = 'admin'
      } else if (actionFilter === 'guest_only') {
        actorType = 'guest'
      } else if (actionFilter) {
        action = actionFilter
      }

      const data = await auditService.getAuditLogs(eventId, page, logsPerPage, action, actorType)

      setAuditLogs(data.logs)
      setTotal(data.total)
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to load audit logs')
    } finally {
      setIsLoadingLogs(false)
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

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString('en-US', {
       month: 'short',
       day: 'numeric',
       hour: 'numeric',
       minute: 'numeric',
       second: 'numeric'
    })
  }

  const getActionColorDetails = (action: string) => {
    switch (action) {
      case 'access':
        return 'bg-cyan-500/20 text-cyan-400'
      case 'scan':
        return 'bg-blue-500/20 text-blue-400'
      case 'upload':
        return 'bg-green-500/20 text-green-400'
      case 'reindex':
        return 'bg-orange-500/20 text-orange-400'
      case 'delete':
        return 'bg-red-500/20 text-red-400'
      default:
        return 'bg-gray-500/20 text-gray-400'
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

      {/* Audit Logs Section */}
      <div className="glass-card p-6 rounded-2xl">
        <div className="flex flex-col sm:flex-row justify-between items-center gap-4 mb-6">
          <h2 className="text-xl font-bold flex items-center gap-2">
             <Search className="w-5 h-5" /> Audit Logs
          </h2>
          <div className="flex items-center gap-2 bg-white/5 px-3 py-1.5 rounded-lg border border-white/10 w-full sm:w-auto">
            <label htmlFor="actionFilter" className="text-sm text-gray-400">Filter:</label>
            <select
              id="actionFilter"
              value={actionFilter}
              onChange={(e) => {
                setActionFilter(e.target.value)
                setPage(1)
              }}
              className="bg-transparent border-none text-sm text-white focus:ring-0 cursor-pointer w-full"
            >
              <option value="admin_only" className="bg-black">Admin Only</option>
              <option value="" className="bg-black">All Activity</option>
              <option value="guest_only" className="bg-black">Guest Only</option>
              <option value="access" className="bg-black">Access</option>
              <option value="scan" className="bg-black">Scan</option>
              <option value="upload" className="bg-black">Upload</option>
              <option value="reindex" className="bg-black">Reindex</option>
              <option value="delete" className="bg-black">Delete</option>
            </select>
          </div>
        </div>

        {isLoadingLogs ? (
          <div className="flex justify-center p-8">
             <Loader2 className="w-6 h-6 animate-spin text-white" />
          </div>
        ) : auditLogs.length === 0 ? (
          <div className="text-center text-gray-500 p-8">
            No audit logs found
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-gray-400">
                    <th className="pb-3 pl-2 font-medium">Timestamp</th>
                    <th className="pb-3 font-medium">Actor</th>
                    <th className="pb-3 font-medium">Action</th>
                    <th className="pb-3 font-medium">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {auditLogs.map((log) => (
                    <tr key={log.log_id} className="hover:bg-white/5 transition-colors">
                      <td className="py-3 pl-2 text-gray-300 whitespace-nowrap">
                        {formatTimestamp(log.timestamp)}
                      </td>
                      <td className="py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                           log.actor_type === 'admin' ? 'bg-purple-500/20 text-purple-300' : 'bg-gray-500/20 text-gray-300'
                        }`}>
                          {log.actor_type}
                        </span>
                      </td>
                      <td className="py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider ${getActionColorDetails(log.action)}`}>
                          {log.action}
                        </span>
                      </td>
                      <td className="py-3 text-gray-400 font-mono text-xs break-all pr-2">
                        {log.metadata && Object.keys(log.metadata).length > 0 ? (
                          <span>{JSON.stringify(log.metadata)}</span>
                        ) : (
                          <span className="opacity-50">-</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {total > logsPerPage && (
              <div className="flex justify-center items-center gap-2 mt-6 pt-4 border-t border-white/10">
                <button
                  onClick={() => setPage(page - 1)}
                  disabled={page === 1}
                  className="px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Previous
                </button>
                <span className="px-4 py-2 text-sm text-gray-400">
                  Page {page} of {Math.ceil(total / logsPerPage)}
                </span>
                <button
                  onClick={() => setPage(page + 1)}
                  disabled={page >= Math.ceil(total / logsPerPage)}
                  className="px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
