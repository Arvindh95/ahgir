import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, BarChart3, CheckCircle2, Gauge, Layers, Loader2, Search, ShieldAlert, Sparkles } from 'lucide-react'
import { eventService, EventAccuracy as EventAccuracyData } from '@/lib/events'

interface EventAccuracyProps {
  eventId: string
}

type Tone = 'neutral' | 'green' | 'blue' | 'orange' | 'red'

function StatCard({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: string | number
  tone?: Tone
}) {
  const tones: Record<Tone, string> = {
    neutral: 'bg-white/5 border-white/10 text-white',
    green: 'bg-green-500/10 border-green-500/20 text-green-300',
    blue: 'bg-blue-500/10 border-blue-500/20 text-blue-300',
    orange: 'bg-orange-500/10 border-orange-500/20 text-orange-300',
    red: 'bg-red-500/10 border-red-500/20 text-red-300',
  }
  return (
    <div className={`p-4 rounded-xl border ${tones[tone]}`}>
      <div className="text-2xl font-bold mb-1">{value}</div>
      <div className="text-xs uppercase tracking-wider opacity-70">{label}</div>
    </div>
  )
}

// Orange when the count is a non-zero signal worth an admin's attention.
const warnIf = (count: number, tone: Tone = 'orange'): Tone => (count > 0 ? tone : 'neutral')

