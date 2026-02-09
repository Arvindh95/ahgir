import Link from 'next/link'
import Image from 'next/image'
import { Mail } from 'lucide-react'

export default function Footer() {
  return (
    <footer className="border-t border-white/10 bg-black/50 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {/* Brand */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Image src="/favicon-96x96.png" alt="PicUr" width={28} height={28} />
              <span className="text-lg font-bold">PicUr</span>
            </div>
            <p className="text-sm text-gray-400 leading-relaxed">
              AI-powered photo sharing for events. Upload photos, share a link, and let guests find themselves instantly.
            </p>
          </div>

          {/* Product */}
          <div>
            <h4 className="text-sm font-semibold text-white mb-4">Product</h4>
            <ul className="space-y-2">
              <li>
                <Link href="/" className="text-sm text-gray-400 hover:text-white transition-colors">
                  Home
                </Link>
              </li>
              <li>
                <Link href="/admin/register" className="text-sm text-gray-400 hover:text-white transition-colors">
                  Get Started
                </Link>
              </li>
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h4 className="text-sm font-semibold text-white mb-4">Legal</h4>
            <ul className="space-y-2">
              <li>
                <Link href="/privacy" className="text-sm text-gray-400 hover:text-white transition-colors">
                  Privacy Policy
                </Link>
              </li>
              <li>
                <Link href="/terms" className="text-sm text-gray-400 hover:text-white transition-colors">
                  Terms of Service
                </Link>
              </li>
              <li>
                <Link href="/contact" className="text-sm text-gray-400 hover:text-white transition-colors">
                  Contact
                </Link>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom */}
        <div className="mt-10 pt-6 border-t border-white/5 flex flex-col sm:flex-row justify-between items-center gap-4">
          <p className="text-xs text-gray-500">
            &copy; {new Date().getFullYear()} PicUr. All rights reserved.
          </p>
          <a
            href="mailto:support@picur.my"
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors flex items-center gap-1.5"
          >
            <Mail className="w-3.5 h-3.5" />
            support@picur.my
          </a>
        </div>
      </div>
    </footer>
  )
}
