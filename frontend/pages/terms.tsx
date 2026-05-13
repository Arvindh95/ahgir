import Head from 'next/head'
import PublicLayout from '@/components/PublicLayout'

export default function TermsOfService() {
  return (
    <PublicLayout>
      <Head>
        <meta name="description" content="PicUr Terms of Service - Rules and guidelines for using our AI-powered photo sharing platform." />
      </Head>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16 md:py-24">
        <h1 className="text-3xl md:text-4xl font-bold mb-2">Terms of Service</h1>
        <p className="text-gray-500 text-sm mb-12">Last updated: May 2026</p>

        <div className="space-y-10 text-gray-300 leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold text-white mb-3">1. Acceptance of Terms</h2>
            <p>
              By accessing or using PicUr (picur.my), you agree to be bound by these Terms of Service. If you do not agree to these terms, please do not use our service. These terms apply to all users, including event organizers, event guests, and visitors.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">2. Description of Service</h2>
            <p>
              PicUr is an AI-powered photo sharing platform designed for events. Event organizers can upload photos to a private gallery, and event guests can use face recognition technology to find photos of themselves by taking a selfie. The service includes photo hosting, AI-based face matching, photo sharing, and photo downloading capabilities.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">3. Account Registration</h2>
            <p className="mb-3">To use PicUr as an event organizer, you must:</p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li>Provide a valid email address and create a password.</li>
              <li>Verify your email address through the verification process.</li>
              <li>Provide accurate and truthful information.</li>
              <li>Maintain the security of your account credentials.</li>
            </ul>
            <p className="mt-3">
              You are responsible for all activity that occurs under your account. Notify us immediately if you suspect unauthorized access to your account.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">4. Acceptable Use</h2>
            <p className="mb-3">You agree not to:</p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li>Upload illegal, harmful, or offensive content.</li>
              <li>Upload photos without the right to share them.</li>
              <li>Use the service for harassment, stalking, or any form of abuse.</li>
              <li>Attempt to circumvent security measures or access controls.</li>
              <li>Use automated tools to scrape, download, or extract data from the platform.</li>
              <li>Impersonate another person or entity.</li>
              <li>Use the face recognition feature for surveillance or tracking purposes.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">5. Face Recognition Consent</h2>
            <p className="mb-3">
              PicUr uses AI-powered face recognition technology. By using this service:
            </p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><span className="text-white font-medium">Event Organizers</span> consent to the processing of faces detected in uploaded photos and accept responsibility for informing their event guests that face recognition will be used.</li>
              <li><span className="text-white font-medium">Event Guests</span> consent to the temporary processing of their facial data when using the scan feature. Guest face scan data is not permanently stored.</li>
            </ul>
            <p className="mt-3">
              Guests who do not wish to use face recognition may browse the event gallery manually where available. For a detailed explanation of how face data is processed and protected, see our <a href="/security" className="text-blue-400 hover:text-blue-300 underline">Security &amp; Data Handling page</a>.
            </p>
            <p className="mt-3">
              <span className="text-white font-medium">Accuracy:</span> face recognition is statistical and is not guaranteed to be 100% accurate. Variations in lighting, angle, expression, occlusion (sunglasses, masks, partial faces), and image quality can cause valid matches to be missed or, less commonly, cause a lookalike to be returned. PicUr tunes for high accuracy but provides no warranty that every photo of a given person will be matched. Organizers should consider providing a manual gallery view alongside face scanning so guests can browse for photos they may have missed.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">6. Plans, Billing &amp; Refunds</h2>
            <p className="mb-3">
              PicUr offers a free tier and paid subscriptions (Starter, Pro) billed monthly or annually, and one-time event packages by quote. Pricing is published at <a href="/pricing" className="text-blue-400 hover:text-blue-300 underline">/pricing</a>. By subscribing you authorize PicUr (through Stripe, our payment processor) to charge the recurring fee on your selected billing cycle.
            </p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><span className="text-white font-medium">Cancellation:</span> You may cancel a subscription at any time from your billing dashboard. Cancellation takes effect at the end of the current billing period; events remain accessible until then.</li>
              <li><span className="text-white font-medium">Refunds:</span> Monthly subscriptions are non-refundable. Annual subscriptions may be refunded on a prorated basis within 14 days of purchase if the service has not been substantively used. One-time event packages are non-refundable once the event has been activated.</li>
              <li><span className="text-white font-medium">Failed payments:</span> If a payment fails, your subscription enters a grace period. If the issue is not resolved, the account is downgraded to Free and excess events may be frozen until the subscription is restored.</li>
              <li><span className="text-white font-medium">Beta period:</span> During beta we may waive subscription fees in exchange for product feedback. Beta arrangements are by individual agreement and do not establish ongoing free service.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">7. Intellectual Property</h2>
            <p className="mb-3">
              <span className="text-white font-medium">Your Content:</span> You retain full ownership of all photos and content you upload to PicUr. By uploading content, you grant PicUr a limited, non-exclusive license to store, process, and display your content solely for the purpose of providing the service.
            </p>
            <p>
              <span className="text-white font-medium">Our Service:</span> PicUr, including its design, features, code, and branding, is owned by PicUr. You may not copy, modify, distribute, or create derivative works of our service without permission.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">8. Data Ownership</h2>
            <p>
              Users own their personal data and uploaded content. PicUr acts as a data processor on behalf of event organizers. When an organizer deletes an event, all associated data (photos, face recognition data) is permanently removed from our systems.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">9. Service Availability</h2>
            <p>
              We strive to maintain high availability of our service but do not guarantee uninterrupted access. PicUr may experience downtime for maintenance, updates, or unforeseen technical issues. We will make reasonable efforts to notify users of planned maintenance in advance.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">10. Limitation of Liability</h2>
            <p>
              To the maximum extent permitted by law, PicUr shall not be liable for any indirect, incidental, special, consequential, or punitive damages arising from your use of the service. This includes, but is not limited to, loss of data, loss of profits, or business interruption. Our total liability for any claim shall not exceed the amount you paid to PicUr in the 12 months preceding the claim.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">11. Termination</h2>
            <p className="mb-3">
              Either party may terminate the relationship at any time:
            </p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><span className="text-white font-medium">By you:</span> You may delete your account at any time. Upon deletion, your events, photos, and associated data will be permanently removed.</li>
              <li><span className="text-white font-medium">By us:</span> We may suspend or terminate your account if you violate these terms, with notice where practicable.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">12. Governing Law</h2>
            <p>
              These Terms of Service are governed by and construed in accordance with the laws of Malaysia. Any disputes arising from these terms shall be subject to the exclusive jurisdiction of the courts of Malaysia.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">13. Contact Us</h2>
            <p>
              If you have any questions about these Terms of Service, please contact us at:
            </p>
            <p className="mt-3">
              <a href="mailto:support@picur.my" className="text-blue-400 hover:text-blue-300 underline">support@picur.my</a>
            </p>
          </section>
        </div>
      </div>
    </PublicLayout>
  )
}
