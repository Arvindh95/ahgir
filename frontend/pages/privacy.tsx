import Head from 'next/head'
import PublicLayout from '@/components/PublicLayout'

export default function PrivacyPolicy() {
  return (
    <PublicLayout>
      <Head>
        <meta name="description" content="PicUr Privacy Policy - How we handle your data, face recognition information, and your rights under PDPA." />
      </Head>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16 md:py-24">
        <h1 className="text-3xl md:text-4xl font-bold mb-2">Privacy Policy</h1>
        <p className="text-gray-500 text-sm mb-12">Last updated: February 2026</p>

        <div className="space-y-10 text-gray-300 leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold text-white mb-3">1. Introduction</h2>
            <p>
              PicUr (&quot;we&quot;, &quot;us&quot;, or &quot;our&quot;) operates the PicUr platform at picur.my. PicUr is an AI-powered photo sharing service designed for events. We use face recognition technology to help event guests find photos of themselves from event galleries.
            </p>
            <p className="mt-3">
              This Privacy Policy explains how we collect, use, store, and protect your personal data in compliance with the Malaysian Personal Data Protection Act 2010 (PDPA).
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">2. Information We Collect</h2>
            <p className="mb-3">We collect the following types of information:</p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><span className="text-white font-medium">Account Information:</span> Email address and encrypted password when you register as an event organizer.</li>
              <li><span className="text-white font-medium">Event Data:</span> Event names, dates, settings, and passcodes created by organizers.</li>
              <li><span className="text-white font-medium">Photos:</span> Images uploaded by event organizers to their event galleries.</li>
              <li><span className="text-white font-medium">Face Recognition Data:</span> Facial feature vectors (mathematical representations) generated from uploaded photos and guest selfie scans. These are not actual images of faces but numerical data used for matching.</li>
              <li><span className="text-white font-medium">Usage Data:</span> Scan counts, download counts, and basic service usage analytics.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">3. Face Recognition Data</h2>
            <p className="mb-3">
              PicUr uses face recognition technology to match guest selfies with photos in event galleries. We want to be transparent about how this works:
            </p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li>When photos are uploaded, our system detects faces and generates mathematical facial feature vectors (embeddings).</li>
              <li>When a guest takes a selfie scan, a temporary facial vector is generated and compared against the indexed vectors to find matches.</li>
              <li>Selfie scan data is processed in real-time and is <span className="text-white font-medium">not permanently stored</span>.</li>
              <li>Facial vectors from uploaded photos are stored only for the duration needed to provide the matching service.</li>
              <li>Face recognition processing is performed on our self-hosted infrastructure. Face data is <span className="text-white font-medium">never sold, shared with, or transferred to third parties</span>.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">4. How We Use Your Information</h2>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li>To provide the PicUr service: photo hosting, face matching, and photo delivery.</li>
              <li>To authenticate and manage your account.</li>
              <li>To send transactional emails (account verification, password resets).</li>
              <li>To improve our service and fix technical issues.</li>
              <li>To enforce our Terms of Service.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">5. Consent</h2>
            <p className="mb-3">
              By creating an account and using PicUr, you consent to the processing of your personal data as described in this policy.
            </p>
            <p className="mb-3">
              <span className="text-white font-medium">Event Organizers:</span> By uploading photos to PicUr, you confirm that you have the right to share those photos and that you will inform your event guests that face recognition technology will be used for photo matching.
            </p>
            <p>
              <span className="text-white font-medium">Event Guests:</span> By using the face scan feature, you consent to the temporary processing of your facial data for the purpose of finding your photos in the event gallery. You may choose not to use the face scan feature and browse the gallery manually instead.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">6. Data Retention</h2>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><span className="text-white font-medium">Account data:</span> Retained until you request account deletion.</li>
              <li><span className="text-white font-medium">Event photos and face data:</span> Retained for the duration of the event. When an event is deleted by the organizer, all associated photos and facial vectors are permanently removed.</li>
              <li><span className="text-white font-medium">Selfie scan data:</span> Processed in real-time and not permanently stored.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">7. Your Rights Under PDPA</h2>
            <p className="mb-3">Under the Malaysian Personal Data Protection Act 2010, you have the right to:</p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><span className="text-white font-medium">Access:</span> Request access to your personal data held by us.</li>
              <li><span className="text-white font-medium">Correction:</span> Request correction of inaccurate personal data.</li>
              <li><span className="text-white font-medium">Deletion:</span> Request deletion of your personal data and account.</li>
              <li><span className="text-white font-medium">Withdraw Consent:</span> Withdraw your consent for data processing at any time.</li>
            </ul>
            <p className="mt-3">
              To exercise any of these rights, please contact us at <a href="mailto:support@picur.my" className="text-blue-400 hover:text-blue-300 underline">support@picur.my</a>.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">8. Data Security</h2>
            <p>
              We implement appropriate technical and organizational measures to protect your personal data, including encrypted data transmission (HTTPS/TLS), secure server infrastructure, access controls, and encrypted password storage. While we strive to protect your data, no method of transmission over the internet is 100% secure.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">9. Third-Party Services</h2>
            <p>
              PicUr uses self-hosted infrastructure for all core services including photo storage and face recognition processing. Your face data and photos are processed entirely on our own servers and are not sent to external third-party AI services. We use Brevo for transactional email delivery (account verification and password reset emails only).
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">10. Changes to This Policy</h2>
            <p>
              We may update this Privacy Policy from time to time. We will notify registered users of significant changes via email. Continued use of PicUr after changes constitutes acceptance of the updated policy.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">11. Contact Us</h2>
            <p>
              If you have any questions about this Privacy Policy or our data practices, please contact us at:
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
