import { useState, FormEvent } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { authService } from '@/lib/auth'
import { Loader2, Lock, CheckCircle, XCircle, Check, Circle } from 'lucide-react'

const PASSWORD_RULES = [
  { label: 'At least 8 characters', test: (p: string) => p.length >= 8 },
  { label: 'One uppercase letter (A-Z)', test: (p: string) => /[A-Z]/.test(p) },
  { label: 'One lowercase letter (a-z)', test: (p: string) => /[a-z]/.test(p) },
  { label: 'One digit (0-9)', test: (p: string) => /\d/.test(p) },
  { label: 'One special character (!@#$%^&*…)', test: (p: string) => /[!@#$%^&*(),.?":{}|<>]/.test(p) },
]

function PasswordChecklist({ password }: { password: string }) {
  return (
    <ul className="space-y-1 text-xs">
      {PASSWORD_RULES.map((rule) => {
        const ok = rule.test(password)
        return (
          <li
            key={rule.label}
            className={`flex items-center gap-2 ${ok ? 'text-green-400' : 'text-gray-500'}`}
          >
            {ok ? <Check className="w-3.5 h-3.5" /> : <Circle className="w-3.5 h-3.5" />}
            <span>{rule.label}</span>
          </li>
        )
      })}
    </ul>
  )
}

export default function ResetPassword() {
  const router = useRouter()
  const { token } = router.query

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [status, setStatus] = useState<'form' | 'success' | 'error'>('form')
  const [errorMessage, setErrorMessage] = useState('')

  const validatePassword = (): boolean => {
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return false
    }
    if (!/[A-Z]/.test(password)) {
      setError('Password must contain at least one uppercase letter')
      return false
    }
    if (!/[a-z]/.test(password)) {
      setError('Password must contain at least one lowercase letter')
      return false
    }
    if (!/\d/.test(password)) {
      setError('Password must contain at least one digit')
      return false
    }
    if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
      setError('Password must contain at least one special character')
      return false
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return false
    }
    return true
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')

    if (!validatePassword()) return

    if (!token || typeof token !== 'string') {
      setError('Invalid reset link')
      return
    }

    setIsLoading(true)
    try {
      await authService.resetPassword(token, password)
      setStatus('success')
    } catch (err: any) {
      const msg = err.response?.data?.error?.message || err.response?.data?.detail || 'Reset failed'
      setErrorMessage(msg)
      setStatus('error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4 overflow-hidden relative">
      <Head><title>Reset Password - PicUr</title></Head>
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
        <div className={`absolute top-[-20%] left-[-10%] w-[60%] h-[60%] ${status === 'success' ? 'bg-green-900/10' : status === 'error' ? 'bg-red-900/10' : 'bg-blue-900/10'} rounded-full blur-[120px]`} />
        <div className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] bg-purple-900/10 rounded-full blur-[120px]" />
      </div>

      <div className="glass-card w-full max-w-md p-8 rounded-2xl relative z-10">
        {status === 'form' && (
          <>
            <div className="text-center mb-8">
              <h1 className="text-3xl font-bold mb-2">New Password</h1>
              <p className="text-gray-400 text-sm">Enter your new password below</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="space-y-2">
                <label htmlFor="password" className="block text-sm font-medium text-gray-300 ml-1">
                  New Password
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

              <div className="space-y-2">
                <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-300 ml-1">
                  Confirm Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                  <input
                    id="confirmPassword"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="glass-input w-full pl-12 pr-4 py-3 rounded-xl bg-white/5 border border-white/10 focus:ring-2 focus:ring-white/20 transition-all placeholder:text-gray-600"
                    placeholder="••••••••"
                    disabled={isLoading}
                  />
                </div>
              </div>

              <PasswordChecklist password={password} />

              {error && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm text-center">
                  {error}
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
                    <span>Resetting...</span>
                  </>
                ) : (
                  <span>Reset Password</span>
                )}
              </button>
            </form>
          </>
        )}

        {status === 'success' && (
          <div className="text-center">
            <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
              <CheckCircle className="w-8 h-8 text-green-400" />
            </div>
            <h1 className="text-2xl font-bold mb-3">Password Reset!</h1>
            <p className="text-gray-400 mb-8">Your password has been updated. You can now sign in.</p>
            <a
              href="/admin/login"
              className="inline-block bg-white text-black font-semibold py-3 px-8 rounded-xl hover:bg-gray-100 transition-all"
            >
              Sign In
            </a>
          </div>
        )}

        {status === 'error' && (
          <div className="text-center">
            <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
              <XCircle className="w-8 h-8 text-red-400" />
            </div>
            <h1 className="text-2xl font-bold mb-3">Reset Failed</h1>
            <p className="text-gray-400 mb-8">{errorMessage}</p>
            <a
              href="/admin/forgot-password"
              className="inline-block bg-white text-black font-semibold py-3 px-8 rounded-xl hover:bg-gray-100 transition-all"
            >
              Request New Link
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
