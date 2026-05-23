import Head from 'next/head'
import { LumiereLayout, LUMIERE } from '@/components/lumiere'

export default function TermsOfService() {
  const t = LUMIERE

  return (
    <LumiereLayout>
      <Head>
        <meta
          name="description"
          content="PicUr Terms of Service — rules and guidelines for using our AI-powered photo sharing platform."
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
            Terms of <span style={{ fontStyle: 'italic', color: t.accent }}>service.</span>
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
            <h2><span className="num">01</span>Acceptance of terms</h2>
            <p>
              By accessing or using PicUr (picur.my), you agree to be bound by these Terms of Service. If you do not agree to these terms, please do not use our service. These terms apply to all users, including event organizers, event guests, and visitors.
            </p>
          </section>

          <section>
            <h2><span className="num">02</span>Description of service</h2>
            <p>
              PicUr is an AI-powered photo sharing platform designed for events. Event organizers can upload photos to a private gallery, and event guests can use face recognition technology to find photos of themselves by taking a selfie. The service includes photo hosting, AI-based face matching, photo sharing, and photo downloading capabilities.
            </p>
          </section>

          <section>
            <h2><span className="num">03</span>Account registration</h2>
            <p>To use PicUr as an event organizer, you must:</p>
            <ul>
              <li>Provide a valid email address and create a password.</li>
              <li>Verify your email address through the verification process.</li>
              <li>Provide accurate and truthful information.</li>
              <li>Maintain the security of your account credentials.</li>
            </ul>
            <p>
              You are responsible for all activity that occurs under your account. Notify us immediately if you suspect unauthorized access to your account.
            </p>
          </section>

          <section>
            <h2><span className="num">04</span>Acceptable use</h2>
            <p>You agree not to:</p>
            <ul>
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
            <h2><span className="num">05</span>Face recognition consent</h2>
            <p>PicUr uses AI-powered face recognition technology. By using this service:</p>
            <ul>
              <li><strong>Event organizers</strong> consent to the processing of faces detected in uploaded photos and accept responsibility for informing their event guests that face recognition will be used.</li>
              <li><strong>Event guests</strong> consent to the temporary processing of their facial data when using the scan feature. Guest face scan data is not permanently stored.</li>
            </ul>
            <p>
              Guests who do not wish to use face recognition may browse the event gallery manually where available. For a detailed explanation of how face data is processed and protected, see our <a href="/security">Security &amp; Data Handling page</a>.
            </p>
            <p>
              <strong>Accuracy:</strong> face recognition is statistical and is not guaranteed to be 100% accurate. Variations in lighting, angle, expression, occlusion (sunglasses, masks, partial faces), and image quality can cause valid matches to be missed or, less commonly, cause a lookalike to be returned. PicUr tunes for high accuracy but provides no warranty that every photo of a given person will be matched.
            </p>
          </section>

          <section>
            <h2><span className="num">06</span>Plans, billing &amp; refunds</h2>
            <p>
              PicUr offers a free tier and paid subscriptions (Starter, Pro) billed monthly or annually, and one-time event packages by quote. Pricing is published at <a href="/pricing">/pricing</a>. By subscribing you authorize PicUr (through Stripe, our payment processor) to charge the recurring fee on your selected billing cycle.
            </p>
            <ul>
              <li><strong>Cancellation:</strong> You may cancel a subscription at any time from your billing dashboard. Cancellation takes effect at the end of the current billing period; events remain accessible until then.</li>
              <li><strong>Refunds:</strong> Monthly subscriptions are non-refundable. Annual subscriptions may be refunded on a prorated basis within 14 days of purchase if the service has not been substantively used. One-time event packages are non-refundable once the event has been activated.</li>
              <li><strong>Failed payments:</strong> If a payment fails, your subscription enters a grace period. If the issue is not resolved, the account is downgraded to Free and excess events may be frozen until the subscription is restored.</li>
              <li><strong>Beta period:</strong> During beta we may waive subscription fees in exchange for product feedback. Beta arrangements are by individual agreement and do not establish ongoing free service.</li>
            </ul>
          </section>

          <section>
            <h2><span className="num">07</span>Intellectual property</h2>
            <p>
              <strong>Your content:</strong> You retain full ownership of all photos and content you upload to PicUr. By uploading content, you grant PicUr a limited, non-exclusive license to store, process, and display your content solely for the purpose of providing the service.
            </p>
            <p>
              <strong>Our service:</strong> PicUr, including its design, features, code, and branding, is owned by PicUr. You may not copy, modify, distribute, or create derivative works of our service without permission.
            </p>
          </section>

          <section>
            <h2><span className="num">08</span>Data ownership</h2>
            <p>
              Users own their personal data and uploaded content. PicUr acts as a data processor on behalf of event organizers. When an organizer deletes an event, all associated data (photos, face recognition data) is immediately removed from active systems; encrypted operational backups retain a copy for up to 7 days before they too are rotated out.
            </p>
          </section>

          <section>
            <h2><span className="num">09</span>Service availability</h2>
            <p>
              We strive to maintain high availability of our service but do not guarantee uninterrupted access. PicUr may experience downtime for maintenance, updates, or unforeseen technical issues. We will make reasonable efforts to notify users of planned maintenance in advance.
            </p>
          </section>

          <section>
            <h2><span className="num">10</span>Limitation of liability</h2>
            <p>
              To the maximum extent permitted by law, PicUr shall not be liable for any indirect, incidental, special, consequential, or punitive damages arising from your use of the service. This includes, but is not limited to, loss of data, loss of profits, or business interruption. Our total liability for any claim shall not exceed the amount you paid to PicUr in the 12 months preceding the claim.
            </p>
          </section>

          <section>
            <h2><span className="num">11</span>Termination</h2>
            <p>Either party may terminate the relationship at any time:</p>
            <ul>
              <li><strong>By you:</strong> You may delete your account at any time. Upon deletion, your events, photos, and associated data are immediately removed from active systems; encrypted backups roll off within 7 days.</li>
              <li><strong>By us:</strong> We may suspend or terminate your account if you violate these terms, with notice where practicable.</li>
            </ul>
          </section>

          <section>
            <h2><span className="num">12</span>Governing law</h2>
            <p>
              These Terms of Service are governed by and construed in accordance with the laws of Malaysia. Any disputes arising from these terms shall be subject to the exclusive jurisdiction of the courts of Malaysia.
            </p>
          </section>

          <section>
            <h2><span className="num">13</span>Reporting abuse &amp; takedown</h2>
            <p>
              Every event photo viewable by a guest carries a <strong>Report</strong> control. Anyone who can see a photo can flag it — no PicUr account required. The form collects a category (non-consensual content, minor in photo, harassment, copyright, other), an optional reason, and an optional contact email. Submissions are protected by Cloudflare Turnstile to keep automated abuse off the queue.
            </p>
            <ul>
              <li><strong>Review:</strong> reports land in a queue reviewed by our operations team. An operator may view the specific reported photo to verify the report. Every operator view is recorded in the event&apos;s audit log — the organizer can see exactly when the carve-out was exercised on their event.</li>
              <li><strong>Actions:</strong> after review, a report is resolved as <em>dismissed</em> (no policy violation), <em>quarantined</em> (photo hidden from guests pending further investigation), or <em>removed</em> (photo deleted from storage and the face index). Organizers can also delete a flagged photo themselves; open reports against that photo are auto-closed.</li>
              <li><strong>Good-faith use:</strong> reports must be made in good faith. Mass-flagging, retaliation, or reports submitted to harass an organizer are prohibited and may result in IP rate-limiting or account action.</li>
              <li><strong>Counter-notice:</strong> if your photo was removed and you believe the takedown was incorrect, email <a href="mailto:support@picur.my">support@picur.my</a> with the event link and the photo reference. We will review the operator decision and respond.</li>
              <li><strong>Open reports block deletion:</strong> while an active report (pending, reviewing, or quarantined) exists against a photo, the organizer cannot delete the surrounding event. Resolve the report first by deleting the specific photo, or contact support if you believe the report is in bad faith.</li>
            </ul>
            <p>
              We do not act on reports outside the in-app flow. Email or DM-based takedown requests are routed back through the Report button so they receive the same audit trail. For data subject requests under PDPA, see the <a href="/privacy">Privacy Policy</a>.
            </p>
          </section>

          <section>
            <h2><span className="num">14</span>Contact us</h2>
            <p>
              If you have any questions about these Terms of Service, please contact us at <a href="mailto:support@picur.my">support@picur.my</a>.
            </p>
          </section>
        </div>
      </section>
    </LumiereLayout>
  )
}
