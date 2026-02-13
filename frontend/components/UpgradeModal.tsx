import { useState } from 'react'
import { X, Loader2, Zap, Check } from 'lucide-react'
import { paymentService } from '@/lib/payments'

interface UpgradeModalProps {
  open: boolean
  currentTier: string
  onClose: () => void
}

const UPGRADE_TIERS = [
  {
    key: 'premium',
    name: 'Premium',
    price_cents: 5000,
    events: '3',
    photos: '300',
    features: ['Up to 3 events', 'Up to 300 photos per event', 'Face recognition', 'Guest scanning'],
    popular: true,
  },
  {
    key: 'premium_plus',
    name: 'Premium+',
    price_cents: 10000,
    events: '10',
    photos: '500',
    features: ['Up to 10 events', 'Up to 500 photos per event', 'Face recognition', 'Guest scanning'],
  },
]

const TIER_ORDER = ['free', 'premium', 'premium_plus']

function getUpgradePrice(currentTier: string, targetTier: string): number {
  const prices: Record<string, number> = { free: 0, premium: 5000, premium_plus: 10000 }
  return (prices[targetTier] || 0) - (prices[currentTier] || 0)
}

export default function UpgradeModal({ open, currentTier, onClose }: UpgradeModalProps) {
  const [isLoading, setIsLoading] = useState<string | null>(null)
  const [error, setError] = useState('')

  if (!open) return null

  const currentIdx = TIER_ORDER.indexOf(currentTier)
  const availableTiers = UPGRADE_TIERS.filter((t) => {
    const targetIdx = TIER_ORDER.indexOf(t.key)
    return targetIdx > currentIdx
  })

  const handleUpgrade = async (tierName: string) => {
    try {
      setIsLoading(tierName)
      setError('')
      const result = await paymentService.createCheckout(tierName)
      window.location.href = result.checkout_url
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to start checkout')
      setIsLoading(null)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div
        className="glass-card rounded-2xl p-8 max-w-2xl w-full mx-4 relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 rounded-lg hover:bg-white/10 transition-colors"
        >
          <X className="w-5 h-5 text-gray-400" />
        </button>

        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/20 text-blue-400 text-sm font-medium mb-4">
            <Zap className="w-4 h-4" /> Upgrade Account
          </div>
          <h2 className="text-2xl font-bold">Unlock more events & photos</h2>
          <p className="text-gray-400 mt-2">Choose a plan to increase your limits</p>
        </div>

        {error && (
          <div className="mb-6 p-3 bg-red-500/10 border border-red-500/20 text-red-400 rounded-xl text-sm text-center">
            {error}
          </div>
        )}

        <div className={`grid gap-4 ${availableTiers.length === 1 ? 'max-w-sm mx-auto' : 'grid-cols-1 md:grid-cols-2'}`}>
          {availableTiers.map((tier) => {
            const price = getUpgradePrice(currentTier, tier.key)
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
                  <span className="text-3xl font-bold">RM {price / 100}</span>
                  <span className="text-gray-400 text-sm">one-time</span>
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
                      <Loader2 className="w-4 h-4 animate-spin" /> Redirecting to payment...
                    </span>
                  ) : (
                    `Upgrade to ${tier.name}`
                  )}
                </button>
              </div>
            )
          })}
        </div>

        <p className="text-xs text-gray-500 text-center mt-6">
          Secure payment powered by Stripe. One-time payment per account.
        </p>
      </div>
    </div>
  )
}
