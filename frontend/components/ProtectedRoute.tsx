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
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <p>Loading...</p>
      </div>
    )
  }

  return <>{children}</>
}
