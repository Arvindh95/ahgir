import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import { paymentService, UserTierInfo, BillingInterval } from '@/lib/payments'
import { useToast } from '@/hooks/useToast'
import { CreditCard, Check, ArrowRight, Loader2, AlertCircle } from 'lucide-react'

const TIERS = [
  {
    key: 'starter' as const,
    name: 'Starter',
    monthly_rm: 39,
    yearly_rm: 390,
    features: ['5 active events', '500 photos per event', '6-month retention'],
  },
  {
    key: 'pro' as const,
    name: 'Pro',
    monthly_rm: 99,
    yearly_rm: 990,
    features: ['20 active events', '2000 photos per event', '1-year retention', 'Priority indexing'],
    popular: true,
  },
]

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
}

function statusLabel(s: string | null, cancelAtPeriodEnd: boolean): { label: string; color: string } {
  if (cancelAtPeriodEnd) return { label: 'Canceling at period end', color: 'text-yellow-400' }
  switch (s) {
    case 'active':
      return { label: 'Active', color: 'text-green-400' }
    case 'trialing':
      return { label: 'Trialing', color: 'text-blue-400' }
    case 'past_due':
      return { label: 'Past due', color: 'text-orange-400' }
    case 'canceled':
      return { label: 'Canceled', color: 'text-red-400' }
    case 'incomplete':
    case 'incomplete_expired':
      return { label: 'Incomplete', color: 'text-orange-400' }
    case 'unpaid':
      return { label: 'Unpaid', color: 'text-red-400' }
    case 'paused':
      return { label: 'Paused', color: 'text-gray-400' }
    default:
      return { label: '—', color: 'text-gray-400' }
  }
}

