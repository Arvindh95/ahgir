import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import Image from 'next/image'
import { authService } from '@/lib/auth'
import { LogOut, Shield, Menu, X, CreditCard } from 'lucide-react'

interface AdminLayoutProps {
  children: React.ReactNode
}

export default function AdminLayout({ children }: AdminLayoutProps) {
  const router = useRouter()
  const [isSuperadmin, setIsSuperadmin] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  useEffect(() => {
    authService.getMe().then(user => {
      setIsSuperadmin(user.is_superadmin || false)
    }).catch(() => {})
  }, [])

  const handleLogout = async () => {
    await authService.logout()
    router.push('/admin/login')
  }

  return (
    <div className="min-h-screen bg-black text-white">
      <nav className="border-b border-white/10 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-8">
              <div
                className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity"
                onClick={() => router.push('/admin/events')}
              >
                <Image src="/favicon-96x96.png" alt="PicUr" width={32} height={32} />
                <span className="text-xl font-bold">PicUr Admin</span>
              </div>
              <div className="hidden md:flex gap-6">
                <a
                  href="/admin/events"
                  className="text-sm font-medium text-gray-300 hover:text-white transition-colors"
                >
                  Events
                </a>
                <a
                  href="/admin/billing"
                  className="text-sm font-medium text-gray-300 hover:text-white transition-colors flex items-center gap-1"
                >
                  <CreditCard className="w-3.5 h-3.5" />
                  Billing
                </a>
                {isSuperadmin && (
                  <a
                    href="/admin/superadmin"
                    className="text-sm font-medium text-purple-400 hover:text-purple-300 transition-colors flex items-center gap-1"
                  >
                    <Shield className="w-3.5 h-3.5" />
                    Superadmin
                  </a>
                )}
              </div>
            </div>

            <div className="flex items-center gap-4">
              <button
                onClick={handleLogout}
                className="hidden md:flex items-center gap-2 text-sm font-medium text-gray-400 hover:text-white transition-colors px-3 py-2 rounded-lg hover:bg-white/5"
              >
                <LogOut className="w-4 h-4" />
                Logout
              </button>
              <button
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                className="md:hidden p-2 text-gray-400 hover:text-white"
              >
                {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
              </button>
            </div>
          </div>

          {/* Mobile menu */}
          {mobileMenuOpen && (
            <div className="md:hidden border-t border-white/10 py-3 space-y-1">
              <a
                href="/admin/events"
                className="block px-3 py-2 text-sm font-medium text-gray-300 hover:text-white hover:bg-white/5 rounded-lg"
              >
                Events
              </a>
              <a
                href="/admin/billing"
                className="flex items-center gap-1 px-3 py-2 text-sm font-medium text-gray-300 hover:text-white hover:bg-white/5 rounded-lg"
              >
                <CreditCard className="w-3.5 h-3.5" />
                Billing
              </a>
              {isSuperadmin && (
                <a
                  href="/admin/superadmin"
                  className="flex items-center gap-1 px-3 py-2 text-sm font-medium text-purple-400 hover:text-purple-300 hover:bg-white/5 rounded-lg"
                >
                  <Shield className="w-3.5 h-3.5" />
                  Superadmin
                </a>
              )}
              <button
                onClick={handleLogout}
                className="flex items-center gap-2 w-full px-3 py-2 text-sm font-medium text-gray-400 hover:text-white hover:bg-white/5 rounded-lg"
              >
                <LogOut className="w-4 h-4" />
                Logout
              </button>
            </div>
          )}
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  )
}
