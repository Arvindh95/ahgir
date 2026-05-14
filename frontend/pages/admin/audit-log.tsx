import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import api from '@/lib/api'
import { Search, Filter, ChevronLeft, ChevronRight, Loader2, ShieldCheck, User as UserIcon, Calendar, Clock, ChevronDown, ChevronUp } from 'lucide-react'

interface AuditEntry {
  id: string
  timestamp: string
  actor_type: 'admin' | 'guest' | 'system'
  actor_id: string | null
  actor_email: string | null
  action: string
  event_id: string | null
  event_name: string | null
  metadata: Record<string, any>
}

interface AuditResponse {
  entries: AuditEntry[]
  total: number
  limit: number
  offset: number
}

const PAGE_SIZE = 50

// Colour map for the action badge so the eye can scan the table by category.
function actionColor(action: string): string {
  if (action.startsWith('admin_')) return 'bg-purple-500/20 text-purple-300 border-purple-500/30'
  if (action === 'scan') return 'bg-blue-500/20 text-blue-300 border-blue-500/30'
  if (action === 'access' || action === 'gallery_view' || action === 'photo_view') return 'bg-gray-500/20 text-gray-300 border-gray-500/30'
  if (action === 'upload' || action.includes('create')) return 'bg-green-500/20 text-green-300 border-green-500/30'
  if (action === 'delete' || action.includes('delete')) return 'bg-red-500/20 text-red-300 border-red-500/30'
  if (action.includes('share') || action.includes('download')) return 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30'
  return 'bg-gray-500/20 text-gray-400 border-gray-500/30'
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

function targetSummary(entry: AuditEntry): string {
  const md = entry.metadata || {}
  if (entry.event_name) return entry.event_name
  if (md.target_email) return md.target_email
  if (md.owner_email) return md.owner_email
  if (md.target_event_name) return md.target_event_name
  if (md.target_user_id) return `user ${String(md.target_user_id).slice(0, 8)}…`
  if (md.target_event_id) return `event ${String(md.target_event_id).slice(0, 8)}…`
  if (entry.event_id) return `event ${entry.event_id.slice(0, 8)}…`
  return '—'
}

export default function AuditLogPage() {
  const router = useRouter()
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // Filters
  const [actorType, setActorType] = useState<string>('')
  const [actionFilter, setActionFilter] = useState<string>('')
  const [searchQ, setSearchQ] = useState<string>('')

  const load = async (newOffset: number) => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      params.set('limit', String(PAGE_SIZE))
      params.set('offset', String(newOffset))
      if (actorType) params.set('actor_type', actorType)
      if (actionFilter) params.set('action', actionFilter)
      if (searchQ) params.set('q', searchQ)
      const resp = await api.get<AuditResponse>(`/admin/audit-log?${params.toString()}`)
      setEntries(resp.data.entries)
      setTotal(resp.data.total)
      setOffset(resp.data.offset)
    } catch (err: any) {
      setError(err.response?.data?.error?.message || err.response?.data?.detail || 'Failed to load audit log')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const applyFilters = () => {
    setExpandedId(null)
    load(0)
  }

  const resetFilters = () => {
    setActorType('')
    setActionFilter('')
    setSearchQ('')
    setExpandedId(null)
    // Use timeout to let state flush so the load reads the cleared values.
    setTimeout(() => load(0), 0)
  }

  const goPrev = () => {
    if (offset === 0) return
    load(Math.max(0, offset - PAGE_SIZE))
  }
  const goNext = () => {
    if (offset + PAGE_SIZE >= total) return
    load(offset + PAGE_SIZE)
  }

  const pageStart = total === 0 ? 0 : offset + 1
  const pageEnd = Math.min(offset + PAGE_SIZE, total)

  return (
    <ProtectedRoute>
      <Head><title>Audit Log - PicUr</title></Head>
      <AdminLayout>
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between mb-8">
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <ShieldCheck className="w-8 h-8 text-purple-400" />
              Audit Log
            </h1>
            <button
              onClick={() => router.push('/admin/superadmin')}
              className="text-sm text-gray-400 hover:text-white transition-colors"
            >
              ← Back to Superadmin
            </button>
          </div>

          {/* Filters */}
          <div className="glass-card p-5 rounded-2xl mb-6">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-300 mb-4">
              <Filter className="w-4 h-4" /> Filters
            </div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <select
                value={actorType}
                onChange={(e) => setActorType(e.target.value)}
                className="glass-input px-3 py-2 rounded-xl text-sm [&>option]:bg-gray-900 [&>option]:text-white"
              >
                <option value="">All actor types</option>
                <option value="admin">Admin</option>
                <option value="guest">Guest</option>
                <option value="system">System (automated)</option>
              </select>
              <input
                type="text"
                placeholder="Action contains… (e.g. admin_user)"
                value={actionFilter}
                onChange={(e) => setActionFilter(e.target.value)}
                className="glass-input px-3 py-2 rounded-xl text-sm"
              />
              <div className="relative md:col-span-2">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                <input
                  type="text"
                  placeholder="Search actor email / metadata…"
                  value={searchQ}
                  onChange={(e) => setSearchQ(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && applyFilters()}
                  className="glass-input w-full pl-10 pr-4 py-2 rounded-xl text-sm"
                />
              </div>
            </div>
            <div className="flex items-center gap-2 mt-4">
              <button
                onClick={applyFilters}
                className="px-4 py-2 rounded-xl text-sm font-semibold bg-blue-600 text-white hover:bg-blue-700 transition-colors"
              >
                Apply
              </button>
              <button
                onClick={resetFilters}
                className="px-4 py-2 rounded-xl text-sm font-medium text-gray-300 hover:text-white hover:bg-white/5 transition-colors"
              >
                Reset
              </button>
              <span className="ml-auto text-xs text-gray-500">
                {total > 0 ? `Showing ${pageStart}–${pageEnd} of ${total}` : (loading ? 'Loading…' : 'No entries')}
              </span>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="glass-card p-4 rounded-xl mb-6 text-sm text-red-300 border border-red-500/30">
              {error}
            </div>
          )}

          {/* Table */}
          <div className="glass-card p-5 rounded-2xl">
            {loading && entries.length === 0 ? (
              <div className="flex items-center justify-center py-12 text-gray-400 gap-2">
                <Loader2 className="w-5 h-5 animate-spin" /> Loading audit log…
              </div>
            ) : entries.length === 0 ? (
              <div className="text-center py-12 text-gray-500 text-sm">No audit entries match your filters.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-gray-400 text-xs uppercase tracking-wider">
                      <th className="pb-3 pl-2 font-medium w-44"><Clock className="w-3.5 h-3.5 inline mr-1" />When</th>
                      <th className="pb-3 font-medium w-32">Actor</th>
                      <th className="pb-3 font-medium">Email</th>
                      <th className="pb-3 font-medium">Action</th>
                      <th className="pb-3 font-medium">Target</th>
                      <th className="pb-3 font-medium w-10"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {entries.map((e) => {
                      const isOpen = expandedId === e.id
                      return (
                        <>
                          <tr key={e.id} className="hover:bg-white/5 transition-colors cursor-pointer" onClick={() => setExpandedId(isOpen ? null : e.id)}>
                            <td className="py-3 pl-2 align-top">
                              <div className="text-gray-300">{relativeTime(e.timestamp)}</div>
                              <div className="text-[10px] text-gray-500">{formatTimestamp(e.timestamp)}</div>
                            </td>
                            <td className="py-3 align-top">
                              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                                e.actor_type === 'admin'
                                  ? 'bg-purple-500/15 text-purple-300'
                                  : e.actor_type === 'system'
                                    ? 'bg-amber-500/15 text-amber-300'
                                    : 'bg-gray-500/15 text-gray-300'
                              }`}>
                                {e.actor_type === 'admin'
                                  ? <ShieldCheck className="w-3 h-3" />
                                  : e.actor_type === 'system'
                                    ? <Clock className="w-3 h-3" />
                                    : <UserIcon className="w-3 h-3" />}
                                {e.actor_type}
                              </span>
                            </td>
                            <td className="py-3 text-gray-300 align-top text-xs">{e.actor_email || '—'}</td>
                            <td className="py-3 align-top">
                              <span className={`px-2 py-0.5 rounded text-xs font-mono border ${actionColor(e.action)}`}>{e.action}</span>
                            </td>
                            <td className="py-3 text-gray-400 align-top text-xs">{targetSummary(e)}</td>
                            <td className="py-3 align-top text-gray-500">
                              {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                            </td>
                          </tr>
                          {isOpen && (
                            <tr className="bg-black/40">
                              <td colSpan={6} className="px-4 py-3 text-xs">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                  <div>
                                    <div className="text-gray-500 mb-1 text-[10px] uppercase tracking-wider">IDs</div>
                                    <div className="font-mono text-gray-300 space-y-1">
                                      <div>entry: <span className="text-gray-400">{e.id}</span></div>
                                      {e.actor_id && <div>actor: <span className="text-gray-400">{e.actor_id}</span></div>}
                                      {e.event_id && <div>event: <span className="text-gray-400">{e.event_id}</span></div>}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-gray-500 mb-1 text-[10px] uppercase tracking-wider">Metadata</div>
                                    <pre className="font-mono text-[11px] text-gray-300 bg-black/50 p-2 rounded-lg overflow-auto max-h-48">{JSON.stringify(e.metadata, null, 2)}</pre>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pagination */}
            {total > PAGE_SIZE && (
              <div className="flex items-center justify-end gap-2 mt-4 pt-4 border-t border-white/5">
                <button
                  onClick={goPrev}
                  disabled={offset === 0 || loading}
                  className="p-2 rounded-lg bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="text-xs text-gray-500">{pageStart}–{pageEnd} of {total}</span>
                <button
                  onClick={goNext}
                  disabled={offset + PAGE_SIZE >= total || loading}
                  className="p-2 rounded-lg bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        </div>
      </AdminLayout>
    </ProtectedRoute>
  )
}
