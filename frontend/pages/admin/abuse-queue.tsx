import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import AdminLayout from '@/components/AdminLayout'
import ProtectedRoute from '@/components/ProtectedRoute'
import { abuseService, AbuseReportRow } from '@/lib/abuse'
import { authService } from '@/lib/auth'
import { useToast } from '@/hooks/useToast'
import { Flag, ArrowRight, Loader2, Ban, ShieldOff } from 'lucide-react'

const STATUSES = ['pending', 'reviewing', 'dismissed', 'quarantined', 'removed'] as const
const CATEGORIES = ['csam', 'nudity', 'harassment', 'copyright', 'violence', 'other'] as const

const CATEGORY_COLOR: Record<string, string> = {
  csam: 'bg-red-600/30 text-red-300 border-red-500/40',
  nudity: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
  harassment: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
  copyright: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
  violence: 'bg-red-500/20 text-red-300 border-red-500/40',
  other: 'bg-gray-500/20 text-gray-300 border-gray-500/40',
}

const PAGE_SIZE = 25

function formatDate(iso: string | null | undefined) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

function truncate(s: string | null | undefined, n: number) {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}

export default function AbuseQueuePage() {
  const router = useRouter()
  const { toast } = useToast()
  const [items, setItems] = useState<AbuseReportRow[]>([])
  const [total, setTotal] = useState(0)
  const [statusFilter, setStatusFilter] = useState<string>('pending')
  const [categoryFilter, setCategoryFilter] = useState<string>('')
  const [sort, setSort] = useState<'newest' | 'oldest'>('newest')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [bulkLoading, setBulkLoading] = useState<string | null>(null)

  const refreshAfterAction = async () => {
    const data = await abuseService.list({
      status: statusFilter,
      category: categoryFilter || undefined,
      sort,
      limit: PAGE_SIZE,
      offset,
    })
    setItems(data.items)
    setTotal(data.total)
  }
  // Refresh button: re-fetch the current page. Previously this called
  // setOffset(0) which only triggered the load-effect when offset was
  // already non-zero — on page 1 it was a no-op. Resetting to page 1
  // AND issuing a fresh fetch covers both cases.
  const handleRefresh = async () => {
    if (offset !== 0) {
      setOffset(0)
      return
    }
    try {
      setLoading(true)
      await refreshAfterAction()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load reports')
    } finally {
      setLoading(false)
    }
  }

  const handleDismissBySource = async (row: AbuseReportRow) => {
    const source = row.reporter_ip ?? row.reporter_email ?? ''
    if (!source) return
    if (!window.confirm(`Dismiss every pending/reviewing report from ${source}?`)) return
    try {
      setBulkLoading(row.id)
      const n = await abuseService.dismissBySource(
        row.reporter_ip ? { reporter_ip: row.reporter_ip } : { reporter_email: row.reporter_email! }
      )
      toast(`Dismissed ${n} report${n === 1 ? '' : 's'}.`, 'success')
      await refreshAfterAction()
    } catch (err: any) {
      toast(err.response?.data?.detail || 'Failed to bulk-dismiss', 'error')
    } finally {
      setBulkLoading(null)
    }
  }

  const handleClearBan = async (row: AbuseReportRow) => {
    if (!row.reporter_ip) return
    if (!window.confirm(`Clear ban on ${row.reporter_ip}? They will be able to file reports again immediately.`)) return
    try {
      setBulkLoading(row.id)
      await abuseService.clearBan(row.reporter_ip)
      toast('Ban cleared.', 'success')
      await refreshAfterAction()
    } catch (err: any) {
      toast(err.response?.data?.detail || 'Failed to clear ban', 'error')
    } finally {
      setBulkLoading(null)
    }
  }

  useEffect(() => {
    authService.getMe().then((u) => {
      if (!u.is_superadmin) router.replace('/admin/events')
    }).catch(() => router.replace('/admin/login'))
  }, [router])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        setLoading(true)
        const data = await abuseService.list({
          status: statusFilter,
          category: categoryFilter || undefined,
          sort,
          limit: PAGE_SIZE,
          offset,
        })
        if (cancelled) return
        setItems(data.items)
        setTotal(data.total)
      } catch (err: any) {
        if (cancelled) return
        setError(err.response?.data?.detail || 'Failed to load reports')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [statusFilter, categoryFilter, sort, offset])

  const pageEnd = offset + items.length
  const hasNext = pageEnd < total
  const hasPrev = offset > 0

  return (
    <ProtectedRoute>
      <Head><title>Abuse Queue - PicUr</title></Head>
      <AdminLayout>
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between mb-6 flex-wrap gap-2">
            <h1 className="text-3xl font-bold flex items-center gap-2">
              <Flag className="w-7 h-7 text-orange-400" /> Abuse Review Queue
              {statusFilter === 'pending' && total > 0 && (
                <span className="ml-2 px-2 py-0.5 rounded-full text-sm font-bold bg-red-500/20 text-red-400">
                  {total} pending
                </span>
              )}
            </h1>
            <button
              onClick={handleRefresh}
              disabled={loading}
              className="px-3 py-1.5 text-sm bg-white/10 hover:bg-white/20 rounded-lg transition-colors disabled:opacity-50"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Refresh'}
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2 mb-4">
            <div className="flex flex-wrap gap-2">
              {STATUSES.map((s) => (
                <button
                  key={s}
                  onClick={() => { setStatusFilter(s); setOffset(0) }}
                  className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
                    statusFilter === s
                      ? 'bg-orange-500/30 text-orange-200 border border-orange-500/50'
                      : 'bg-white/5 text-gray-400 border border-white/10 hover:bg-white/10'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
            <select
              value={categoryFilter}
              onChange={(e) => { setCategoryFilter(e.target.value); setOffset(0) }}
              className="bg-white/5 border border-white/10 text-sm rounded-lg px-3 py-1.5"
            >
              <option value="">All categories</option>
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <select
              value={sort}
              onChange={(e) => { setSort(e.target.value as 'newest' | 'oldest'); setOffset(0) }}
              className="bg-white/5 border border-white/10 text-sm rounded-lg px-3 py-1.5"
            >
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
            </select>
          </div>

          {error && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 text-red-400 rounded-lg text-sm">
              {error}
            </div>
          )}

          {loading ? (
            <div className="text-center py-12">
              <Loader2 className="w-6 h-6 animate-spin mx-auto" />
            </div>
          ) : items.length === 0 ? (
            <div className="glass-card rounded-2xl p-12 text-center text-gray-400 text-sm">
              No reports matching these filters.
            </div>
          ) : (
            <div className="glass-card rounded-2xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-gray-400 text-left">
                      <th className="px-4 py-3 font-medium">Category</th>
                      <th className="px-4 py-3 font-medium">Event</th>
                      <th className="px-4 py-3 font-medium">Filename</th>
                      <th className="px-4 py-3 font-medium">Reporter</th>
                      <th className="px-4 py-3 font-medium">Description</th>
                      <th className="px-4 py-3 font-medium">Reported</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="px-4 py-3 font-medium"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {items.map((r) => (
                      <tr key={r.id} className="hover:bg-white/5 transition-colors">
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase border ${CATEGORY_COLOR[r.category] ?? CATEGORY_COLOR.other}`}>
                            {r.category}
                          </span>
                          {!!r.duplicate_count && r.duplicate_count > 0 && (
                            <div className="mt-1 inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                              +{r.duplicate_count} duplicate
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 truncate max-w-xs">{r.event_name || '—'}</td>
                        <td className="px-4 py-3 font-mono text-xs text-gray-400 truncate max-w-xs">{r.filename || '—'}</td>
                        <td className="px-4 py-3 text-gray-400 truncate max-w-[14rem]">
                          <div className="truncate">{r.reporter_email || '—'}</div>
                          {r.reporter_ip && (
                            <div className="font-mono text-[10px] text-gray-500 truncate flex items-center gap-1">
                              {r.reporter_ip}
                              {r.reporter_ban_state && (
                                <span className={`px-1 rounded text-[9px] font-bold ${
                                  r.reporter_ban_state === 'permaban'
                                    ? 'bg-red-500/30 text-red-300'
                                    : 'bg-orange-500/30 text-orange-300'
                                }`}>
                                  {r.reporter_ban_state}
                                </span>
                              )}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-gray-400 max-w-md">{truncate(r.description, 80) || '—'}</td>
                        <td className="px-4 py-3 text-gray-400 whitespace-nowrap">{formatDate(r.created_at)}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                            r.status === 'pending' ? 'bg-orange-500/20 text-orange-400' :
                            r.status === 'reviewing' ? 'bg-blue-500/20 text-blue-400' :
                            r.status === 'dismissed' ? 'bg-gray-500/20 text-gray-400' :
                            r.status === 'quarantined' ? 'bg-yellow-500/20 text-yellow-400' :
                            'bg-red-500/20 text-red-400'
                          }`}>
                            {r.status}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-col gap-1 items-end">
                            <button
                              onClick={() => router.push(`/admin/abuse-queue/${r.id}`)}
                              className="inline-flex items-center gap-1 px-3 py-1 text-xs bg-orange-500/10 text-orange-400 border border-orange-500/30 rounded hover:bg-orange-500/20 transition-colors"
                            >
                              Review <ArrowRight className="w-3 h-3" />
                            </button>
                            {(r.reporter_ip || r.reporter_email) && r.status !== 'dismissed' && r.status !== 'removed' && (
                              <button
                                onClick={() => handleDismissBySource(r)}
                                disabled={bulkLoading === r.id}
                                title="Dismiss every pending/reviewing report from this reporter"
                                className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] bg-gray-500/10 text-gray-300 border border-gray-500/30 rounded hover:bg-gray-500/20 transition-colors disabled:opacity-50"
                              >
                                {bulkLoading === r.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Ban className="w-3 h-3" />}
                                Dismiss-all
                              </button>
                            )}
                            {r.reporter_ban_state && r.reporter_ip && (
                              <button
                                onClick={() => handleClearBan(r)}
                                disabled={bulkLoading === r.id}
                                title="Clear the soft/permaban on this reporter IP"
                                className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] bg-green-500/10 text-green-300 border border-green-500/30 rounded hover:bg-green-500/20 transition-colors disabled:opacity-50"
                              >
                                {bulkLoading === r.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <ShieldOff className="w-3 h-3" />}
                                Clear ban
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between px-4 py-3 border-t border-white/10 text-sm text-gray-400">
                <span>
                  {offset + 1}–{pageEnd} of {total}
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                    disabled={!hasPrev || loading}
                    className="px-3 py-1 bg-white/10 hover:bg-white/20 rounded disabled:opacity-40 transition-colors"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                    disabled={!hasNext || loading}
                    className="px-3 py-1 bg-white/10 hover:bg-white/20 rounded disabled:opacity-40 transition-colors"
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </AdminLayout>
    </ProtectedRoute>
  )
}
