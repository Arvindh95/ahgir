import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import AdminLayout from '@/components/AdminLayout'
import ProtectedRoute from '@/components/ProtectedRoute'
import { abuseService, AbuseReportRow, AbuseRevealResponse } from '@/lib/abuse'
import { authService } from '@/lib/auth'
import { useToast } from '@/hooks/useToast'
import { ArrowLeft, Loader2, Trash2, EyeOff, X } from 'lucide-react'

const CATEGORY_COLOR: Record<string, string> = {
  csam: 'bg-red-600/30 text-red-200 border-red-500/40',
  nudity: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
  harassment: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
  copyright: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
  violence: 'bg-red-500/20 text-red-300 border-red-500/40',
  other: 'bg-gray-500/20 text-gray-300 border-gray-500/40',
}

function formatDate(iso: string | null | undefined) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

export default function AbuseReviewScreen() {
  const router = useRouter()
  const { toast } = useToast()
  const { report_id } = router.query
  const [report, setReport] = useState<AbuseReportRow | null>(null)
  const [reveal, setReveal] = useState<AbuseRevealResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    authService.getMe().then((u) => {
      if (!u.is_superadmin) router.replace('/admin/events')
    }).catch(() => router.replace('/admin/login'))
  }, [router])

  useEffect(() => {
    if (!report_id || typeof report_id !== 'string') return
    let cancelled = false
    const load = async () => {
      try {
        setLoading(true)
        // Reveal fires first — it sets reviewing state and mints the signed
        // URL. The reveal endpoint also returns the current report status.
        const revealData = await abuseService.reveal(report_id)
        if (cancelled) return
        setReveal(revealData)
        // Then fetch row metadata. The Phase-1 service hits /list and
        // finds locally; follow-up will add a dedicated single-get
        // endpoint.
        const row = await abuseService.get(report_id)
        if (cancelled) return
        setReport(row)
      } catch (err: any) {
        if (cancelled) return
        setError(err.response?.data?.detail || 'Failed to load report')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [report_id])

  const isTerminal = !!(report && (report.status === 'dismissed' || report.status === 'removed'))

  const doAction = async (kind: 'dismiss' | 'quarantine' | 'delete') => {
    if (!report || !report_id || typeof report_id !== 'string') return
    const prompts = {
      dismiss: 'Mark this report as not abuse?',
      quarantine: 'Hide the image from guests? Bytes stay in storage; you can still review here.',
      delete: 'Permanently remove the photo? Cannot be undone.',
    }
    if (!window.confirm(prompts[kind])) return
    try {
      setActionLoading(kind)
      if (kind === 'dismiss') await abuseService.dismiss(report_id)
      if (kind === 'quarantine') await abuseService.quarantine(report_id)
      if (kind === 'delete') await abuseService.deletePhoto(report_id)
      toast(`Report ${kind}ed.`, 'success')
      router.push('/admin/abuse-queue')
    } catch (err: any) {
      toast(err.response?.data?.detail || `Failed to ${kind}`, 'error')
      setActionLoading(null)
    }
  }

  return (
    <ProtectedRoute>
      <Head><title>Review report - PicUr</title></Head>
      <AdminLayout>
        <div className="max-w-6xl mx-auto">
          <button
            onClick={() => router.push('/admin/abuse-queue')}
            className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors mb-4"
          >
            <ArrowLeft className="w-4 h-4" /> Back to queue
          </button>

          {loading ? (
            <div className="text-center py-12">
              <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
              <p className="text-sm text-gray-400">Loading photo for review…</p>
            </div>
          ) : error || !report ? (
            <div className="glass-card rounded-2xl p-8 text-center text-red-400">
              {error || 'Report not found'}
            </div>
          ) : (
            <>
              {isTerminal && (
                <div className="mb-6 p-4 bg-gray-500/10 border border-gray-500/20 rounded-xl text-sm">
                  <strong>This report was already actioned</strong> by{' '}
                  {report.reviewed_by_email || 'an operator'} on {formatDate(report.reviewed_at)}.
                  The image action ({report.action_taken}) cannot be undone here.
                </div>
              )}

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Image viewer */}
                <div className="lg:col-span-2 glass-card rounded-2xl p-4">
                  {reveal && (
                    <img
                      src={reveal.review_url}
                      alt="reported"
                      className="w-full max-h-[80vh] object-contain rounded bg-black"
                    />
                  )}
                  <div className="mt-3 text-xs text-gray-500 font-mono">
                    {report.filename || '—'} · uploaded {formatDate(report.uploaded_at)}
                  </div>
                </div>

                {/* Context + actions */}
                <div className="glass-card rounded-2xl p-6 space-y-4">
                  <div>
                    <span className={`px-3 py-1 rounded-full text-sm font-bold uppercase border ${CATEGORY_COLOR[report.category] ?? CATEGORY_COLOR.other}`}>
                      {report.category}
                    </span>
                  </div>

                  {report.description && (
                    <div>
                      <div className="text-xs text-gray-500 uppercase mb-1">Description</div>
                      <p className="text-sm whitespace-pre-wrap">{report.description}</p>
                    </div>
                  )}

                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between">
                      <span className="text-gray-500">Reporter email</span>
                      <span className="text-gray-300">{report.reporter_email || '—'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Reporter IP</span>
                      <span className="text-gray-300 font-mono">{report.reporter_ip || '—'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Reported at</span>
                      <span className="text-gray-300">{formatDate(report.created_at)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Reviewed at</span>
                      <span className="text-gray-300">{formatDate(report.reviewed_at)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Reviewed by</span>
                      <span className="text-gray-300">{report.reviewed_by_email || '—'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Status</span>
                      <span className="text-gray-300">{report.status}</span>
                    </div>
                  </div>

                  {report.event_name && (
                    <button
                      onClick={() => router.push(`/admin/events/${report.event_id}`)}
                      className="w-full text-left text-xs px-3 py-2 bg-white/5 hover:bg-white/10 rounded transition-colors"
                    >
                      View event: <span className="text-gray-300">{report.event_name}</span>
                    </button>
                  )}

                  <div className="pt-4 border-t border-white/10 space-y-2">
                    <button
                      onClick={() => doAction('dismiss')}
                      disabled={!!actionLoading || isTerminal}
                      className="w-full flex items-center justify-center gap-2 bg-gray-500/10 text-gray-300 border border-gray-500/30 px-4 py-2 rounded-lg font-semibold hover:bg-gray-500/20 transition-colors disabled:opacity-50"
                    >
                      {actionLoading === 'dismiss' ? <Loader2 className="w-4 h-4 animate-spin" /> : <X className="w-4 h-4" />}
                      Dismiss
                    </button>
                    <button
                      onClick={() => doAction('quarantine')}
                      disabled={!!actionLoading || isTerminal}
                      className="w-full flex items-center justify-center gap-2 bg-yellow-500/10 text-yellow-400 border border-yellow-500/30 px-4 py-2 rounded-lg font-semibold hover:bg-yellow-500/20 transition-colors disabled:opacity-50"
                    >
                      {actionLoading === 'quarantine' ? <Loader2 className="w-4 h-4 animate-spin" /> : <EyeOff className="w-4 h-4" />}
                      Quarantine
                    </button>
                    <button
                      onClick={() => doAction('delete')}
                      disabled={!!actionLoading || isTerminal}
                      className="w-full flex items-center justify-center gap-2 bg-red-500/10 text-red-400 border border-red-500/30 px-4 py-2 rounded-lg font-semibold hover:bg-red-500/20 transition-colors disabled:opacity-50"
                    >
                      {actionLoading === 'delete' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                      Delete photo
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </AdminLayout>
    </ProtectedRoute>
  )
}
