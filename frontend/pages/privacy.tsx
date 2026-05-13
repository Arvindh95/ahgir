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
        <p className="text-gray-500 text-sm mb-12">Last updated: May 2026</p>

        <div className="space-y-10 text-gray-300 leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold text-white mb-3">1. Introduction</h2>
            <p>
              PicUr (&quot;we&quot;, &quot;us&quot;, or &quot;our&quot;) operates the PicUr platform at picur.my. PicUr is an AI-powered photo sharing service designed for events. We use face recognition technology to help event guests find photos of themselves from event galleries.
            </p>
            <p className="mt-3">
              This Privacy Policy explains how we collect, use, store, and protect your personal data in compliance with the Malaysian Personal Data Protection Act 2010 (PDPA). For a plain-English explanation of the technical safeguards behind these promises, see our <a href="/security" className="text-blue-400 hover:text-blue-300 underline">Security &amp; Data Handling page</a>.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">2. Information We Collect</h2>
            <p className="mb-3">We collect the following types of information:</p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><span className="text-white font-medium">Account Information:</span> Email address and encrypted password when you register as an event organizer.</li>
              <li><span className="text-white font-medium">Event Data:</span> Event names, dates, settings, and passcodes created by organizers.</li>
              <li><span className="text-white font-medium">Photos:</span> Images uploaded by event organizers to their event galleries. EXIF metadata (including GPS coordinates, camera serial number, and capture timestamps) is stripped before storage.</li>
              <li><span className="text-white font-medium">Face Recognition Data:</span> Facial feature vectors (mathematical representations) generated from uploaded photos and guest selfie scans. These are not actual images of faces but numerical data used for matching.</li>
              <li><span className="text-white font-medium">Usage Data:</span> Scan counts, download counts, and basic service usage analytics.</li>
              <li><span className="text-white font-medium">Payment Data:</span> If you subscribe to a paid plan or buy a one-time event package, your payment is processed by Stripe. We receive a Stripe customer ID, subscription status, and invoice metadata — we do not see or store your full card number.</li>
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
              <li><span className="text-white font-medium">Event photos and face data:</span> Retained for the retention window of the event&apos;s plan — 30 days on Free, 6 months on Starter, 1 year on Pro, and a custom window on enterprise / one-time event packages. When the window expires or the organizer deletes the event, all associated photos, thumbnails, and facial vectors are permanently removed from storage, the face recognition engine, and the database.</li>
              <li><span className="text-white font-medium">Selfie scan data:</span> Processed in real-time and not permanently stored.</li>
              <li><span className="text-white font-medium">Payment history:</span> Stripe customer IDs and invoice records are retained for accounting and tax purposes as required by Malaysian law.</li>
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
              We implement appropriate technical and organizational measures to protect your personal data: HTTPS/TLS 1.2+ on all traffic, Cloudflare edge protection in front of our origin, encrypted server storage, bcrypt-hashed passwords, short-lived signed URLs for photo downloads, and per-event access isolation. A full breakdown is on our <a href="/security" className="text-blue-400 hover:text-blue-300 underline">Security &amp; Data Handling page</a>. While we strive to protect your data, no method of transmission over the internet is 100% secure.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">9. Operator Access</h2>
            <p className="mb-3">
              PicUr is operated by a small team. Our systems run on infrastructure we maintain, which means a limited number of staff have administrative access to the underlying servers, databases, and object storage where your photos live. We want to be transparent about this rather than imply otherwise:
            </p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><span className="text-white font-medium">In-app:</span> The PicUr admin console exposes only event <em>metadata</em> (event name, owner email, photo count, plan information) to authorized superadmin accounts. There is no in-app feature to view or download photos from another organizer&apos;s event.</li>
              <li><span className="text-white font-medium">Infrastructure-level:</span> Authorized operators technically have the ability to access photos and face data directly on the servers, the same way operators of any cloud service can.</li>
              <li><span className="text-white font-medium">When we actually access your data:</span> only to respond to your own support requests, to investigate abuse or security incidents, to comply with valid Malaysian legal process, or to perform necessary maintenance. We do not routinely browse customer events.</li>
              <li><span className="text-white font-medium">Audit:</span> administrative actions performed through the PicUr admin console are recorded in our audit log.</li>
              <li><span className="text-white font-medium">Vendors:</span> we never grant administrative access to third-party AI vendors, marketers, or data brokers.</li>
            </ul>
            <p className="mt-3">
              If you would like a written attestation that no operator has accessed your event, contact us at <a href="mailto:support@picur.my" className="text-blue-400 hover:text-blue-300 underline">support@picur.my</a> and we will check the audit log and confirm.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">10. Third-Party Services</h2>
            <p className="mb-3">
              PicUr uses self-hosted infrastructure for all core services including photo storage and face recognition processing. Your face data and photos are processed entirely on our own servers and are not sent to external third-party AI services such as AWS Rekognition or Google Vision.
            </p>
            <p className="mb-3">The third parties we do rely on are limited to:</p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><span className="text-white font-medium">Cloudflare</span> — DNS, edge proxy, DDoS protection, and TLS termination for picur.my.</li>
              <li><span className="text-white font-medium">Stripe</span> — payment processing for subscriptions and one-time event packages. Stripe handles your card data under their own privacy policy.</li>
              <li><span className="text-white font-medium">Brevo</span> — transactional email delivery (account verification and password reset emails only).</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">11. Changes to This Policy</h2>
            <p>
              We may update this Privacy Policy from time to time. We will notify registered users of significant changes via email. Continued use of PicUr after changes constitutes acceptance of the updated policy.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">12. Contact Us</h2>
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
