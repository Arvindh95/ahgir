import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

// Per-request CSP nonce. Pages Router's _document reads it from the
// request headers via getInitialProps and applies it to NextScript and
// any other inline <script> elements.
export function middleware(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString('base64')

  // strict-dynamic: scripts loaded by nonced scripts (Next.js framework)
  // also run, so we don't have to enumerate every chunk URL.
  // 'unsafe-inline' is a fallback for browsers that don't understand
  // strict-dynamic — modern browsers ignore it once nonces are present.
  const cspHeader =
    `default-src 'self'; ` +
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' 'unsafe-inline' https: http:; ` +
    `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; ` +
    `img-src 'self' data: blob:; ` +
    `font-src 'self' data: https://fonts.gstatic.com; ` +
    `connect-src 'self' https://api.stripe.com https://cloudflareinsights.com https://cdn.jsdelivr.net; ` +
    `frame-src https://js.stripe.com https://hooks.stripe.com; ` +
    `media-src 'self' blob:; ` +
    `object-src 'none'; ` +
    `base-uri 'self'; ` +
    `form-action 'self'; ` +
    `frame-ancestors 'self'`

  const requestHeaders = new Headers(request.headers)
  requestHeaders.set('x-nonce', nonce)
  requestHeaders.set('content-security-policy', cspHeader)

  const response = NextResponse.next({ request: { headers: requestHeaders } })
  response.headers.set('content-security-policy', cspHeader)
  return response
}

// Skip API, static assets, prefetch requests (cache-friendly).
export const config = {
  matcher: [
    {
      source: '/((?!api|_next/static|_next/image|favicon.ico).*)',
      missing: [
        { type: 'header', key: 'next-router-prefetch' },
        { type: 'header', key: 'purpose', value: 'prefetch' },
      ],
    },
  ],
}
