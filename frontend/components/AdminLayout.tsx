import { useRouter } from 'next/router'
import { authService } from '@/lib/auth'

interface AdminLayoutProps {
  children: React.ReactNode
}

export default function AdminLayout({ children }: AdminLayoutProps) {
  const router = useRouter()

  const handleLogout = () => {
    authService.logout()
    router.push('/admin/login')
  }

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f5f5f5' }}>
      <nav style={{
        backgroundColor: '#0070f3',
        color: 'white',
        padding: '15px 30px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <h2 style={{ margin: 0, cursor: 'pointer' }} onClick={() => router.push('/admin/events')}>
          PicUr Admin
        </h2>
        <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
          <a
            href="/admin/events"
            style={{ color: 'white', textDecoration: 'none', cursor: 'pointer' }}
          >
            Events
          </a>
          <button
            onClick={handleLogout}
            style={{
              backgroundColor: 'transparent',
              color: 'white',
              border: '1px solid white',
              padding: '5px 15px',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            Logout
          </button>
        </div>
      </nav>
      <main style={{ padding: '30px' }}>
        {children}
      </main>
    </div>
  )
}