export default function EventAccuracy({ eventId }: EventAccuracyProps) {
  const [data, setData] = useState<EventAccuracyData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadAccuracy = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      setData(await eventService.getAccuracy(eventId))
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load accuracy telemetry')
    } finally {
      setLoading(false)
    }
  }, [eventId])

  useEffect(() => {
    loadAccuracy()
  }, [loadAccuracy])

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
        {error || 'No accuracy telemetry available'}
      </div>
    )
  }

  const { scan_summary, match_quality, indexing_health } = data
  const maxBucketCount = Math.max(
    ...data.score_buckets.map(bucket => bucket.passed + bucket.filtered),
    1,
  )
  const recommendationIcon = {
    success: CheckCircle2,
    info: Sparkles,
    warning: AlertTriangle,
  }

  return (
    <div className="glass-card p-6 rounded-2xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <Gauge className="w-5 h-5" /> Face Accuracy
        </h2>
        <button
          onClick={loadAccuracy}
          className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-sm font-medium transition-colors"
        >
          Refresh
        </button>
      </div>

      <h3 className="text-sm font-semibold text-gray-300 mb-3">Scans</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Scans" value={scan_summary.total_scans} tone="blue" />
        <StatCard label="Unique Guests" value={scan_summary.unique_guests} />
        <StatCard label="Matched" value={scan_summary.matched_scans} tone="green" />
        <StatCard label="Zero Match" value={scan_summary.zero_match_scans} tone={warnIf(scan_summary.zero_match_scans)} />
        <StatCard label="No Face" value={scan_summary.no_face_scans} tone={warnIf(scan_summary.no_face_scans)} />
        <StatCard label="Upstream Errors" value={scan_summary.upstream_error_scans} tone={warnIf(scan_summary.upstream_error_scans, 'red')} />
        <StatCard label="Uncategorized" value={scan_summary.uncategorized_scans} />
        <StatCard label="Avg Matches" value={scan_summary.avg_returned_matches} />
      </div>

      <h3 className="text-sm font-semibold text-gray-300 mb-3">Match Candidates</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Candidates" value={match_quality.candidate_count} />
        <StatCard label="Telemetry Scans" value={match_quality.telemetry_scans} />
        <StatCard label="Passed" value={match_quality.passed_candidates} tone="green" />
        <StatCard label="Filtered" value={match_quality.filtered_candidates} />
        <StatCard label="Near Miss" value={match_quality.near_miss_candidates} tone={warnIf(match_quality.near_miss_candidates)} />
        <StatCard label="Rescued" value={match_quality.rescued_candidates} tone="blue" />
        <StatCard label="Tiny Faces" value={match_quality.tiny_filtered_candidates} tone={warnIf(match_quality.tiny_filtered_candidates)} />
        <StatCard label="Blurry" value={match_quality.blurry_filtered_candidates} tone={warnIf(match_quality.blurry_filtered_candidates)} />
      </div>

      <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
        <Layers className="w-4 h-4" /> Indexing Health
        <span className="text-xs font-normal text-gray-500">
          {indexing_health.indexing_percentage}% indexed
        </span>
      </h3>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
        <StatCard label="Total Photos" value={indexing_health.total_photos} />
        <StatCard label="Indexed" value={indexing_health.indexed} tone="green" />
        <StatCard label="Pending" value={indexing_health.pending} tone={warnIf(indexing_health.pending)} />
        <StatCard label="No Faces" value={indexing_health.no_faces} tone={warnIf(indexing_health.no_faces)} />
        <StatCard label="Failed" value={indexing_health.failed} tone={warnIf(indexing_health.failed, 'red')} />
        <StatCard label="Total Faces" value={indexing_health.total_faces} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-white/5 border border-white/10 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4" /> Score Buckets
          </h3>
          {data.score_buckets.length === 0 ? (
            <p className="text-sm text-gray-500">No scan candidate telemetry yet.</p>
          ) : (
            <div className="space-y-3">
              {data.score_buckets.map(bucket => {
                const total = bucket.passed + bucket.filtered
                const passedWidth = total > 0 ? (bucket.passed / total) * 100 : 0
                const filteredWidth = total > 0 ? (bucket.filtered / total) * 100 : 0
                const totalWidth = (total / maxBucketCount) * 100
                return (
                  <div key={bucket.bucket}>
                    <div className="flex justify-between text-xs text-gray-400 mb-1">
                      <span>{bucket.bucket}</span>
                      <span>{bucket.passed} passed / {bucket.filtered} filtered</span>
                    </div>
                    <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                      <div
                        className="h-full flex"
                        style={{ width: `${totalWidth}%` }}
                      >
                        <div className="h-full bg-green-500" style={{ width: `${passedWidth}%` }} />
                        <div className="h-full bg-orange-500" style={{ width: `${filteredWidth}%` }} />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <div className="bg-white/5 border border-white/10 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
            <ShieldAlert className="w-4 h-4" /> Recommendations
          </h3>
          <div className="space-y-3">
            {data.recommendations.map((item, index) => {
              const Icon = recommendationIcon[item.level]
              return (
                <div key={`${item.title}-${index}`} className="flex gap-3 p-3 rounded-lg bg-black/20">
                  <Icon className={`w-5 h-5 mt-0.5 ${
                    item.level === 'warning' ? 'text-orange-400' :
                    item.level === 'info' ? 'text-blue-400' : 'text-green-400'
                  }`} />
                  <div>
                    <div className="font-semibold text-sm">{item.title}</div>
                    <div className="text-sm text-gray-400 mt-1">{item.detail}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      <div className="bg-white/5 border border-white/10 rounded-xl p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Search className="w-4 h-4" /> Problem Scans
        </h3>
        {data.problem_scans.length === 0 ? (
          <p className="text-sm text-gray-500">No zero-match scans with strong near-miss evidence yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-gray-500 border-b border-white/10">
                <tr>
                  <th className="text-left py-2 font-medium">Scan ID</th>
                  <th className="text-right py-2 font-medium">Candidates</th>
                  <th className="text-right py-2 font-medium">Near Misses</th>
                  <th className="text-right py-2 font-medium">Max Raw</th>
                  <th className="text-right py-2 font-medium">Max Scored</th>
                </tr>
              </thead>
              <tbody>
                {data.problem_scans.map(scan => (
                  <tr key={scan.scan_id} className="border-b border-white/5">
                    <td className="py-2 font-mono text-xs text-gray-400">{scan.scan_id}</td>
                    <td className="py-2 text-right">{scan.candidate_count}</td>
                    <td className="py-2 text-right">{scan.near_miss_count}</td>
                    <td className="py-2 text-right">{scan.max_raw_similarity.toFixed(4)}</td>
                    <td className="py-2 text-right">{scan.max_scored_similarity.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
