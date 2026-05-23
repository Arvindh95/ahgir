import Head from 'next/head'
import { LumiereLayout, LUMIERE } from '@/components/lumiere'

export default function PrivacyPolicy() {
  const t = LUMIERE

  return (
    <LumiereLayout>
      <Head>
        <meta
          name="description"
          content="PicUr Privacy Policy — how we handle your data, face recognition information, and your rights under PDPA."
        />
      </Head>

      <style>{`
        .lumiere-legal-h1 { font-size: clamp(40px, 7vw, 88px); line-height: 0.95; letter-spacing: -0.02em; }
        .lumiere-legal h2 {
          font-family: var(--font-display);
          font-weight: 400;
          font-size: clamp(24px, 2.6vw, 30px);
          letter-spacing: -0.01em;
          margin: 0 0 14px;
          color: ${t.ink};
        }
        .lumiere-legal h2 .num {
          font-family: var(--font-mono);
          font-style: normal;
          font-size: 11px;
          letter-spacing: 0.22em;
          color: ${t.accent};
          margin-right: 12px;
          vertical-align: 0.25em;
        }
        .lumiere-legal p { margin: 0 0 14px; }
        .lumiere-legal ul {
          list-style: none;
          padding: 0;
          margin: 0 0 14px;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .lumiere-legal li {
          padding-left: 18px;
          position: relative;
        }
        .lumiere-legal li::before {
          content: '';
          position: absolute;
          left: 0;
          top: 10px;
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: ${t.accent};
        }
        .lumiere-legal a {
          color: ${t.accent};
          text-decoration: none;
          border-bottom: 1px solid ${t.accent}55;
        }
        .lumiere-legal strong {
          color: ${t.ink};
          font-weight: 600;
        }
      `}</style>

      <section className="px-6 sm:px-10 lg:px-14 py-16 lg:py-20">
        <div className="max-w-[860px] mx-auto">
          <div
            style={{
              fontFamily: t.monoFont,
              fontSize: 11,
              letterSpacing: '0.26em',
              color: t.accent,
              marginBottom: 16,
              textTransform: 'uppercase',
            }}
          >
            — LEGAL · LAST UPDATED MAY 2026 —
          </div>
          <h1
            className="lumiere-legal-h1"
            style={{ fontFamily: t.displayFont, fontWeight: 400, margin: 0, color: t.ink }}
          >
            Privacy <span style={{ fontStyle: 'italic', color: t.accent }}>policy.</span>
          </h1>
        </div>
      </section>

      <section className="px-6 sm:px-10 lg:px-14 pb-20 lg:pb-28">
        <div
          className="lumiere-legal max-w-[860px] mx-auto"
          style={{
            fontFamily: t.bodyFont,
            fontSize: 15.5,
            lineHeight: 1.65,
            color: t.inkDim,
            display: 'flex',
            flexDirection: 'column',
            gap: 32,
          }}
        >
          <section>
            <h2><span className="num">01</span>Introduction</h2>
            <p>
              PicUr (&quot;we&quot;, &quot;us&quot;, or &quot;our&quot;) operates the PicUr platform at picur.my. PicUr is an AI-powered photo sharing service designed for events. We use face recognition technology to help event guests find photos of themselves from event galleries.
            </p>
            <p>
              This Privacy Policy explains how we collect, use, store, and protect your personal data in compliance with the Malaysian Personal Data Protection Act 2010 (PDPA). For a plain-English explanation of the technical safeguards behind these promises, see our <a href="/security">Security &amp; Data Handling page</a>.
            </p>
          </section>

          <section>
            <h2><span className="num">02</span>Information we collect</h2>
            <p>We collect the following types of information:</p>
            <ul>
              <li><strong>Account information:</strong> Email address and encrypted password when you register as an event organizer.</li>
              <li><strong>Event data:</strong> Event names, dates, settings, and passcodes created by organizers.</li>
              <li><strong>Photos:</strong> Images uploaded by event organizers to their event galleries. EXIF metadata (including GPS coordinates, camera serial number, and capture timestamps) is stripped before storage.</li>
              <li><strong>Face recognition data:</strong> Facial feature vectors (mathematical representations) generated from uploaded photos and guest selfie scans. These are not actual images of faces but numerical data used for matching.</li>
              <li><strong>Usage data:</strong> Scan counts, download counts, and basic service usage analytics.</li>
              <li><strong>Payment data:</strong> If you subscribe to a paid plan or buy a one-time event package, your payment is processed by Stripe. We receive a Stripe customer ID, subscription status, and invoice metadata — we do not see or store your full card number.</li>
              <li><strong>Abuse report data:</strong> When a user submits an abuse report against a photo, we record the report category, the optional reason text, the reporter&apos;s email (if provided), the reporter&apos;s IP address, and a Cloudflare Turnstile token. This data is used to verify the report and to detect abuse-report spam.</li>
            </ul>
          </section>

          <section>
            <h2><span className="num">03</span>Face recognition data</h2>
            <p>
              PicUr uses face recognition technology to match guest selfies with photos in event galleries. We want to be transparent about how this works:
            </p>
            <ul>
              <li>When photos are uploaded, our system detects faces and generates mathematical facial feature vectors (embeddings).</li>
              <li>When a guest takes a selfie scan, a temporary facial vector is generated and compared against the indexed vectors to find matches.</li>
              <li>Selfie scan data is processed in real-time and is <strong>not permanently stored</strong>.</li>
              <li>Facial vectors from uploaded photos are stored only for the duration needed to provide the matching service.</li>
              <li>Face recognition processing is performed on our self-hosted infrastructure. Face data is <strong>never sold, shared with, or transferred to third parties</strong>.</li>
            </ul>
          </section>

          <section>
            <h2><span className="num">04</span>How we use your information</h2>
            <ul>
              <li>To provide the PicUr service: photo hosting, face matching, and photo delivery.</li>
              <li>To authenticate and manage your account.</li>
              <li>To send transactional emails (account verification, password resets).</li>
              <li>To improve our service and fix technical issues.</li>
              <li>To enforce our Terms of Service.</li>
            </ul>
          </section>

          <section>
            <h2><span className="num">05</span>Consent</h2>
            <p>
              By creating an account and using PicUr, you consent to the processing of your personal data as described in this policy.
            </p>
            <p>
              <strong>Event organizers:</strong> By uploading photos to PicUr, you confirm that you have the right to share those photos and that you will inform your event guests that face recognition technology will be used for photo matching.
            </p>
            <p>
              <strong>Event guests:</strong> By using the face scan feature, you consent to the temporary processing of your facial data for the purpose of finding your photos in the event gallery. You may choose not to use the face scan feature and browse the gallery manually instead.
            </p>
          </section>

          <section>
            <h2><span className="num">06</span>Data retention</h2>
            <ul>
              <li><strong>Account data:</strong> Retained until you request account deletion.</li>
              <li><strong>Event photos and face data:</strong> Retained for the retention window of the event&apos;s plan — 30 days on Free, 6 months on Starter, 1 year on Pro, and a custom window on enterprise / one-time event packages. When the window expires or the organizer deletes the event, all associated photos, thumbnails, and facial vectors are immediately removed from active storage, the face recognition engine, and the database. Encrypted operational backups containing this data roll off on a 7-day rotation, after which it is permanently gone.</li>
              <li><strong>Selfie scan data:</strong> Processed in real-time and not permanently stored.</li>
              <li><strong>Payment history:</strong> Stripe customer IDs and invoice records are retained for accounting and tax purposes as required by Malaysian law.</li>
              <li><strong>Abuse report rows:</strong> When a reported photo is deleted (by the organizer or by our operator after review), the photo bytes and face data are purged immediately, but the abuse report row itself is preserved with its image link nulled out. The row keeps the category, reason text, reporter contact, and review decision so we have an audit trail of every takedown action. Report rows roll off with the event when the event is deleted.</li>
            </ul>
          </section>

          <section>
            <h2><span className="num">07</span>Your rights under PDPA</h2>
            <p>Under the Malaysian Personal Data Protection Act 2010, you have the right to:</p>
            <ul>
              <li><strong>Access:</strong> Request access to your personal data held by us.</li>
              <li><strong>Correction:</strong> Request correction of inaccurate personal data.</li>
              <li><strong>Deletion:</strong> Request deletion of your personal data and account.</li>
              <li><strong>Withdraw consent:</strong> Withdraw your consent for data processing at any time.</li>
            </ul>
            <p>
              To exercise any of these rights, please contact us at <a href="mailto:support@picur.my">support@picur.my</a>.
            </p>
          </section>

          <section>
            <h2><span className="num">08</span>Data security</h2>
            <p>
              We implement appropriate technical and organizational measures to protect your personal data: HTTPS/TLS 1.2+ on all traffic, Cloudflare edge protection in front of our origin, encrypted server storage, bcrypt-hashed passwords, short-lived signed URLs for photo downloads, and per-event access isolation. A full breakdown is on our <a href="/security">Security &amp; Data Handling page</a>. While we strive to protect your data, no method of transmission over the internet is 100% secure.
            </p>
          </section>

          <section>
            <h2><span className="num">09</span>Operator access</h2>
            <p>
              PicUr is operated by a small team. Our systems run on infrastructure we maintain, which means a limited number of staff have administrative access to the underlying servers, databases, and object storage where your photos live. We want to be transparent about this rather than imply otherwise:
            </p>
            <ul>
              <li><strong>In-app:</strong> The PicUr admin console exposes only event metadata (event name, owner email, photo count, plan information) to authorized superadmin accounts. There is no in-app feature to view or download photos from another organizer&apos;s event.</li>
              <li><strong>Infrastructure-level:</strong> Authorized operators technically have the ability to access photos and face data directly on the servers, the same way operators of any cloud service can.</li>
              <li><strong>When we actually access your data:</strong> only to respond to your own support requests, to investigate abuse or security incidents, to comply with valid Malaysian legal process, or to perform necessary maintenance. We do not routinely browse customer events.</li>
              <li><strong>Abuse review carve-out:</strong> when a user files a written abuse report against a specific photo, an operator may view that specific photo to verify the report and decide whether to leave it, quarantine it, or remove it. Every such view is recorded in the event&apos;s own audit log — the audit row names the operator, the photo, the report category, and the reporter context, so an organizer can see every time the carve-out was exercised on their event.</li>
              <li><strong>Audit:</strong> administrative actions performed through the PicUr admin console are recorded in our audit log.</li>
              <li><strong>Vendors:</strong> we never grant administrative access to third-party AI vendors, marketers, or data brokers.</li>
            </ul>
            <p>
              If you would like a written attestation that no operator has accessed your event, contact us at <a href="mailto:support@picur.my">support@picur.my</a> and we will check the audit log and confirm.
            </p>
          </section>

          <section>
            <h2><span className="num">10</span>Third-party services</h2>
            <p>
              PicUr uses self-hosted infrastructure for all core services including photo storage and face recognition processing. Your face data and photos are processed entirely on our own servers and are not sent to external third-party AI services such as AWS Rekognition or Google Vision.
            </p>
            <p>The third parties we do rely on are limited to:</p>
            <ul>
              <li><strong>Cloudflare</strong> — DNS, edge proxy, DDoS protection, and TLS termination for picur.my.</li>
              <li><strong>Stripe</strong> — payment processing for subscriptions and one-time event packages. Stripe handles your card data under their own privacy policy.</li>
              <li><strong>Brevo</strong> — transactional email delivery (account verification and password reset emails only).</li>
            </ul>
          </section>

          <section>
            <h2><span className="num">11</span>Changes to this policy</h2>
            <p>
              We may update this Privacy Policy from time to time. We will notify registered users of significant changes via email. Continued use of PicUr after changes constitutes acceptance of the updated policy.
            </p>
          </section>

          <section>
            <h2><span className="num">12</span>Contact us</h2>
            <p>
              If you have any questions about this Privacy Policy or our data practices, please contact us at <a href="mailto:support@picur.my">support@picur.my</a>.
            </p>
          </section>
        </div>
      </section>
    </LumiereLayout>
  )
}
