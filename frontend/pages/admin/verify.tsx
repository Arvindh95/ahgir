import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { authService } from '@/lib/auth'
import { Loader2, CheckCircle, XCircle } from 'lucide-react'

export default function VerifyEmail() {
  const router = useRouter()
  const { token } = router.query

  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const verifiedRef = useRef(false)

  useEffect(() => {
    if (!token || typeof token !== 'string') return
    if (verifiedRef.current) return
    verifiedRef.current = true

    const verify = async () => {
      try {
        const res = await authService.verifyEmail(token)
        setMessage(res.message)
        setStatus('success')
      } catch (err: any) {
        setMessage(err.response?.data?.error?.message || 'Verification failed')
        setStatus('error')
      }
    }

    verify()
  }, [token])

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4 overflow-hidden relative">
      <Head><title>Verify Email - PicUr</title></Head>
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
        <div className={`absolute top-[-20%] left-[-10%] w-[60%] h-[60%] ${status === 'success' ? 'bg-green-900/10' : status === 'error' ? 'bg-red-900/10' : 'bg-blue-900/10'} rounded-full blur-[120px]`} />
        <div className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] bg-purple-900/10 rounded-full blur-[120px]" />
      </div>

      <div className="glass-card w-full max-w-md p-8 rounded-2xl relative z-10 text-center">
        {status === 'loading' && (
          <>
            <div className="w-16 h-16 bg-blue-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
              <Loader2 className="w-8 h-8 text-blue-400 animate-spin" />
            </div>
            <h1 className="text-2xl font-bold mb-3">Verifying your email</h1>
            <p className="text-gray-400">Please wait...</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
              <CheckCircle className="w-8 h-8 text-green-400" />
            </div>
            <h1 className="text-2xl font-bold mb-3">Email Verified!</h1>
            <p className="text-gray-400 mb-8">{message}</p>
            <a
              href="/admin/login"
              className="inline-block bg-white text-black font-semibold py-3 px-8 rounded-xl hover:bg-gray-100 transition-all"
            >
              Sign In
            </a>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
              <XCircle className="w-8 h-8 text-red-400" />
            </div>
            <h1 className="text-2xl font-bold mb-3">Verification Failed</h1>
            <p className="text-gray-400 mb-8">{message}</p>
            <a
              href="/admin/login"
              className="inline-block bg-white text-black font-semibold py-3 px-8 rounded-xl hover:bg-gray-100 transition-all"
            >
              Go to Sign In
            </a>
          </>
        )}
      </div>
    </div>
  )
}
