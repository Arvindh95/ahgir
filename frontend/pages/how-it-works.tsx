import { useState } from 'react'
import Link from 'next/link'
import {
  Upload,
  ScanFace,
  Images,
  ArrowRight,
  Check,
  Camera,
  Download,
  QrCode,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import PublicLayout from '@/components/PublicLayout'
import { FadeIn, FadeInStagger } from '@/components/FadeIn'

// Real photos live in /public/how-it-works/. Until a file is present, each tile
// falls back to a CSS gradient (see PhotoTile) so the page never looks broken.
const UPLOAD_PHOTOS = Array.from({ length: 8 }, (_, i) => `/how-it-works/upload-${i + 1}.jpg`)
const RESULT_PHOTOS = Array.from({ length: 10 }, (_, i) => `/how-it-works/result-${i + 1}.jpg`)
const SCAN_PHOTO = '/how-it-works/scan.jpg'

// Gradient fallbacks for any tile whose photo hasn't been added yet.
const TILE_GRADIENTS = [
  'from-blue-500/40 to-cyan-400/20',
  'from-purple-500/40 to-pink-400/20',
  'from-amber-500/40 to-rose-400/20',
  'from-emerald-500/40 to-teal-400/20',
  'from-indigo-500/40 to-blue-400/20',
  'from-rose-500/40 to-orange-400/20',
  'from-sky-500/40 to-indigo-400/20',
  'from-fuchsia-500/40 to-purple-400/20',
  'from-teal-500/40 to-emerald-400/20',
]

// An <img> that swaps to a gradient placeholder if the file is missing / fails.
function PhotoTile({ src, gradient, className = '' }: { src: string; gradient: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) {
    return <div className={`${className} bg-gradient-to-br ${gradient} border border-white/10`} />
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      className={`${className} object-cover w-full h-full border border-white/10`}
    />
  )
}

const STEPS = [
  {
    n: '01',
    who: 'You, the photographer',
    icon: Upload,
    title: 'Upload your gallery',
    body:
      'Drag in your event photos. PicUr encrypts them, strips GPS and EXIF metadata, and quietly indexes every face in the background — no tagging, no manual sorting.',
    points: ['Bulk drag-and-drop upload', 'Private by default', 'Automatic face indexing'],
  },
  {
    n: '02',
    who: 'Your guests',
    icon: ScanFace,
    title: 'Guests scan their face',
    body:
      'Share a link or QR code. Each guest snaps a quick selfie, and our self-hosted AI turns it into a numeric faceprint — math, never a stored photo of them.',
    points: ['Just one selfie', 'Works on any phone', 'No app to install'],
  },
  {
    n: '03',
    who: 'Instantly',
    icon: Images,
    title: 'Their photos appear',
    body:
      'In a few seconds, every photo a guest appears in shows up in their own personal gallery — ready to download one by one or all at once. They can stick to just their matches, or browse the entire event gallery whenever they like.',
    points: [
      'Results in ~5 seconds',
      'See just their photos — or the whole gallery',
      'One-tap downloads',
    ],
  },
]

/* ----------------------------- visual mockups ----------------------------- */

function UploadMockup() {
  return (
    <div className="glass-card rounded-3xl p-5 w-full max-w-md mx-auto shadow-2xl">
      {/* window chrome */}
      <div className="flex items-center gap-2 mb-5">
        <span className="w-3 h-3 rounded-full bg-red-400/70" />
        <span className="w-3 h-3 rounded-full bg-yellow-400/70" />
        <span className="w-3 h-3 rounded-full bg-green-400/70" />
        <span className="ml-3 text-xs text-gray-400 font-medium">Beach Wedding · 2026</span>
      </div>

      {/* drop zone */}
      <div className="rounded-2xl border-2 border-dashed border-white/15 bg-white/[0.03] py-6 flex flex-col items-center justify-center mb-4">
        <Upload className="w-7 h-7 text-blue-400 mb-2" />
        <p className="text-sm text-gray-300 font-medium">Drag photos here</p>
        <p className="text-xs text-gray-500">or click to browse</p>
      </div>

      {/* uploaded photo grid */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        {UPLOAD_PHOTOS.map((src, i) => (
          <PhotoTile
            key={src}
            src={src}
            gradient={TILE_GRADIENTS[i % TILE_GRADIENTS.length]}
            className="aspect-square rounded-lg overflow-hidden"
          />
        ))}
      </div>

      {/* progress */}
      <div className="flex items-center justify-between text-xs text-gray-400 mb-1.5">
        <span>Uploading 248 photos…</span>
        <span className="text-blue-300">indexing faces</span>
      </div>
      <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div className="hiw-fill h-full rounded-full bg-gradient-to-r from-blue-500 to-purple-500" />
      </div>
    </div>
  )
}

function ScanMockup() {
  const [failed, setFailed] = useState(false)
  return (
    <div className="flex justify-center">
      {/* phone frame */}
      <div className="relative w-[230px] rounded-[2.5rem] border border-white/15 bg-black/60 p-3 shadow-2xl">
        <div className="absolute top-3 left-1/2 -translate-x-1/2 w-20 h-1.5 rounded-full bg-white/15" />
        <div className="relative mt-5 aspect-[9/16] rounded-[1.8rem] overflow-hidden bg-gradient-to-b from-blue-950/40 to-black border border-white/10">
          {/* the guest's face (or fallback icon) */}
          {failed ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <ScanFace className="hiw-pulse w-24 h-24 text-blue-300/80" strokeWidth={1.25} />
            </div>
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={SCAN_PHOTO}
              alt="Guest scanning their face"
              onError={() => setFailed(true)}
              className="absolute inset-0 w-full h-full object-cover"
            />
          )}

          {/* dim + viewfinder brackets sit on top of the photo */}
          <div className="absolute inset-0 bg-blue-950/20" />
          <div className="absolute inset-6 rounded-2xl">
            <span className="absolute top-0 left-0 w-7 h-7 border-t-2 border-l-2 border-blue-400/80 rounded-tl-xl" />
            <span className="absolute top-0 right-0 w-7 h-7 border-t-2 border-r-2 border-blue-400/80 rounded-tr-xl" />
            <span className="absolute bottom-0 left-0 w-7 h-7 border-b-2 border-l-2 border-blue-400/80 rounded-bl-xl" />
            <span className="absolute bottom-0 right-0 w-7 h-7 border-b-2 border-r-2 border-blue-400/80 rounded-br-xl" />
          </div>

          {/* scanning line */}
          <div className="hiw-scan-line absolute left-5 right-5 h-px bg-gradient-to-r from-transparent via-blue-300 to-transparent shadow-[0_0_12px_2px_rgba(96,165,250,0.6)]" />

          {/* shutter */}
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 rounded-full bg-white/90 text-black text-xs font-semibold px-4 py-2">
            <Camera className="w-4 h-4" />
            Scan
          </div>
        </div>
      </div>
    </div>
  )
}

function GalleryMockup() {
  return (
    <div className="glass-card rounded-3xl p-5 w-full max-w-md mx-auto shadow-2xl">
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-sm font-bold">Your photos</p>
          <p className="text-xs text-gray-400">{RESULT_PHOTOS.length} matches found</p>
        </div>
        <div className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1.5 text-xs font-medium">
          <Download className="w-3.5 h-3.5" />
          Download all
        </div>
      </div>

      <FadeInStagger faster>
        <div className="grid grid-cols-3 gap-2">
          {RESULT_PHOTOS.map((src, i) => (
            <FadeIn key={src}>
              <PhotoTile
                src={src}
                gradient={TILE_GRADIENTS[i % TILE_GRADIENTS.length]}
                className="aspect-square rounded-xl overflow-hidden"
              />
            </FadeIn>
          ))}
        </div>
      </FadeInStagger>
    </div>
  )
}

const MOCKUPS = [UploadMockup, ScanMockup, GalleryMockup]

export default function HowItWorks() {
  return (
    <PublicLayout>
      {/* Prefix-namespaced keyframes for the in-code mockups. */}
      <style jsx global>{`
        @keyframes hiw-scan {
          0% { top: 12%; opacity: 0; }
          15% { opacity: 1; }
          85% { opacity: 1; }
          100% { top: 84%; opacity: 0; }
        }
        @keyframes hiw-fill {
          0% { width: 8%; }
          70% { width: 100%; }
          100% { width: 100%; }
        }
        @keyframes hiw-pulse {
          0%, 100% { opacity: 0.45; }
          50% { opacity: 0.9; }
        }
        .hiw-scan-line { animation: hiw-scan 2.6s ease-in-out infinite; }
        .hiw-fill { animation: hiw-fill 3.2s ease-in-out infinite; }
        .hiw-pulse { animation: hiw-pulse 2.4s ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce) {
          .hiw-scan-line, .hiw-fill, .hiw-pulse { animation: none; }
          .hiw-scan-line { top: 50%; }
        }
      `}</style>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[600px] bg-blue-500/5 rounded-full blur-[120px] pointer-events-none" />
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-24 pb-16 text-center">
          <FadeIn>
            <span className="inline-flex items-center gap-2 mb-6 px-4 py-2 rounded-full bg-white/5 border border-white/10 text-sm text-gray-300">
              <Sparkles className="w-4 h-4 text-blue-400" />
              How it works
            </span>
          </FadeIn>
          <FadeIn delay={0.1}>
            <h1 className="text-5xl md:text-7xl font-bold tracking-tight leading-[1.1] mb-6">
              From upload to{' '}
              <span className="bg-gradient-to-r from-blue-400 via-purple-400 to-blue-400 bg-clip-text text-transparent">
                “there I am!”
              </span>
            </h1>
          </FadeIn>
          <FadeIn delay={0.2}>
            <p className="text-xl text-gray-400 max-w-2xl mx-auto font-light">
              Three simple steps. No app to install, no endless scrolling through thousands of
              photos — guests find every shot they&apos;re in with a single selfie.
            </p>
          </FadeIn>
        </div>
      </section>

      {/* Steps — alternating text / mockup */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-16 space-y-24 md:space-y-32">
        {STEPS.map((step, i) => {
          const Mockup = MOCKUPS[i]
          const flip = i % 2 === 1
          return (
            <FadeIn key={step.n}>
              <div className="grid md:grid-cols-2 gap-10 md:gap-16 items-center">
                {/* copy */}
                <div className={flip ? 'md:order-2' : ''}>
                  <div className="flex items-center gap-3 mb-5">
                    <span className="text-sm font-mono text-blue-400 tracking-wider">
                      STEP {step.n}
                    </span>
                    <span className="text-xs text-gray-500 px-2.5 py-1 rounded-full bg-white/5 border border-white/10">
                      {step.who}
                    </span>
                  </div>
                  <div className="w-14 h-14 rounded-2xl bg-blue-500/10 flex items-center justify-center mb-6">
                    <step.icon className="w-7 h-7 text-blue-400" />
                  </div>
                  <h2 className="text-3xl md:text-4xl font-bold mb-4 tracking-tight">
                    {step.title}
                  </h2>
                  <p className="text-gray-400 text-lg leading-relaxed font-light mb-6">
                    {step.body}
                  </p>
                  <ul className="space-y-2.5">
                    {step.points.map((p) => (
                      <li key={p} className="flex items-center gap-2.5 text-gray-300">
                        <Check className="w-5 h-5 text-green-400 flex-shrink-0" />
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* mockup */}
                <div className={flip ? 'md:order-1' : ''}>
                  <Mockup />
                </div>
              </div>
            </FadeIn>
          )
        })}
      </section>

      {/* Privacy reassurance strip */}
      <section className="py-24">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeIn>
            <div className="glass-card rounded-3xl p-8 md:p-12">
              <div className="flex flex-col md:flex-row md:items-center gap-6">
                <div className="w-14 h-14 rounded-2xl bg-blue-500/15 text-blue-300 flex items-center justify-center flex-shrink-0">
                  <ShieldCheck className="w-7 h-7" />
                </div>
                <div className="flex-1">
                  <h3 className="text-2xl font-bold mb-2">Private by design</h3>
                  <p className="text-gray-400 leading-relaxed">
                    Selfies are turned into numeric faceprints, not stored as photos. Matching runs
                    on our own self-hosted AI — no third-party vendor ever sees your guests. When the
                    event&apos;s retention window ends, photos and face data are purged automatically.
                  </p>
                  <Link
                    href="/security"
                    className="inline-flex items-center gap-2 mt-4 text-blue-400 hover:text-blue-300 font-medium transition-colors"
                  >
                    Read the full security breakdown
                    <ArrowRight className="w-4 h-4" />
                  </Link>
                </div>
              </div>
            </div>
          </FadeIn>
        </div>
      </section>

      {/* Final CTA */}
      <section className="pb-32">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <FadeIn>
            <div className="glass-card rounded-[2.5rem] p-12 md:p-20 text-center relative overflow-hidden border border-white/10">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-blue-500/20 rounded-full blur-[120px] pointer-events-none" />
              <div className="relative z-10">
                <div className="flex items-center justify-center gap-2 mb-6 text-gray-400 text-sm">
                  <QrCode className="w-4 h-4" />
                  Share a link or QR code — that&apos;s all your guests need
                </div>
                <h2 className="text-4xl md:text-5xl font-bold mb-6 tracking-tight">
                  Try it on your next event
                </h2>
                <p className="text-gray-300 text-lg mb-10 max-w-2xl mx-auto font-light">
                  Create your first event free and watch the magic happen.
                </p>
                <Link
                  href="/admin/register"
                  className="inline-flex items-center justify-center gap-2 bg-white text-black font-semibold px-10 py-4 rounded-full hover:bg-gray-100 transition-all active:scale-[0.98] text-lg tracking-wide hover:shadow-[0_0_40px_-10px_rgba(255,255,255,0.3)]"
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
