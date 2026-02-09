import Head from 'next/head'
import Link from 'next/link'
import { Check, ArrowRight } from 'lucide-react'
import PublicLayout from '@/components/PublicLayout'

// TODO: finalize pricing values and tiers
const tiers = [
  {
    name: 'Free',
    price: 'RM0',
    period: '',
    description: 'Perfect for trying out PicUr',
    features: [
      '1 event',
      'Up to 50 photos',
      'Face recognition',
      'Guest scanning',
      'Photo downloads',
    ],
    cta: 'Get Started',
    href: '/admin/register',
    disabled: false,
    highlighted: false,
  },
  {
    name: 'Single Event',
    price: 'RM29',
    period: 'per event',
    description: 'For one-time events like weddings or parties',
    features: [
      '1 event',
      'Up to 2,000 photos',
      'Face recognition',
      'Guest scanning',
      'Photo downloads',
      'Priority support',
    ],
    cta: 'Coming Soon',
    href: '#',
    disabled: true,
    highlighted: true,
  },
  {
    name: 'Pro',
    price: 'RM79',
    period: '/month',
    description: 'For photographers and frequent event organizers',
    features: [
      'Unlimited events',
      'Unlimited photos',
      'Face recognition',
      'Guest scanning',
      'Photo downloads',
      'Priority support',
      'Analytics dashboard',
    ],
    cta: 'Coming Soon',
    href: '#',
    disabled: true,
    highlighted: false,
  },
]

export default function Pricing() {
  return (
    <PublicLayout>
      <Head>
        <meta name="description" content="PicUr Pricing - Choose the plan that fits your needs." />
      </Head>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 md:py-24">
        <div className="text-center mb-16">
          <h1 className="text-3xl md:text-4xl font-bold mb-4">Simple, transparent pricing</h1>
          <p className="text-gray-400 text-lg max-w-xl mx-auto">
            Start free, upgrade when you need more.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8 max-w-5xl mx-auto">
          {tiers.map((tier) => (
            <div
              key={tier.name}
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
                <span className="text-3xl font-bold">{tier.price}</span>
                {tier.period && <span className="text-gray-400 text-sm">{tier.period}</span>}
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

              {tier.disabled ? (
                <button
                  disabled
                  className="w-full py-3 rounded-xl font-semibold text-sm bg-white/10 text-gray-500 cursor-not-allowed"
                >
                  {tier.cta}
                </button>
              ) : (
                <Link
                  href={tier.href}
                  className="inline-flex items-center justify-center gap-2 w-full py-3 rounded-xl font-semibold text-sm bg-white text-black hover:bg-gray-100 transition-all active:scale-[0.98]"
                >
                  {tier.cta}
                  <ArrowRight className="w-4 h-4" />
                </Link>
              )}
            </div>
          ))}
        </div>
      </div>
    </PublicLayout>
  )
}
