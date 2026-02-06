import { useEffect, useState } from 'react'
import api from '@/lib/api'
import { ScanFace, Users, Download, Eye, TrendingUp } from 'lucide-react'

interface GlobalAnalyticsData {
  total_scans: number
  unique_guests: number
  total_downloads: number
  total_gallery_views: number
  top_events: { name: string; scans: number; guests: number }[]
  scans_by_day: { date: string; count: number }[]
}

export default function GlobalAnalytics() {
  const [data, setData] = useState<GlobalAnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/admin/global-analytics')
      .then(res => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="glass-card p-6 rounded-2xl mb-8 animate-pulse">
        <div className="h-6 w-48 bg-white/10 rounded mb-6" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <div key={i} className="h-20 bg-white/5 rounded-xl" />)}
        </div>
      </div>
    )
  }

  if (!data) return null

  const stats = [
    { label: 'Total Scans', value: data.total_scans, icon: ScanFace, color: 'text-blue-400' },
    { label: 'Unique Guests', value: data.unique_guests, icon: Users, color: 'text-green-400' },
    { label: 'Downloads', value: data.total_downloads, icon: Download, color: 'text-purple-400' },
    { label: 'Gallery Views', value: data.total_gallery_views, icon: Eye, color: 'text-yellow-400' },
  ]

  const maxScans = Math.max(...(data.scans_by_day.map(d => d.count)), 1)
  const maxTopScans = Math.max(...(data.top_events.map(e => e.scans)), 1)

  return (
    <div className="glass-card p-6 rounded-2xl mb-8">
      <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
        <TrendingUp className="w-5 h-5 text-blue-400" />
        Platform Analytics
      </h2>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {stats.map(stat => (
          <div key={stat.label} className="bg-white/5 rounded-xl p-4 text-center">
            <stat.icon className={`w-5 h-5 mx-auto mb-2 ${stat.color}`} />
            <div className="text-2xl font-bold">{stat.value.toLocaleString()}</div>
            <div className="text-xs text-gray-400 mt-1">{stat.label}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Scans by day chart */}
        {data.scans_by_day.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-gray-400 mb-3">Scans (Last 30 Days)</h3>
            <div className="flex items-end gap-1 h-24">
              {data.scans_by_day.map((day, i) => (
                <div
                  key={i}
                  className="flex-1 bg-blue-500/60 rounded-t hover:bg-blue-400/80 transition-colors"
                  style={{ height: `${(day.count / maxScans) * 100}%`, minHeight: day.count > 0 ? '4px' : '0' }}
                  title={`${new Date(day.date).toLocaleDateString()}: ${day.count} scans`}
                />
              ))}
            </div>
          </div>
        )}

        {/* Top events table */}
        {data.top_events.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-gray-400 mb-3">Top Events</h3>
            <div className="space-y-2">
              {data.top_events.map((event, i) => (
                <div key={i} className="flex items-center gap-3">
                  <span className="text-sm text-gray-400 w-4">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{event.name}</div>
                    <div className="w-full bg-white/5 rounded-full h-1.5 mt-1">
                      <div
                        className="bg-blue-500 h-1.5 rounded-full"
                        style={{ width: `${(event.scans / maxTopScans) * 100}%` }}
                      />
                    </div>
                  </div>
                  <span className="text-sm text-gray-400 whitespace-nowrap">{event.scans} scans</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
