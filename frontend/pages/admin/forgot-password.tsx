import { useState, FormEvent } from 'react'
import Head from 'next/head'
import { authService } from '@/lib/auth'
import { Loader2, Mail, ArrowLeft, CheckCircle } from 'lucide-react'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!email) return

    setIsLoading(true)
    try {
      await authService.forgotPassword(email)
    } catch {
      // Always show success to prevent email enumeration
    } finally {
      setIsLoading(false)
      setSubmitted(true)
    }
  }

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4 overflow-hidden relative">
      <Head><meta name="page-title" content="Forgot Password - PicUr" /></Head>
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] bg-blue-900/10 rounded-full blur-[120px]" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] bg-purple-900/10 rounded-full blur-[120px]" />
      </div>

      <div className="glass-card w-full max-w-md p-8 rounded-2xl relative z-10">
        {!submitted ? (
          <>
            <div className="text-center mb-8">
              <h1 className="text-3xl font-bold mb-2">Reset Password</h1>
              <p className="text-gray-400 text-sm">
                Enter your email and we'll send you a reset link
              </p>
            </div>

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
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading || !email}
                className="group w-full bg-white text-black font-semibold py-3.5 px-4 rounded-xl hover:bg-gray-100 transition-all active:scale-[0.98] flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span>Sending...</span>
                  </>
                ) : (
                  <span>Send Reset Link</span>
                )}
              </button>
            </form>
          </>
        ) : (
          <div className="text-center">
            <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
              <CheckCircle className="w-8 h-8 text-green-400" />
            </div>
            <h1 className="text-2xl font-bold mb-3">Check your email</h1>
            <p className="text-gray-400 mb-8">
              If an account exists for <span className="text-white">{email}</span>, we've sent a password reset link.
            </p>
          </div>
        )}

        <p className="mt-8 text-center text-sm text-gray-500">
          <a href="/admin/login" className="inline-flex items-center gap-1 text-white hover:underline decoration-white/30 underline-offset-4">
            <ArrowLeft className="w-4 h-4" />
            Back to Sign In
          </a>
        </p>
      </div>
    </div>
  )
}
