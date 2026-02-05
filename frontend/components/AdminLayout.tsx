import { useRouter } from 'next/router'
import { authService } from '@/lib/auth'
import { LogOut, Menu } from 'lucide-react'

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
    <div className="min-h-screen bg-black text-white">
      <nav className="border-b border-white/10 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-8">
              <h2 
                className="text-xl font-bold cursor-pointer hover:opacity-80 transition-opacity" 
                onClick={() => router.push('/admin/events')}
              >
                PicUr Admin
              </h2>
              <div className="hidden md:flex gap-6">
                <a
                  href="/admin/events"
                  className="text-sm font-medium text-gray-300 hover:text-white transition-colors"
                >
                  Events
                </a>
              </div>
            </div>
            
            <div className="flex items-center gap-4">
              <button
                onClick={handleLogout}
                className="flex items-center gap-2 text-sm font-medium text-gray-400 hover:text-white transition-colors px-3 py-2 rounded-lg hover:bg-white/5"
              >
                <LogOut className="w-4 h-4" />
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  )
}
