import Link from 'next/link'
import Head from 'next/head'
import {
  Upload,
  Share2,
  ScanFace,
  Brain,
  Zap,
  Shield,
  Smartphone,
  Lock,
  ImageDown,
  ArrowRight,
  ChevronDown,
  Check,
} from 'lucide-react'
import PublicLayout from '@/components/PublicLayout'
import { FadeIn, FadeInStagger } from '@/components/FadeIn'

const steps = [
  {
    icon: Upload,
    title: 'Upload Photos',
    description: 'Upload your event photos to a private, secure gallery in seconds.',
  },
  {
    icon: Share2,
    title: 'Share Your Event',
    description: 'Send guests a simple link or QR code to access your event.',
  },
  {
    icon: ScanFace,
    title: 'Scan & Find',
    description: 'Guests take a quick selfie and AI instantly finds all their photos.',
  },
]

const features = [
  {
    icon: Brain,
    title: 'AI Face Recognition',
    description: 'Advanced AI identifies faces across hundreds of photos in seconds.',
  },
  {
    icon: Zap,
    title: 'Instant Results',
    description: 'Guests find their photos in under 5 seconds with a single selfie.',
  },
  {
    icon: Shield,
    title: 'Privacy First',
    description: 'Face data is processed securely and never shared with third parties.',
  },
  {
    icon: Smartphone,
    title: 'Mobile Friendly',
    description: 'Works perfectly on any device. No app download needed.',
  },
  {
    icon: Lock,
    title: 'Passcode Protected',
    description: 'Secure your events with optional passcode access for guests.',
  },
  {
    icon: ImageDown,
    title: 'Easy Downloads',
    description: 'Guests can download their photos individually or in bulk with one tap.',
  },
]

// JSON-LD structured data — Organization + SoftwareApplication.
// Helps Google show rich snippets (rating, price, etc.) in search results.
const STRUCTURED_DATA = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'Organization',
      '@id': 'https://picur.my/#org',
      name: 'PicUr',
      url: 'https://picur.my',
      logo: 'https://picur.my/web-app-manifest-512x512.png',
      sameAs: [],
    },
    {
      '@type': 'SoftwareApplication',
      '@id': 'https://picur.my/#app',
      name: 'PicUr',
      description:
        'AI-powered face recognition photo sharing platform for event photographers. Guests find their photos using just a selfie.',
      applicationCategory: 'PhotographyApplication',
      operatingSystem: 'Web',
      offers: [
        {
          '@type': 'Offer',
          name: 'Free',
          price: '0',
          priceCurrency: 'USD',
        },
        {
          '@type': 'Offer',
          name: 'Starter',
          price: '9',
          priceCurrency: 'USD',
          priceSpecification: {
            '@type': 'UnitPriceSpecification',
            price: '9',
            priceCurrency: 'USD',
            unitText: 'MONTH',
          },
        },
        {
          '@type': 'Offer',
          name: 'Pro',
          price: '29',
          priceCurrency: 'USD',
          priceSpecification: {
            '@type': 'UnitPriceSpecification',
            price: '29',
            priceCurrency: 'USD',
            unitText: 'MONTH',
          },
        },
      ],
      featureList: [
        'Face recognition photo matching',
        'Multi-angle scan capture',
        'Guest selfie scanning',
        'Bulk photo download',
        'Custom event retention',
      ],
    },
  ],
}

