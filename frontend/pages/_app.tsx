import '@/styles/globals.css'
import type { AppProps } from 'next/app'
import Head from 'next/head'
import { useRouter } from 'next/router'
import ErrorBoundary from '@/components/ErrorBoundary'
import { ToastProvider } from '@/components/Toast'

const SITE = 'https://picur.my'
const DEFAULT_DESCRIPTION =
  'AI-powered face recognition photo sharing for events. Upload photos, share a link, guests find themselves with just a selfie.'
const OG_IMAGE = `${SITE}/og-image.png`

// Per-page metadata. Per-page <Head> tags are still allowed and override these.
// Keep titles under 60 chars and descriptions under 160 for clean SERP rendering.
const PAGE_META: Record<string, { title: string; description: string }> = {
  '/': {
    title: 'PicUr — AI face recognition photo sharing for events',
    description: DEFAULT_DESCRIPTION,
  },
  '/how-it-works': {
    title: 'How it works — PicUr',
    description:
      'See how PicUr works in three steps: upload your event photos, guests scan a selfie, and their matched gallery appears instantly.',
  },
  '/pricing': {
    title: 'Pricing — PicUr',
    description: 'Pay per event with one-time packages — no subscription required. Optional monthly plans for photographers who shoot regularly. Free beta packages available.',
  },
  '/contact': {
    title: 'Contact — PicUr',
    description: 'Get in touch with the PicUr team. Free tailor-made event packages during beta.',
  },
  '/privacy': {
    title: 'Privacy Policy — PicUr',
    description: 'How PicUr handles guest photos, face data, and personal information.',
  },
  '/terms': {
    title: 'Terms of Service — PicUr',
    description: 'PicUr terms of service for photographers and event organizers.',
  },
}

function metaForPath(path: string): { title: string; description: string } {
  // Strip query/hash; treat /foo/ same as /foo
  let p = path.split('?')[0].split('#')[0]
  if (p.length > 1 && p.endsWith('/')) p = p.slice(0, -1)
  return PAGE_META[p] || { title: 'PicUr', description: DEFAULT_DESCRIPTION }
}

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter()
  const { title, description } = metaForPath(router.pathname)
  const canonical = `${SITE}${router.pathname === '/' ? '' : router.pathname}`

  return (
    <>
      <Head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
        <link rel="icon" type="image/png" sizes="96x96" href="/favicon-96x96.png" />
        <link rel="icon" href="/favicon.ico" />
        <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
        <link rel="manifest" href="/site.webmanifest" />
        <meta name="theme-color" content="#000000" />

        {/* Per-page primary tags */}
        <title>{title}</title>
        <meta name="description" content={description} />
        <link rel="canonical" href={canonical} />
        <meta name="robots" content="index, follow" />

        {/* Open Graph */}
        <meta property="og:type" content="website" />
        <meta property="og:site_name" content="PicUr" />
        <meta property="og:title" content={title} />
        <meta property="og:description" content={description} />
        <meta property="og:url" content={canonical} />
        <meta property="og:image" content={OG_IMAGE} />
        <meta property="og:image:width" content="1200" />
        <meta property="og:image:height" content="630" />
        <meta property="og:locale" content="en_US" />

        {/* Twitter Card */}
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={title} />
        <meta name="twitter:description" content={description} />
        <meta name="twitter:image" content={OG_IMAGE} />
      </Head>
      <ErrorBoundary>
        <ToastProvider>
          <Component {...pageProps} />
        </ToastProvider>
      </ErrorBoundary>
    </>
  )
}
