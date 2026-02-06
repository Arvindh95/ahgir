import { useEffect, useState } from 'react'
import api from '@/lib/api'
import { BarChart3, Users, Download, Eye, Loader2, Activity } from 'lucide-react'

interface AnalyticsData {
  total_scans: number
  unique_guests: number
  total_downloads: number
  total_gallery_views: number
  scans_by_day: { date: string; count: number }[]
  peak_hours: { hour: number; count: number }[]
  recent_activity: {
    id: string
    action: string
    actor_type: string
    timestamp: string
    metadata: Record<string, any>
  }[]
}

interface EventAnalyticsProps {
  eventId: string
}

export default function EventAnalytics({ eventId }: EventAnalyticsProps) {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    loadAnalytics()
  }, [eventId])

  const loadAnalytics = async () => {
    try {
      setLoading(true)
      const response = await api.get(`/events/${eventId}/analytics`)
      setData(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load analytics')
    } finally {
      setLoading(false)
    }
  }

  const formatTimestamp = (ts: string) => {
    return new Date(ts).toLocaleString('en-US', {
      month: 'short', day: 'numeric', hour: 'numeric', minute: 'numeric'
    })
  }

  const formatDate = (ts: string) => {
    return new Date(ts).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric'
    })
  }

  const getActionColor = (action: string) => {
    const colors: Record<string, string> = {
      scan: 'bg-blue-500/20 text-blue-400',
      access: 'bg-cyan-500/20 text-cyan-400',
      upload: 'bg-green-500/20 text-green-400',
      bulk_download: 'bg-purple-500/20 text-purple-400',
      gallery_view: 'bg-yellow-500/20 text-yellow-400',
      reindex: 'bg-orange-500/20 text-orange-400',
      delete: 'bg-red-500/20 text-red-400',
    }
    return colors[action] || 'bg-gray-500/20 text-gray-400'
  }

  if (loading) {
    return (
      <div className="glass-card p-6 rounded-2xl flex justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-white" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="glass-card p-6 rounded-2xl text-center text-gray-500">
        {error || 'No analytics data available'}
      </div>
    )
  }

  const maxScanCount = Math.max(...data.scans_by_day.map(d => d.count), 1)
  const maxHourCount = Math.max(...data.peak_hours.map(h => h.count), 1)

  return (
    <div className="glass-card p-6 rounded-2xl">
      <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
        <BarChart3 className="w-5 h-5" /> Analytics
      </h2>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div className="p-4 bg-blue-500/10 rounded-xl text-center border border-blue-500/20">
          <div className="text-2xl font-bold text-blue-400 mb-1">{data.total_scans}</div>
          <div className="text-xs text-blue-500/70 uppercase tracking-wider">Face Scans</div>
        </div>
        <div className="p-4 bg-green-500/10 rounded-xl text-center border border-green-500/20">
          <div className="text-2xl font-bold text-green-400 mb-1">{data.unique_guests}</div>
          <div className="text-xs text-green-500/70 uppercase tracking-wider">Unique Guests</div>
        </div>
        <div className="p-4 bg-purple-500/10 rounded-xl text-center border border-purple-500/20">
          <div className="text-2xl font-bold text-purple-400 mb-1">{data.total_downloads}</div>
          <div className="text-xs text-purple-500/70 uppercase tracking-wider">Downloads</div>
        </div>
        <div className="p-4 bg-yellow-500/10 rounded-xl text-center border border-yellow-500/20">
          <div className="text-2xl font-bold text-yellow-400 mb-1">{data.total_gallery_views}</div>
          <div className="text-xs text-yellow-500/70 uppercase tracking-wider">Gallery Views</div>
        </div>
      </div>

      {/* Scans by Day Chart */}
      {data.scans_by_day.length > 0 && (
        <div className="mb-8">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Scans by Day</h3>
          <div className="flex items-end gap-1 h-32">
            {data.scans_by_day.map((day, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-1">
                <div
                  className="w-full bg-blue-500/60 rounded-t transition-all hover:bg-blue-500/80"
                  style={{ height: `${(day.count / maxScanCount) * 100}%`, minHeight: day.count > 0 ? '4px' : '0' }}
                  title={`${formatDate(day.date)}: ${day.count} scans`}
                />
                <span className="text-[10px] text-gray-500 truncate w-full text-center">
                  {formatDate(day.date)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Peak Hours */}
      {data.peak_hours.length > 0 && (
        <div className="mb-8">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Activity by Hour</h3>
          <div className="flex gap-0.5">
            {Array.from({ length: 24 }, (_, hour) => {
              const match = data.peak_hours.find(h => h.hour === hour)
              const count = match?.count || 0
              const intensity = count > 0 ? Math.max(0.2, count / maxHourCount) : 0
              return (
                <div
                  key={hour}
                  className="flex-1 h-8 rounded-sm transition-all"
                  style={{ backgroundColor: count > 0 ? `rgba(59, 130, 246, ${intensity})` : 'rgba(255,255,255,0.05)' }}
                  title={`${hour}:00 - ${count} actions`}
                />
              )
            })}
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-[10px] text-gray-500">12am</span>
            <span className="text-[10px] text-gray-500">6am</span>
            <span className="text-[10px] text-gray-500">12pm</span>
            <span className="text-[10px] text-gray-500">6pm</span>
            <span className="text-[10px] text-gray-500">12am</span>
          </div>
        </div>
      )}

      {/* Recent Activity */}
      {data.recent_activity.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
            <Activity className="w-4 h-4" /> Recent Activity
          </h3>
          <div className="space-y-2">
            {data.recent_activity.map((log) => (
              <div key={log.id} className="flex items-center gap-3 p-2 rounded-lg bg-white/5 text-sm">
                <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider ${getActionColor(log.action)}`}>
                  {log.action}
                </span>
                <span className={`px-1.5 py-0.5 rounded text-xs ${log.actor_type === 'admin' ? 'bg-purple-500/20 text-purple-300' : 'bg-gray-500/20 text-gray-300'}`}>
                  {log.actor_type}
                </span>
                <span className="text-gray-500 text-xs ml-auto">{formatTimestamp(log.timestamp)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
