import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import AdminLayout from '@/components/AdminLayout'
import ProtectedRoute from '@/components/ProtectedRoute'
import UpgradeModal from '@/components/UpgradeModal'
import { paymentService, UserTierInfo } from '@/lib/payments'
import { eventService, Event } from '@/lib/events'
import { authService } from '@/lib/auth'
import { Zap, Loader2 } from 'lucide-react'

const TIER_BADGE: Record<string, string> = {
  free: 'bg-gray-500/20 text-gray-400',
  starter: 'bg-blue-500/20 text-blue-400',
  pro: 'bg-purple-500/20 text-purple-400',
  custom: 'bg-yellow-500/20 text-yellow-400',
}

export default function PlanAndUsagePage() {
  const router = useRouter()
  const [userTier, setUserTier] = useState<UserTierInfo | null>(null)
  const [events, setEvents] = useState<Event[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [showUpgradeModal, setShowUpgradeModal] = useState(false)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        setIsLoading(true)
        const me = await authService.getMe()
        if (cancelled) return
        if (me.is_superadmin) {
          router.replace('/admin/events')
          return
        }
        const [tier, eventList] = await Promise.all([
          paymentService.getMyTier(),
          eventService.getEvents(),
        ])
        if (cancelled) return
        setUserTier(tier)
        setEvents(eventList)
      } catch (err: any) {
        if (cancelled) return
        setError(err.response?.data?.error?.message || 'Failed to load plan info')
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [router])

  const tierName = userTier?.tier_name || 'free'
  const canUpgrade = tierName !== 'pro' && tierName !== 'custom'
  const photoCap = userTier?.max_photos_per_event ?? 25

  return (
    <ProtectedRoute>
      <Head><title>Plan &amp; Usage - PicUr</title></Head>
      <AdminLayout>
        <div className="max-w-5xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-3xl font-bold flex items-center gap-2">
              <Zap className="w-7 h-7 text-yellow-400" /> Plan &amp; Usage
            </h1>
            {canUpgrade && (
              <button
                onClick={() => setShowUpgradeModal(true)}
                className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg font-semibold hover:bg-blue-700 transition-colors"
              >
                <Zap className="w-4 h-4" /> Upgrade Plan
              </button>
            )}
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl">
              {error}
            </div>
          )}

          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-white" />
            </div>
          ) : (
            <>
              {/* Plan summary */}
              <div className="glass-card p-6 rounded-2xl mb-8">
                <div className="flex flex-wrap items-center gap-4 mb-4">
                  <span className={`px-3 py-1 rounded-full text-sm font-bold uppercase ${TIER_BADGE[tierName] ?? TIER_BADGE.free}`}>
                    {tierName}
                  </span>
                  {userTier && (
                    <span className="text-sm text-gray-400">
                      {userTier.active_events} / {userTier.max_events} active events
                    </span>
                  )}
                  <span className="text-sm text-gray-400">
                    {photoCap.toLocaleString()} photos / event
                  </span>
                  {userTier?.retention_days != null && (
                    <span className="text-sm text-gray-400">
                      {userTier.retention_days}-day retention
                    </span>
                  )}
                </div>

                {userTier && userTier.max_events > 0 && (
                  <div>
                    <div className="flex justify-between text-xs text-gray-400 mb-1">
                      <span>Events used</span>
                      <span>{userTier.active_events} / {userTier.max_events}</span>
                    </div>
                    <div className="w-full bg-white/10 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full transition-all ${
                          userTier.active_events / userTier.max_events > 0.9 ? 'bg-red-500' :
                          userTier.active_events / userTier.max_events > 0.7 ? 'bg-yellow-500' :
                          'bg-blue-500'
                        }`}
                        style={{ width: `${Math.min(100, (userTier.active_events / userTier.max_events) * 100)}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Per-event usage */}
              <h2 className="text-xl font-bold mb-4">Per-event photo usage</h2>
              {events.length === 0 ? (
                <div className="glass-card p-6 rounded-2xl text-gray-400 text-sm">
                  No events yet. Create one to see its usage here.
                </div>
              ) : (
                <div className="space-y-4">
                  {events.map((ev) => {
                    const used = ev.photo_count ?? 0
                    const pct = photoCap > 0 ? Math.min(100, (used / photoCap) * 100) : 0
                    const barColor = pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-yellow-500' : 'bg-blue-500'
                    return (
                      <button
                        key={ev.event_id}
                        onClick={() => router.push(`/admin/events/${ev.event_id}`)}
                        className="w-full text-left glass-card p-5 rounded-2xl hover:bg-white/[0.07] transition-colors"
                      >
                        <div className="flex items-center justify-between mb-2 gap-3">
                          <div className="min-w-0">
                            <div className="font-semibold truncate">{ev.name}</div>
                            <div className="text-xs text-gray-500 truncate">/e/{ev.slug}</div>
                          </div>
                          <div className="text-sm text-gray-400 whitespace-nowrap">
                            {used.toLocaleString()} / {photoCap.toLocaleString()} photos
                          </div>
                        </div>
                        <div className="w-full bg-white/10 rounded-full h-2">
                          <div
                            className={`h-2 rounded-full transition-all ${barColor}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </div>

        <UpgradeModal
          open={showUpgradeModal}
          onClose={() => setShowUpgradeModal(false)}
          currentTier={tierName}
        />
      </AdminLayout>
    </ProtectedRoute>
  )
}