export default function BillingPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [userTier, setUserTier] = useState<UserTierInfo | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [interval, setInterval] = useState<BillingInterval>('month')
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null)
  const [portalLoading, setPortalLoading] = useState(false)

  useEffect(() => {
    loadTier()
    const { status } = router.query
    if (status === 'success') {
      toast('Subscription active. Welcome aboard.', 'success')
      router.replace('/admin/billing', undefined, { shallow: true })
    } else if (status === 'cancelled') {
      toast('Checkout cancelled.', 'error')
      router.replace('/admin/billing', undefined, { shallow: true })
    }
  }, [router.query.status])

  const loadTier = async () => {
    try {
      setIsLoading(true)
      const tier = await paymentService.getMyTier()
      setUserTier(tier)
    } catch (err: any) {
      toast('Failed to load billing info', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleSubscribe = async (tierName: 'starter' | 'pro') => {
    try {
      setCheckoutLoading(tierName)
      const result = await paymentService.createCheckout(tierName, interval)
      window.location.href = result.checkout_url
    } catch (err: any) {
      const detail = err.response?.data?.detail
      if (typeof detail === 'object' && detail?.code === 'ALREADY_SUBSCRIBED') {
        await handlePortal()
        return
      }
      toast(typeof detail === 'string' ? detail : detail?.message || 'Failed to start checkout', 'error')
      setCheckoutLoading(null)
    }
  }

  const handlePortal = async () => {
    try {
      setPortalLoading(true)
      const result = await paymentService.openPortal()
      window.location.href = result.portal_url
    } catch (err: any) {
      toast(err.response?.data?.detail || 'Failed to open billing portal', 'error')
      setPortalLoading(false)
    }
  }

  const isPaid = userTier && userTier.tier_name !== 'free' && userTier.tier_name !== 'custom'
  const isCustom = userTier?.tier_name === 'custom'
  const status = userTier ? statusLabel(userTier.subscription_status, userTier.cancel_at_period_end) : null

  return (
    <ProtectedRoute>
      <Head><title>Billing - PicUr</title></Head>
      <AdminLayout>
        <div className="max-w-5xl mx-auto">
          <div className="mb-8">
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <CreditCard className="w-8 h-8" />
              Billing
            </h1>
            <p className="text-gray-400 mt-1">Manage your subscription and invoices</p>
          </div>

          {isLoading ? (
            <div className="glass-card rounded-2xl p-8 text-center text-gray-400">
              <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
              Loading...
            </div>
          ) : (
            <>
              <div className="glass-card rounded-2xl p-6 mb-8">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div>
                    <div className="text-sm text-gray-400 mb-1">Current plan</div>
                    <div className="text-2xl font-bold capitalize">{userTier?.tier_name || 'free'}</div>
                    {status && (
                      <div className={`text-sm mt-1 ${status.color}`}>{status.label}</div>
                    )}
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-8 gap-y-2 text-sm">
                    <div>
                      <div className="text-gray-400">Active events</div>
                      <div className="font-semibold">{userTier?.active_events ?? 0} / {userTier?.max_events ?? 0}</div>
                    </div>
                    <div>
                      <div className="text-gray-400">Photos per event</div>
                      <div className="font-semibold">{userTier?.max_photos_per_event ?? 0}</div>
                    </div>
                    <div>
                      <div className="text-gray-400">Retention</div>
                      <div className="font-semibold">{userTier?.retention_days ?? 30} days</div>
                    </div>
                    {userTier?.billing_interval && (
                      <div>
                        <div className="text-gray-400">Billing</div>
                        <div className="font-semibold capitalize">{userTier.billing_interval}ly</div>
                      </div>
                    )}
                    {userTier?.current_period_end && (
                      <div className="col-span-2">
                        <div className="text-gray-400">{userTier.cancel_at_period_end ? 'Ends' : 'Renews'}</div>
                        <div className="font-semibold">{formatDate(userTier.current_period_end)}</div>
                      </div>
                    )}
                  </div>
                </div>

                {userTier?.subscription_status === 'past_due' && (
                  <div className="mt-4 p-3 bg-orange-500/10 border border-orange-500/20 rounded-lg flex items-start gap-2 text-sm text-orange-400">
                    <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <div>
                      Your last payment failed. Update your payment method to avoid downgrade. Subscription drops to Free after a 3-day grace period.
                    </div>
                  </div>
                )}

                {isPaid && (
                  <div className="mt-6 flex gap-3">
                    <button
                      onClick={handlePortal}
                      disabled={portalLoading}
                      className="flex items-center gap-2 bg-white text-black px-4 py-2 rounded-lg font-semibold hover:bg-gray-100 transition-colors disabled:opacity-50"
                    >
                      {portalLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <CreditCard className="w-4 h-4" />}
                      Manage subscription
                    </button>
                  </div>
                )}
              </div>

              {!isPaid && !isCustom && (
                <>
                  <div className="flex justify-center mb-6">
                    <div className="inline-flex items-center bg-white/5 rounded-full p-1 border border-white/10">
                      <button
                        onClick={() => setInterval('month')}
                        className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${
                          interval === 'month' ? 'bg-white text-black' : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        Monthly
                      </button>
                      <button
                        onClick={() => setInterval('year')}
                        className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${
                          interval === 'year' ? 'bg-white text-black' : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        Yearly
                        <span className="ml-2 text-xs text-green-400 font-semibold">Save ~17%</span>
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {TIERS.map((tier) => {
                      const price = interval === 'year' ? tier.yearly_rm : tier.monthly_rm
                      return (
                        <div
                          key={tier.key}
                          className={`rounded-2xl p-6 ${
                            tier.popular
                              ? 'glass-card border-blue-500/30 ring-1 ring-blue-500/20'
                              : 'glass-card'
                          }`}
                        >
                          {tier.popular && (
                            <div className="text-xs font-bold text-blue-400 mb-3">MOST POPULAR</div>
                          )}
                          <h3 className="text-xl font-bold">{tier.name}</h3>
                          <div className="flex items-baseline gap-1 mt-1 mb-4">
                            <span className="text-3xl font-bold">RM {price}</span>
                            <span className="text-gray-400 text-sm">/{interval}</span>
                          </div>
                          <ul className="space-y-2 mb-6">
                            {tier.features.map((f) => (
                              <li key={f} className="flex items-center gap-2 text-sm text-gray-300">
                                <Check className="w-4 h-4 text-green-400 flex-shrink-0" /> {f}
                              </li>
                            ))}
                          </ul>
                          <button
                            onClick={() => handleSubscribe(tier.key)}
                            disabled={checkoutLoading !== null}
                            className={`w-full py-3 rounded-xl font-semibold text-sm transition-all active:scale-[0.98] disabled:opacity-50 ${
                              tier.popular
                                ? 'bg-blue-600 text-white hover:bg-blue-700'
                                : 'bg-white text-black hover:bg-gray-100'
                            }`}
                          >
                            {checkoutLoading === tier.key ? (
                              <span className="flex items-center justify-center gap-2">
                                <Loader2 className="w-4 h-4 animate-spin" /> Redirecting...
                              </span>
                            ) : (
                              <span className="flex items-center justify-center gap-2">
                                Subscribe to {tier.name} <ArrowRight className="w-4 h-4" />
                              </span>
                            )}
                          </button>
                        </div>
                      )
                    })}
                  </div>
                </>
              )}

              {isCustom && (
                <div className="glass-card rounded-2xl p-6 text-sm text-gray-400">
                  You're on a custom plan. Contact{' '}
                  <a href="mailto:support@picur.my" className="text-blue-400 hover:underline">support@picur.my</a>{' '}
                  to make changes.
                </div>
              )}
            </>
          )}
        </div>
      </AdminLayout>
    </ProtectedRoute>
  )
}
