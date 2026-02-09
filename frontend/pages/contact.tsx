import Head from 'next/head'
import { Mail, MapPin, Clock } from 'lucide-react'
import PublicLayout from '@/components/PublicLayout'

export default function Contact() {
  return (
    <PublicLayout>
      <Head>
        <meta name="description" content="Contact PicUr - Get in touch with our team for questions, feedback, or support." />
      </Head>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 md:py-24">
        <div className="text-center mb-16">
          <h1 className="text-3xl md:text-4xl font-bold mb-4">Get in Touch</h1>
          <p className="text-gray-400 text-lg max-w-xl mx-auto">
            Have questions, feedback, or need support? We&apos;d love to hear from you.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 md:gap-12 max-w-5xl mx-auto">
          {/* About */}
          <div>
            <h2 className="text-2xl font-bold mb-4">About PicUr</h2>
            <p className="text-gray-300 leading-relaxed mb-4">
              PicUr is an AI-powered photo sharing platform built for events. Whether it&apos;s a wedding, corporate event, birthday party, or conference — we make it effortless for guests to find and download their photos.
            </p>
            <p className="text-gray-300 leading-relaxed mb-4">
              Simply upload your event photos, share a link with your guests, and let our face recognition technology do the rest. Guests take a quick selfie and instantly find all their photos from the event.
            </p>
            <p className="text-gray-400 leading-relaxed">
              Built with privacy in mind. All face recognition processing happens on our own secure servers. Face data is never shared with third parties.
            </p>
          </div>

          {/* Contact Card */}
          <div className="glass-card rounded-2xl p-8">
            <h2 className="text-xl font-bold mb-6">Contact Us</h2>

            <div className="space-y-6">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center flex-shrink-0">
                  <Mail className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-white mb-1">Email</h3>
                  <a
                    href="mailto:support@picur.my"
                    className="text-blue-400 hover:text-blue-300 transition-colors"
                  >
                    support@picur.my
                  </a>
                  <p className="text-gray-500 text-sm mt-1">For general inquiries and support</p>
                </div>
              </div>

              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center flex-shrink-0">
                  <Clock className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-white mb-1">Response Time</h3>
                  <p className="text-gray-300">Within 24 hours</p>
                  <p className="text-gray-500 text-sm mt-1">We typically respond much faster</p>
                </div>
              </div>

              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center flex-shrink-0">
                  <MapPin className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-white mb-1">Location</h3>
                  <p className="text-gray-300">Malaysia</p>
                </div>
              </div>
            </div>

            <div className="mt-8 pt-6 border-t border-white/10">
              <a
                href="mailto:support@picur.my"
                className="inline-flex items-center justify-center gap-2 w-full bg-white text-black font-semibold py-3 rounded-xl hover:bg-gray-100 transition-all active:scale-[0.98]"
              >
                <Mail className="w-4 h-4" />
                Send us an Email
              </a>
            </div>
          </div>
        </div>
      </div>
    </PublicLayout>
  )
}
