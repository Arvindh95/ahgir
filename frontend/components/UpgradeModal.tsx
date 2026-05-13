import { useState } from 'react'
import { X, Loader2, Zap, Check } from 'lucide-react'
import { paymentService, BillingInterval } from '@/lib/payments'

interface UpgradeModalProps {
  open: boolean
  currentTier: string
  onClose: () => void
}

const UPGRADE_TIERS = [
  {
    key: 'starter' as const,
    name: 'Starter',
    monthly_cents: 900,
    yearly_cents: 9000,
    events: '5',
    photos: '250',
    retention: '6 months',
    features: ['5 active events', 'Up to 250 photos per event', '6-month retention', 'Face recognition', 'Guest scanning'],
    popular: true,
  },
  {
    key: 'pro' as const,
    name: 'Pro',
    monthly_cents: 2900,
    yearly_cents: 29000,
    events: '20',
    photos: '500',
    retention: '1 year',
    features: ['20 active events', 'Up to 500 photos per event', '1-year retention', 'Face recognition', 'Guest scanning', 'Priority indexing'],
  },
]

const TIER_ORDER = ['free', 'starter', 'pro']

export default function UpgradeModal({ open, currentTier, onClose }: UpgradeModalProps) {
  const [isLoading, setIsLoading] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [billingInterval, setBillingInterval] = useState<BillingInterval>('month')

  if (!open) return null

  const currentIdx = TIER_ORDER.indexOf(currentTier)
  const availableTiers = UPGRADE_TIERS.filter((t) => {
    const targetIdx = TIER_ORDER.indexOf(t.key)
    return targetIdx > currentIdx
  })

  const handleUpgrade = async (tierName: 'starter' | 'pro') => {
    try {
      setIsLoading(tierName)
      setError('')
      const result = await paymentService.createCheckout(tierName, interval)
      window.location.href = result.checkout_url
    } catch (err: any) {
      const detail = err.response?.data?.detail
      if (typeof detail === 'object' && detail?.code === 'ALREADY_SUBSCRIBED') {
        try {
          const portal = await paymentService.openPortal()
          window.location.href = portal.portal_url
          return
        } catch {
          setError('You already have an active subscription. Open billing settings to change plan.')
        }
      } else {
        setError(typeof detail === 'string' ? detail : detail?.message || 'Failed to start checkout')
      }
      setIsLoading(null)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        className="glass-card rounded-2xl p-8 max-w-2xl w-full my-auto relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 rounded-lg hover:bg-white/10 transition-colors"
        >
          <X className="w-5 h-5 text-gray-400" />
        </button>

        <div className="text-center mb-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/20 text-blue-400 text-sm font-medium mb-4">
            <Zap className="w-4 h-4" /> Upgrade Account
          </div>
          <h2 className="text-2xl font-bold">Unlock more active events</h2>
          <p className="text-gray-400 mt-2">Subscribe monthly or yearly. Cancel anytime.</p>
        </div>

        <div className="flex justify-center mb-6">
          <div className="inline-flex items-center bg-white/5 rounded-full p-1 border border-white/10">
            <button
              onClick={() => setBillingInterval('month')}
              className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${
                billingInterval === 'month' ? 'bg-white text-black' : 'text-gray-400 hover:text-white'
              }`}
            >
              Monthly
            </button>
            <button
              onClick={() => setBillingInterval('year')}
              className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${
                billingInterval === 'year' ? 'bg-white text-black' : 'text-gray-400 hover:text-white'
              }`}
            >
              Yearly
              <span className="ml-1.5 text-[10px] text-green-400 font-semibold">-17%</span>
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-6 p-3 bg-red-500/10 border border-red-500/20 text-red-400 rounded-xl text-sm text-center">
            {error}
          </div>
        )}

        <div className={`grid gap-4 ${availableTiers.length === 1 ? 'max-w-sm mx-auto' : 'grid-cols-1 md:grid-cols-2'}`}>
          {availableTiers.map((tier) => {
            const cents = billingInterval === 'year' ? tier.yearly_cents : tier.monthly_cents
            const period = billingInterval === 'year' ? '/year' : '/month'
            return (
              <div
                key={tier.key}
                className={`rounded-xl p-6 border ${
                  tier.popular
                    ? 'border-blue-500/30 bg-blue-500/5 ring-1 ring-blue-500/20'
                    : 'border-white/10 bg-white/5'
                }`}
              >
                {tier.popular && (
                  <div className="text-xs font-bold text-blue-400 mb-3">RECOMMENDED</div>
                )}
                <h3 className="text-lg font-bold">{tier.name}</h3>
                <div className="flex items-baseline gap-1 mt-1 mb-4">
                  <span className="text-3xl font-bold">${cents / 100}</span>
                  <span className="text-gray-400 text-sm">{period}</span>
                </div>

                <ul className="space-y-2 mb-6">
                  {tier.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm text-gray-300">
                      <Check className="w-4 h-4 text-green-400 flex-shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>

                <button
                  onClick={() => handleUpgrade(tier.key)}
                  disabled={isLoading !== null}
                  className={`w-full py-3 rounded-xl font-semibold text-sm transition-all active:scale-[0.98] disabled:opacity-50 ${
                    tier.popular
                      ? 'bg-blue-600 text-white hover:bg-blue-700'
                      : 'bg-white text-black hover:bg-gray-100'
                  }`}
                >
                  {isLoading === tier.key ? (
                    <span className="flex items-center justify-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" /> Redirecting to checkout...
                    </span>
                  ) : (
                    `Subscribe to ${tier.name}`
                  )}
                </button>
              </div>
            )
          })}
        </div>

        <p className="text-xs text-gray-500 text-center mt-6">
          Secure billing powered by Stripe. Cancel anytime from the billing portal.
        </p>
      </div>
    </div>
  )
}
