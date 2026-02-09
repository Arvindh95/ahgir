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
} from 'lucide-react'
import PublicLayout from '@/components/PublicLayout'

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

export default function Home() {
  return (
    <PublicLayout>
      <Head>
        <meta name="description" content="AI-powered face recognition photo sharing for events. Upload photos, share a link, and let guests find themselves with just a selfie." />
      </Head>

      {/* Hero Section */}
      <section className="relative overflow-hidden">
        {/* Background ambience */}
        <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-blue-500/10 rounded-full blur-[150px]" />
        <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] bg-purple-500/10 rounded-full blur-[150px]" />

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-24 md:pt-32 md:pb-32">
          <div className="text-center max-w-3xl mx-auto">
            <h1 className="text-4xl md:text-6xl font-bold tracking-tight leading-tight mb-6">
              Find your event photos with{' '}
              <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                just a selfie
              </span>
            </h1>
            <p className="text-lg md:text-xl text-gray-400 mb-10 leading-relaxed max-w-2xl mx-auto">
              AI-powered face recognition for event photography. Upload photos, share a link, and let your guests find themselves instantly.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <Link
                href="/admin/register"
                className="inline-flex items-center justify-center gap-2 bg-white text-black font-semibold px-8 py-3.5 rounded-xl hover:bg-gray-100 transition-all active:scale-[0.98] text-lg"
              >
                Get Started Free
                <ArrowRight className="w-5 h-5" />
              </Link>
              <a
                href="#how-it-works"
                className="inline-flex items-center justify-center gap-2 glass-button px-8 py-3.5 rounded-xl font-semibold text-lg"
              >
                Learn More
                <ChevronDown className="w-5 h-5" />
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="scroll-mt-20 py-20 md:py-28">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">How it works</h2>
            <p className="text-gray-400 text-lg max-w-xl mx-auto">
              Three simple steps to share event photos effortlessly.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8">
            {steps.map((step, index) => (
              <div
                key={step.title}
                className="glass-card rounded-2xl p-8 text-center relative group hover:bg-white/[0.08] transition-all"
              >
                <div className="text-xs font-bold text-blue-400 mb-4">STEP {index + 1}</div>
                <div className="w-14 h-14 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto mb-5">
                  <step.icon className="w-7 h-7 text-blue-400" />
                </div>
                <h3 className="text-xl font-bold mb-3">{step.title}</h3>
                <p className="text-gray-400 text-sm leading-relaxed">{step.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-20 md:py-28">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Built for event photographers</h2>
            <p className="text-gray-400 text-lg max-w-xl mx-auto">
              Everything you need to share event photos with your guests.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((feature) => (
              <div
                key={feature.title}
                className="glass-card rounded-2xl p-6 hover:bg-white/[0.08] transition-all group"
              >
                <div className="w-11 h-11 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center mb-4 group-hover:border-blue-500/30 transition-colors">
                  <feature.icon className="w-5 h-5 text-gray-300 group-hover:text-blue-400 transition-colors" />
                </div>
                <h3 className="text-lg font-semibold mb-2">{feature.title}</h3>
                <p className="text-gray-400 text-sm leading-relaxed">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-20 md:py-28">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="glass-card rounded-2xl p-10 md:p-16 text-center relative overflow-hidden">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[400px] h-[200px] bg-blue-500/10 rounded-full blur-[100px]" />
            <div className="relative">
              <h2 className="text-3xl md:text-4xl font-bold mb-4">Ready to get started?</h2>
              <p className="text-gray-400 text-lg mb-8 max-w-lg mx-auto">
                Create your first event for free and see the magic of AI-powered photo sharing.
              </p>
              <Link
                href="/admin/register"
                className="inline-flex items-center justify-center gap-2 bg-white text-black font-semibold px-8 py-3.5 rounded-xl hover:bg-gray-100 transition-all active:scale-[0.98] text-lg"
              >
                Get Started Free
                <ArrowRight className="w-5 h-5" />
              </Link>
            </div>
          </div>
        </div>
      </section>
    </PublicLayout>
  )
}
