import Head from 'next/head'
import { Mail, Clock } from 'lucide-react'
import PublicLayout from '@/components/PublicLayout'
import { FadeIn } from '@/components/FadeIn'

export default function Contact() {
  return (
    <PublicLayout>
      <Head>
        <title>Contact PicUr - Get in Touch</title>
        <meta name="description" content="Contact PicUr - Get in touch with our team for questions, feedback, or support." />
      </Head>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 md:py-24">
        <FadeIn>
          <div className="text-center mb-16">
            <h1 className="text-3xl md:text-5xl font-bold mb-6 tracking-tight">Get in Touch</h1>
            <p className="text-gray-400 text-xl max-w-xl mx-auto font-light">
              Have questions, feedback, or need support? We&apos;d love to hear from you.
            </p>
          </div>
        </FadeIn>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 md:gap-16 max-w-6xl mx-auto">
          {/* About */}
          <FadeIn delay={0.2}>
            <div>
              <h2 className="text-2xl font-bold mb-6">About PicUr</h2>
              <div className="space-y-4 text-gray-300 leading-relaxed font-light text-lg">
                <p>
                  PicUr is an AI-powered photo sharing platform built for events. Whether it&apos;s a wedding, corporate event, birthday party, or conference — we make it effortless for guests to find and download their photos.
                </p>
                <p>
                  Simply upload your event photos, share a link with your guests, and let our face recognition technology do the rest. Guests take a quick selfie and instantly find all their photos from the event.
                </p>
                <p>
                  Built with privacy in mind. All face recognition processing happens on our own secure servers. Face data is never shared with third parties.
                </p>
              </div>
            </div>
          </FadeIn>

          {/* Contact Card */}
          <FadeIn delay={0.4}>
            <div className="glass-card rounded-3xl p-8 md:p-10 border border-white/10">
              <h2 className="text-xl font-bold mb-8">Contact Us</h2>

              <div className="space-y-8">
                <div className="flex items-start gap-5">
                  <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center flex-shrink-0">
                    <Mail className="w-6 h-6 text-blue-400" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-white mb-1">Email</h3>
                    <a
                      href="mailto:support@picur.my"
                      className="text-blue-400 hover:text-blue-300 transition-colors text-lg"
                    >
                      support@picur.my
                    </a>
                    <p className="text-gray-500 text-sm mt-1">For general inquiries and support</p>
                  </div>
                </div>

                <div className="flex items-start gap-5">
                  <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center flex-shrink-0">
                    <Clock className="w-6 h-6 text-blue-400" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-white mb-1">Response Time</h3>
                    <p className="text-gray-300">Within 24 hours</p>
                    <p className="text-gray-500 text-sm mt-1">We typically respond much faster</p>
                  </div>
                </div>

              </div>

              <div className="mt-10 pt-8 border-t border-white/10">
                <a
                  href="mailto:support@picur.my"
                  className="inline-flex items-center justify-center gap-2 w-full bg-white text-black font-semibold py-4 rounded-xl hover:bg-gray-100 transition-all active:scale-[0.98] text-lg"
                >
                  <Mail className="w-5 h-5" />
                  Send us an Email
                </a>
              </div>
            </div>
          </FadeIn>
        </div>
      </div>
    </PublicLayout>
  )
}