export default function Home() {
  return (
    <PublicLayout>
      <Head>
        {/* Title / description / OG / canonical handled by _app.tsx */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED_DATA) }}
        />
      </Head>

      {/* Hero Section */}
      <section className="relative overflow-hidden min-h-[90vh] flex items-center justify-center">
        {/* Background ambience */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-blue-500/5 rounded-full blur-[120px] pointer-events-none" />
        <div className="absolute bottom-0 right-1/4 w-[600px] h-[600px] bg-purple-500/5 rounded-full blur-[120px] pointer-events-none" />

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
          <div className="text-center max-w-5xl mx-auto">
            <FadeIn>
              <Link
                href="/contact"
                className="inline-flex items-center gap-2 mb-8 px-4 py-2 rounded-full bg-gradient-to-r from-blue-600/20 to-purple-600/20 border border-blue-500/30 hover:border-blue-400/60 transition-colors text-sm font-medium"
              >
                <span className="text-xs font-bold tracking-wider px-2 py-0.5 rounded-full bg-gradient-to-r from-blue-600 to-purple-600 text-white">BETA</span>
                <span className="text-gray-200">Free tailor-made event packages — contact us</span>
                <ArrowRight className="w-3.5 h-3.5 text-blue-300" />
              </Link>
            </FadeIn>

            <FadeIn>
              <h1 className="text-6xl md:text-8xl font-bold tracking-tight leading-[1.1] mb-8">
                Find your photos with{' '}
                <span className="bg-gradient-to-r from-blue-400 via-purple-400 to-blue-400 bg-clip-text text-transparent bg-[length:200%_auto] animate-gradient">
                  just a selfie
                </span>
              </h1>
            </FadeIn>
            
            <FadeIn delay={0.2}>
              <p className="text-xl md:text-2xl text-gray-400 mb-12 leading-relaxed max-w-3xl mx-auto font-light">
                The next generation of event photography. AI-powered face recognition that magically delivers photos to your guests instantly.
              </p>
            </FadeIn>

            <FadeIn delay={0.4}>
              <div className="flex flex-col sm:flex-row gap-6 justify-center items-center">
                <Link
                  href="/admin/register"
                  className="group inline-flex items-center justify-center gap-2 bg-white text-black font-semibold px-10 py-4 rounded-full hover:bg-gray-100 transition-all active:scale-[0.98] text-lg tracking-wide hover:shadow-[0_0_40px_-10px_rgba(255,255,255,0.3)]"
                >
                  Get Started Free
                  <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </Link>
                <a
                  href="#how-it-works"
                  className="group inline-flex items-center justify-center gap-2 glass-button px-10 py-4 rounded-full font-semibold text-lg hover:bg-white/10 transition-all"
                >
                  How it works
                </a>
              </div>
            </FadeIn>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="scroll-mt-20 py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeIn>
            <div className="text-center mb-24">
              <h2 className="text-4xl md:text-6xl font-bold mb-6 tracking-tight">How it works</h2>
              <p className="text-gray-400 text-xl max-w-2xl mx-auto font-light">
                Three simple steps to revolutionize your photo sharing workflow.
              </p>
            </div>
          </FadeIn>

          <FadeInStagger>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-12">
              {steps.map((step, index) => (
                <FadeIn key={step.title}>
                  <div className="glass-card rounded-3xl p-10 text-center relative group hover:bg-white/[0.08] transition-all duration-500 border border-white/5 hover:border-white/10 h-full">
                    <div className="text-sm font-mono text-blue-400 mb-6 tracking-wider">STEP 0{index + 1}</div>
                    <div className="w-16 h-16 rounded-2xl bg-blue-500/10 flex items-center justify-center mx-auto mb-8 group-hover:scale-110 transition-transform duration-500">
                      <step.icon className="w-8 h-8 text-blue-400" />
                    </div>
                    <h3 className="text-2xl font-bold mb-4">{step.title}</h3>
                    <p className="text-gray-400 leading-relaxed font-light text-lg">{step.description}</p>
                  </div>
                </FadeIn>
              ))}
            </div>
          </FadeInStagger>
        </div>
      </section>

      {/* Features */}
      <section className="py-32 relative">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1000px] h-[1000px] bg-gradient-to-b from-blue-900/10 to-transparent rounded-full blur-[150px] pointer-events-none" />
        
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative">
          <FadeIn>
            <div className="text-center mb-24">
              <h2 className="text-4xl md:text-6xl font-bold mb-6 tracking-tight">Built for pros</h2>
              <p className="text-gray-400 text-xl max-w-2xl mx-auto font-light">
                Everything you need to deliver a premium experience to your clients.
              </p>
            </div>
          </FadeIn>

          <FadeInStagger faster>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {features.map((feature) => (
                <FadeIn key={feature.title}>
                  <div className="glass-card rounded-2xl p-8 hover:bg-white/[0.08] transition-all duration-300 group hover:-translate-y-1 border border-white/5 hover:border-white/10">
                    <div className="w-12 h-12 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center mb-6 group-hover:border-blue-500/30 group-hover:bg-blue-500/10 transition-colors">
                      <feature.icon className="w-6 h-6 text-gray-300 group-hover:text-blue-400 transition-colors" />
                    </div>
                    <h3 className="text-xl font-bold mb-3">{feature.title}</h3>
                    <p className="text-gray-400 text-sm leading-relaxed font-light">{feature.description}</p>
                  </div>
                </FadeIn>
              ))}
            </div>
          </FadeInStagger>
        </div>
      </section>

      {/* Security Preview */}
      <section className="py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeIn>
            <div className="text-center mb-24">
              <h2 className="text-4xl md:text-6xl font-bold mb-6 tracking-tight">Built private</h2>
              <p className="text-gray-400 text-xl max-w-2xl mx-auto font-light">
                Your photos stay in your event, your face data is math not faces, and everything auto-deletes when your event ends.
              </p>
            </div>
          </FadeIn>

          <FadeInStagger>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8 max-w-5xl mx-auto">
              {[
                { icon: Lock, title: 'Encrypted everywhere', desc: 'TLS in transit, encrypted storage at rest, bcrypt passwords. GPS and EXIF metadata stripped before storage.' },
                { icon: ScanFace, title: 'Math, not faces', desc: 'Face matching uses numerical embeddings on our own self-hosted AI. No third-party vendor sees your photos.' },
                { icon: Shield, title: 'Auto-deletes with the event', desc: 'Photos, thumbnails, and face data are purged when the retention window ends; encrypted backups roll off within 7 days.' },
              ].map((item) => (
                <FadeIn key={item.title}>
                  <div className="glass-card rounded-2xl p-8 flex flex-col h-full">
                    <div className="w-10 h-10 rounded-xl bg-blue-500/15 text-blue-300 flex items-center justify-center mb-5">
                      <item.icon className="w-5 h-5" />
                    </div>
                    <h3 className="text-lg font-bold mb-2">{item.title}</h3>
                    <p className="text-gray-400 text-sm leading-relaxed">{item.desc}</p>
                  </div>
                </FadeIn>
              ))}
            </div>
          </FadeInStagger>

          <FadeIn>
            <div className="text-center mt-12">
              <Link
                href="/security"
                className="inline-flex items-center gap-2 text-blue-400 hover:text-blue-300 font-medium transition-colors"
              >
                See the full security breakdown
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </FadeIn>
        </div>
      </section>

      {/* Pricing Preview */}
      <section className="py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeIn>
            <div className="text-center mb-24">
              <h2 className="text-4xl md:text-6xl font-bold mb-6 tracking-tight">Simple pricing</h2>
              <p className="text-gray-400 text-xl max-w-2xl mx-auto font-light">
                Start free, upgrade your account when you need more.
              </p>
            </div>
          </FadeIn>

          <FadeInStagger>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8 max-w-5xl mx-auto">
              {[
                { name: 'Free', price: '$0', period: '', desc: '1 active event, 25 photos', highlighted: false },
                { name: 'Starter', price: '$9', period: '/month', desc: '5 active events, 250 photos each', highlighted: true },
                { name: 'Pro', price: '$29', period: '/month', desc: '20 active events, 500 photos each', highlighted: false },
              ].map((tier) => (
                <FadeIn key={tier.name}>
                  <div className={`rounded-2xl p-8 flex flex-col text-center ${
                    tier.highlighted
                      ? 'glass-card border-blue-500/30 ring-1 ring-blue-500/20'
                      : 'glass-card'
                  }`}>
                    {tier.highlighted && (
                      <div className="text-xs font-bold text-blue-400 mb-4">MOST POPULAR</div>
                    )}
                    <h3 className="text-xl font-bold mb-1">{tier.name}</h3>
                    <div className="flex items-baseline gap-1 justify-center mb-2">
                      <span className="text-3xl font-bold">{tier.price}</span>
                      {tier.period && <span className="text-gray-400 text-sm">{tier.period}</span>}
                    </div>
                    <p className="text-gray-400 text-sm mb-6">{tier.desc}</p>
                    <ul className="space-y-2 mb-6 text-left">
                      {['Face recognition', 'Guest scanning', 'Photo downloads'].map((f) => (
                        <li key={f} className="flex items-center gap-2 text-sm text-gray-300">
                          <Check className="w-4 h-4 text-green-400 flex-shrink-0" />
                          {f}
                        </li>
                      ))}
                    </ul>
                  </div>
                </FadeIn>
              ))}
            </div>
          </FadeInStagger>

          <FadeIn>
            <div className="max-w-3xl mx-auto mt-16">
              <div className="glass-card rounded-2xl p-8 text-center">
                <div className="text-xs font-bold text-blue-400 mb-3 tracking-wider">SHOOTING ONE EVENT?</div>
                <h3 className="text-2xl font-bold mb-3">One-time event packages</h3>
                <p className="text-gray-400 mb-6 max-w-xl mx-auto">
                  Shooting a single event and don&apos;t need a recurring subscription?
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
          </FadeIn>

          <FadeIn>
            <div className="text-center mt-12">
              <Link
                href="/pricing"
                className="inline-flex items-center gap-2 text-blue-400 hover:text-blue-300 font-medium transition-colors"
              >
                View full pricing details
                <ArrowRight className="w-4 h-4" />
              </Link>
              <p className="text-gray-500 text-sm mt-4">
                Need a custom plan? Contact us at{' '}
                <a href="mailto:support@picur.my" className="text-gray-400 hover:text-white transition-colors underline">
                  support@picur.my
                </a>
              </p>
            </div>
          </FadeIn>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-32">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeIn>
            <div className="glass-card rounded-[2.5rem] p-12 md:p-24 text-center relative overflow-hidden border border-white/10">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-blue-500/20 rounded-full blur-[120px] pointer-events-none" />
              
              <div className="relative z-10">
                <h2 className="text-4xl md:text-6xl font-bold mb-8 tracking-tight">Ready to get started?</h2>
                <p className="text-gray-300 text-xl mb-12 max-w-2xl mx-auto font-light">
                  Create your first event for free and experience the magic of AI-powered photo sharing today.
                </p>
                <Link
                  href="/admin/register"
                  className="inline-flex items-center justify-center gap-2 bg-white text-black font-semibold px-12 py-5 rounded-full hover:bg-gray-100 transition-all active:scale-[0.98] text-lg tracking-wide hover:shadow-[0_0_40px_-5px_rgba(255,255,255,0.4)]"
                >
                  Get Started Free
                  <ArrowRight className="w-5 h-5" />
                </Link>
              </div>
            </div>
          </FadeIn>
        </div>
      </section>
    </PublicLayout>
  )
}
