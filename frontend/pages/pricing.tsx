import Head from 'next/head'
import Link from 'next/link'
import { useState } from 'react'
import { Check, ArrowRight } from 'lucide-react'
import PublicLayout from '@/components/PublicLayout'

type Interval = 'month' | 'year'

const tiers = [
  {
    key: 'free',
    name: 'Free',
    monthlyUSD: 0,
    yearlyUSD: 0,
    description: 'Try PicUr with one event',
    features: [
      '1 active event',
      'Up to 50 photos per event',
      '30-day retention',
      'Face recognition',
      'Guest scanning',
      'Photo downloads',
    ],
    cta: 'Get Started',
    href: '/admin/register',
    highlighted: false,
  },
  {
    key: 'starter',
    name: 'Starter',
    monthlyUSD: 9,
    yearlyUSD: 90,
    description: 'For photographers running a few events at a time',
    features: [
      '5 active events',
      'Up to 500 photos per event',
      '6-month retention',
      'Face recognition',
      'Guest scanning',
      'Photo downloads',
    ],
    cta: 'Subscribe',
    href: '/admin/register?plan=starter',
    highlighted: true,
  },
  {
    key: 'pro',
    name: 'Pro',
    monthlyUSD: 29,
    yearlyUSD: 290,
    description: 'For studios managing many events year-round',
    features: [
      '20 active events',
      'Up to 2000 photos per event',
      '1-year retention',
      'Face recognition',
      'Guest scanning',
      'Photo downloads',
      'Priority indexing',
    ],
    cta: 'Subscribe',
    href: '/admin/register?plan=pro',
    highlighted: false,
  },
]

export default function Pricing() {
  const [interval, setInterval] = useState<Interval>('month')

  const formatPrice = (tier: typeof tiers[0]) => {
    if (tier.key === 'free') return '$0'
    return interval === 'year' ? `$${tier.yearlyUSD}` : `$${tier.monthlyUSD}`
  }

  const formatPeriod = (tier: typeof tiers[0]) => {
    if (tier.key === 'free') return ''
    return interval === 'year' ? '/year' : '/month'
  }

  return (
    <PublicLayout>
      <Head>
        <meta name="description" content="PicUr Pricing - Subscription plans for wedding photographers." />
      </Head>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 md:py-24">
        <div className="text-center mb-10">
          <h1 className="text-3xl md:text-4xl font-bold mb-4">Simple, transparent pricing</h1>
          <p className="text-gray-400 text-lg max-w-xl mx-auto">
            Pay monthly or save with annual billing. Cancel anytime.
          </p>
        </div>

        <div className="flex justify-center mb-12">
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

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8 max-w-5xl mx-auto">
          {tiers.map((tier) => (
            <div
              key={tier.key}
              className={`rounded-2xl p-8 flex flex-col ${
                tier.highlighted
                  ? 'glass-card border-blue-500/30 ring-1 ring-blue-500/20'
                  : 'glass-card'
              }`}
            >
              {tier.highlighted && (
                <div className="text-xs font-bold text-blue-400 mb-4">MOST POPULAR</div>
              )}
              <h3 className="text-xl font-bold mb-1">{tier.name}</h3>
              <div className="flex items-baseline gap-1 mb-2">
                <span className="text-3xl font-bold">{formatPrice(tier)}</span>
                {formatPeriod(tier) && <span className="text-gray-400 text-sm">{formatPeriod(tier)}</span>}
              </div>
              <p className="text-gray-400 text-sm mb-6">{tier.description}</p>

              <ul className="space-y-3 mb-8 flex-1">
                {tier.features.map((feature) => (
                  <li key={feature} className="flex items-center gap-2 text-sm text-gray-300">
                    <Check className="w-4 h-4 text-green-400 flex-shrink-0" />
                    {feature}
                  </li>
                ))}
              </ul>

              <Link
                href={tier.href}
                className={`inline-flex items-center justify-center gap-2 w-full py-3 rounded-xl font-semibold text-sm transition-all active:scale-[0.98] ${
                  tier.highlighted
                    ? 'bg-blue-600 text-white hover:bg-blue-700'
                    : 'bg-white text-black hover:bg-gray-100'
                }`}
              >
                {tier.cta}
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          ))}
        </div>

        <div className="max-w-3xl mx-auto mt-16">
          <div className="glass-card rounded-2xl p-8 text-center">
            <div className="text-xs font-bold text-blue-400 mb-3 tracking-wider">SHOOTING ONE EVENT?</div>
            <h2 className="text-2xl font-bold mb-3">One-time event packages</h2>
            <p className="text-gray-400 mb-6 max-w-xl mx-auto">
              Photographing a single wedding and don&apos;t need a recurring subscription?
              We offer one-time event packages tailored to your photo count and retention needs.
              Contact us with your event details and we&apos;ll send a custom quote.
            </p>
            <a
              href="mailto:support@picur.my?subject=One-time%20event%20package&body=Hi%2C%20I'd%20like%20a%20quote%20for%20a%20one-time%20event.%0A%0AEvent%20date%3A%0AEstimated%20guest%20count%3A%0AEstimated%20photo%20count%3A%0AAccess%20duration%20needed%3A"
              className="inline-flex items-center gap-2 bg-white text-black px-6 py-3 rounded-xl font-semibold text-sm hover:bg-gray-100 transition-colors"
            >
              Request a quote
              <ArrowRight className="w-4 h-4" />
            </a>
          </div>
        </div>

        <p className="text-center text-gray-500 text-sm mt-12">
          Need a custom plan? Contact us at{' '}
          <a href="mailto:support@picur.my" className="text-gray-400 hover:text-white transition-colors underline">
            support@picur.my
          </a>
        </p>
      </div>
    </PublicLayout>
  )
}
