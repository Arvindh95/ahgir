import '@/styles/globals.css'
import type { AppProps } from 'next/app'
import Head from 'next/head'
import { useRouter } from 'next/router'
import { useEffect } from 'react'
import ErrorBoundary from '@/components/ErrorBoundary'
import { ToastProvider } from '@/components/Toast'

const PAGE_TITLES: Record<string, string> = {
  '/admin/login': 'Login - PicUr',
  '/admin/register': 'Register - PicUr',
  '/admin/forgot-password': 'Forgot Password - PicUr',
  '/admin/verify': 'Verify Email - PicUr',
  '/admin/reset-password': 'Reset Password - PicUr',
  '/admin/superadmin': 'Super Admin - PicUr',
  '/admin/events': 'Events - PicUr',
  '/admin/events/create': 'Create Event - PicUr',
  '/admin/events/[id]': 'Event Details - PicUr',
  '/admin/events/[id]/photos': 'Photos - PicUr',
  '/e/[slug]': 'Event - PicUr',
  '/e/[slug]/gallery': 'Gallery - PicUr',
  '/e/[slug]/results': 'Results - PicUr',
  '/e/[slug]/scan': 'Scan - PicUr',
}

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter()

  useEffect(() => {
    document.title = PAGE_TITLES[router.pathname] || 'PicUr'
  }, [router.pathname])

  return (
    <>
      <Head>
        <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
        <link rel="icon" type="image/png" sizes="96x96" href="/favicon-96x96.png" />
        <link rel="icon" href="/favicon.ico" />
        <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
        <link rel="manifest" href="/site.webmanifest" />
        <meta name="theme-color" content="#000000" />
      </Head>
      <ErrorBoundary>
        <ToastProvider>
          <Component {...pageProps} />
        </ToastProvider>
      </ErrorBoundary>
    </>
  )
}
