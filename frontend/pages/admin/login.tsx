import { useState, FormEvent, useEffect } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { authService } from '@/lib/auth'
import GoogleAuthSection from '@/components/GoogleAuthSection'
import { Loader2, Lock, Mail, ArrowRight, RefreshCw } from 'lucide-react'

// Error codes the Google OAuth callback can append as ?error= when it bounces
// the user back here. Anything unrecognised falls back to a generic message.
const OAUTH_ERROR_MESSAGES: Record<string, string> = {
  oauth_cancelled: 'Google sign-in was cancelled.',
  oauth_state: 'Google sign-in could not be verified. Please try again.',
  oauth_failed: 'Google sign-in failed. Please try again.',
  oauth_unverified_email: "Your Google account's email is not verified.",
  oauth_conflict: 'This email is already linked to a different Google account.',
  oauth_unavailable: 'Google sign-in is currently unavailable.',
  account_disabled: 'This account has been disabled. Contact an administrator.',
}

export default function Login() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [showResend, setShowResend] = useState(false)
  const [resendLoading, setResendLoading] = useState(false)
  const [resendSuccess, setResendSuccess] = useState(false)

  useEffect(() => {
    // Auth state now lives in an HttpOnly cookie; the only way to know
    // is to ask the server. We fire-and-forget — a logged-in visitor
    // gets bounced to /admin/events; anyone else just stays on this
    // page (no error UI for "not logged in"; that's the whole point).
    authService.isAuthenticated().then((authed) => {
      if (authed) router.push('/admin/events')
    })
  }, [router])

  useEffect(() => {
    // Surface a failed Google sign-in (the callback redirects here with
    // ?error=<code>). Wait for the router to hydrate query params, then strip
    // the param from the URL so a refresh doesn't re-show a stale error.
    if (!router.isReady) return
    const code = router.query.error
    if (typeof code === 'string') {
      setError(OAUTH_ERROR_MESSAGES[code] || 'Google sign-in failed. Please try again.')
      router.replace('/admin/login', undefined, { shallow: true })
    }
  }, [router.isReady, router.query.error, router])

  const validateForm = (): boolean => {
    if (!email || !password) {
      setError('Email and password are required')
      return false
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError('Invalid email format')
      return false
    }

    return true
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setShowResend(false)
    setResendSuccess(false)

    if (!validateForm()) {
      return
    }

    setIsLoading(true)

    try {
      await authService.login(email, password)
      router.push('/admin/events')
    } catch (err: any) {
      if (err.response?.status === 429) {
        const detail = err.response?.data?.detail || ''
        const retryAfter = err.response?.headers?.['retry-after']
        const minutes = retryAfter ? Math.ceil(parseInt(retryAfter) / 60) : null
        setError(
          minutes
            ? `Too many login attempts. Please wait ${minutes} minute${minutes > 1 ? 's' : ''} and try again.`
            : 'Too many login attempts. Please wait a few minutes and try again.'
        )
        return
      }

      const errorCode = err.response?.data?.error?.code
      const errorMessage = err.response?.data?.error?.message || 'Login failed'

      setError(errorMessage)

      if (errorCode === 'EMAIL_NOT_VERIFIED') {
        setShowResend(true)
      }
    } finally {
      setIsLoading(false)
    }
  }

  const handleResend = async () => {
    setResendLoading(true)
    setResendSuccess(false)

    try {
      await authService.resendVerification(email)
      setResendSuccess(true)
    } catch (err: any) {
      // Don't show error, the API always returns success for security
      setResendSuccess(true)
    } finally {
      setResendLoading(false)
    }
  }

  return (
    <>
      <Head><title>Login - PicUr</title></Head>
      <div className="min-h-screen bg-black flex items-center justify-center p-4 overflow-hidden relative">
        {/* Background Ambience */}
        <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
          <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] bg-blue-900/10 rounded-full blur-[120px]" />
          <div className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] bg-purple-900/10 rounded-full blur-[120px]" />
        </div>

        <div className="glass-card w-full max-w-md p-8 rounded-2xl relative z-10">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold mb-2">Admin Login</h1>
            <p className="text-gray-400 text-sm">Sign in to manage your events</p>
          </div>

          <GoogleAuthSection label="Continue with Google" />

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <label htmlFor="email" className="block text-sm font-medium text-gray-300 ml-1">
                Email Address
              </label>
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="glass-input w-full pl-12 pr-4 py-3 rounded-xl bg-white/5 border border-white/10 focus:ring-2 focus:ring-white/20 transition-all placeholder:text-gray-600"
                  placeholder="admin@example.com"
                  disabled={isLoading}
                />
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="password" className="block text-sm font-medium text-gray-300 ml-1">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="glass-input w-full pl-12 pr-4 py-3 rounded-xl bg-white/5 border border-white/10 focus:ring-2 focus:ring-white/20 transition-all placeholder:text-gray-600"
                  placeholder="••••••••"
                  disabled={isLoading}
                />
              </div>
            </div>

            <div className="text-right -mt-2">
              <a href="/admin/forgot-password" className="text-sm text-gray-400 hover:text-white transition-colors">
                Forgot password?
              </a>
            </div>

            {error && (
              <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm text-center">
                {error}
                {showResend && !resendSuccess && (
                  <button
                    type="button"
                    onClick={handleResend}
                    disabled={resendLoading}
                    className="mt-3 w-full flex items-center justify-center gap-2 text-blue-400 hover:text-blue-300 transition-colors"
                  >
                    {resendLoading ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Sending...
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-4 h-4" />
                        Resend verification email
                      </>
                    )}
                  </button>
                )}
                {resendSuccess && (
                  <p className="mt-3 text-green-400">Verification email sent! Check your inbox.</p>
                )}
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="group w-full bg-white text-black font-semibold py-3.5 px-4 rounded-xl hover:bg-gray-100 transition-all active:scale-[0.98] flex items-center justify-center gap-2"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>Logging in...</span>
                </>
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </>
              )}
            </button>
          </form>

          <p className="mt-8 text-center text-sm text-gray-500">
            Don't have an account?{' '}
            <a href="/admin/register" className="text-white hover:underline decoration-white/30 underline-offset-4">
              Register
            </a>
          </p>
        </div>
      </div>
    </>
  )
}
