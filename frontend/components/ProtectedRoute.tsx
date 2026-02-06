import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import { authService } from '@/lib/auth'

interface ProtectedRouteProps {
  children: React.ReactNode
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const router = useRouter()
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const checkAuth = async () => {
      if (!authService.isAuthenticated()) {
        router.push('/admin/login')
        return
      }

      try {
        await authService.getMe()
        setIsLoading(false)
      } catch (error) {
        authService.logout()
        router.push('/admin/login')
      }
    }

    checkAuth()
  }, [router])

  if (isLoading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <img src="/favicon-96x96.png" alt="PicUr" className="w-12 h-12 animate-pulse" />
          <div className="w-8 h-8 border-2 border-white/20 border-t-white rounded-full animate-spin" />
        </div>
      </div>
    )
  }

  return <>{children}</>
}
