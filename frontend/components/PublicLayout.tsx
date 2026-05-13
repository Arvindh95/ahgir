import { useState } from 'react'
import { useRouter } from 'next/router'
import Image from 'next/image'
import Link from 'next/link'
import { Menu, X, ArrowRight } from 'lucide-react'
import Footer from './Footer'

interface PublicLayoutProps {
  children: React.ReactNode
}

export default function PublicLayout({ children }: PublicLayoutProps) {
  const router = useRouter()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  return (
    <div className="min-h-screen bg-black text-white flex flex-col overflow-x-clip">
      {/* Navbar */}
      <nav className="border-b border-white/10 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-8">
              <Link
                href="/"
                className="flex items-center gap-2 hover:opacity-80 transition-opacity"
              >
                <Image src="/favicon-96x96.png" alt="PicUr" width={32} height={32} />
                <span className="text-xl font-bold">PicUr</span>
              </Link>
              <div className="hidden md:flex gap-6">
                <Link
                  href="/pricing"
                  className="text-sm font-medium text-gray-300 hover:text-white transition-colors"
                >
                  Pricing
                </Link>
                <Link
                  href="/security"
                  className="text-sm font-medium text-gray-300 hover:text-white transition-colors"
                >
                  Security
                </Link>
                <Link
                  href="/contact"
                  className="text-sm font-medium text-gray-300 hover:text-white transition-colors"
                >
                  About Us & Contact
                </Link>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <Link
                href="/admin/login"
                className="hidden md:inline-flex text-sm font-medium text-gray-300 hover:text-white transition-colors px-3 py-2 rounded-lg hover:bg-white/5"
              >
                Sign In
              </Link>
              <Link
                href="/admin/register"
                className="hidden md:inline-flex items-center gap-2 text-sm font-semibold bg-white text-black px-4 py-2 rounded-xl hover:bg-gray-100 transition-all active:scale-[0.98]"
              >
                Get Started
                <ArrowRight className="w-4 h-4" />
              </Link>
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
              <Link
                href="/pricing"
                className="block px-3 py-2 text-sm font-medium text-gray-300 hover:text-white hover:bg-white/5 rounded-lg"
              >
                Pricing
              </Link>
              <Link
                href="/security"
                className="block px-3 py-2 text-sm font-medium text-gray-300 hover:text-white hover:bg-white/5 rounded-lg"
              >
                Security
              </Link>
              <Link
                href="/contact"
                className="block px-3 py-2 text-sm font-medium text-gray-300 hover:text-white hover:bg-white/5 rounded-lg"
              >
                About Us & Contact
              </Link>
              <Link
                href="/admin/login"
                className="block px-3 py-2 text-sm font-medium text-gray-300 hover:text-white hover:bg-white/5 rounded-lg"
              >
                Sign In
              </Link>
              <Link
                href="/admin/register"
                className="flex items-center gap-2 px-3 py-2 text-sm font-semibold text-white bg-white/10 hover:bg-white/20 rounded-lg"
              >
                Get Started
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          )}
        </div>
      </nav>

      {/* Page content */}
      <main className="flex-1">{children}</main>

      {/* Footer */}
      <Footer />
    </div>
  )
}
