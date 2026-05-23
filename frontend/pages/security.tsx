import Head from 'next/head'
import Link from 'next/link'
import {
  ShieldCheck,
  Lock,
  Image as ImageIcon,
  ScanFace,
  MapPin,
  Trash2,
  Server,
  EyeOff,
  KeyRound,
  Mail,
  Flag,
  ClipboardCheck,
  AlertTriangle,
} from 'lucide-react'
import { AtelierLayout, ATELIER } from '@/components/atelier'

type Card = {
  icon: typeof ShieldCheck
  title: string
  body: string
}

const TRANSIT_CARDS: Card[] = [
  {
    icon: Lock,
    title: 'Encrypted in transit',
    body: 'Every upload, download, and face scan goes over HTTPS/TLS 1.2+ between your device, Cloudflare, and our servers. Your photos never travel as plain text.',
  },
  {
    icon: Server,
    title: 'Encrypted at rest',
    body: 'Photos and database records sit on disks encrypted at the storage layer. A stolen drive cannot read your photos without the keys held on the running server.',
  },
  {
    icon: KeyRound,
    title: 'Passwords never stored as text',
    body: 'Organizer passwords are hashed with bcrypt before they ever touch the database. Even our team cannot read them.',
  },
]

const PHOTO_CARDS: Card[] = [
  {
    icon: MapPin,
    title: 'Location & camera metadata stripped',
    body: 'Before a photo is stored we wipe its EXIF metadata — GPS coordinates, camera serial number, timestamps. Whatever the original file knew about where or how it was taken, we forget.',
  },
  {
    icon: EyeOff,
    title: 'Photos are private to one event',
    body: 'There is no global gallery. A guest can only see photos by opening the event link the organizer shared with them. Other events are completely walled off — even from our search tools.',
  },
  {
    icon: Trash2,
    title: 'Auto-delete on the schedule you choose',
    body: 'Every event has a retention window (30 days on Free, up to 1 year on Pro, custom on enterprise plans). When the window expires, every photo, thumbnail, and face record is deleted from storage and the database. No archive, no copies.',
  },
]

const FACE_CARDS: Card[] = [
  {
    icon: ScanFace,
    title: 'Face data is math, not photos',
    body: 'For each face we detect, our AI generates a list of numbers — a “face embedding” — that captures what makes that face look like that face. We store the numbers, not a separate photo of the face. The embedding alone cannot be turned back into a human-recognizable image.',
  },
  {
    icon: EyeOff,
    title: 'Guest selfies are processed, not kept',
    body: 'When a guest scans their face, we turn that selfie into a temporary embedding, compare it to the event’s embeddings to find matches, then discard it. The selfie itself is never written to disk.',
  },
  {
    icon: ImageIcon,
    title: 'Face data dies with the event',
    body: 'Face embeddings live exactly as long as the photos they came from. When you delete an event or its retention window expires, every embedding generated from that event is purged from every system that touched it.',
  },
]

const INFRA_CARDS: Card[] = [
  {
    icon: Server,
    title: 'Self-hosted AI — no third-party engine',
    body: 'Face detection and matching run on our own servers using open-source models. Your photos never leave our infrastructure to call out to a third-party AI API. No AWS Rekognition, no Google Vision, no commercial model vendor sees your faces.',
  },
  {
    icon: ShieldCheck,
    title: 'Cloudflare edge protection',
    body: 'All traffic is fronted by Cloudflare — it absorbs denial-of-service attacks, blocks malicious bots, and serves photos through a global cache so your guests get fast loads without our origin servers being directly exposed.',
  },
  {
    icon: KeyRound,
    title: 'Signed download links',
    body: 'When a guest downloads a photo, the URL is signed with a short-lived signature. Even if someone copied that URL, it stops working when the event expires — and it never grants access to any other event’s photos.',
  },
]

const NEVER_DO = [
  'We do not sell or share your photos, face data, or contact details with any third party.',
  'We do not use your photos or face data to train any AI model, ours or anyone else’s.',
  'We do not maintain a global face database across events. Each event is isolated.',
  'We do not allow other organizers, guests, or anonymous internet users to discover your event.',
  'We do not log GPS coordinates from photos — they are stripped before storage.',
  'We do not keep selfies from guest scans. They are deleted as soon as the match is returned.',
]

const REPORT_CARDS: Card[] = [
  {
    icon: Flag,
    title: 'One tap to report',
    body: 'Every guest-viewable photo carries a Report control. Pick a category, leave an optional note, and the report goes straight to our ops queue. Cloudflare Turnstile keeps automated abuse off the form.',
  },
  {
    icon: ClipboardCheck,
    title: 'Reviewed by a human',
    body: 'An operator reviews the report, may view the specific photo, and resolves it as dismissed, quarantined, or removed. Every operator view is recorded in the event’s audit log so the organizer can see when the carve-out was used.',
  },
  {
    icon: AlertTriangle,
    title: 'Removed means gone',
    body: 'When a photo is taken down — by the organizer or by an operator — the bytes and face embeddings are purged immediately. The report row itself stays as an audit trail with its image link nulled out.',
  },
]

function SectionHead({
  num,
  kicker,
  title,
  italicTail,
  blurb,
}: {
  num: string
  kicker: string
  title: string
  italicTail?: string
  blurb: string
}) {
  const t = ATELIER
  return (
    <div style={{ marginBottom: 32 }}>
      <div
        style={{
          fontFamily: t.monoFont,
          fontSize: 11,
          letterSpacing: '0.18em',
          color: t.muted,
          marginBottom: 12,
          textTransform: 'uppercase',
        }}
      >
        SECTION {num} · {kicker}
      </div>
      <h2
        style={{
          fontFamily: t.displayFont,
          fontWeight: 400,
          fontSize: 'clamp(28px, 4vw, 48px)',
          lineHeight: 1.05,
          margin: '0 0 14px',
          letterSpacing: '-0.015em',
        }}
      >
        {title}
        {italicTail && <span style={{ fontStyle: 'italic' }}> {italicTail}</span>}
      </h2>
      <p
        style={{
          fontFamily: t.bodyFont,
          fontSize: 15,
          lineHeight: 1.6,
          color: `${t.ink}aa`,
          maxWidth: 720,
          margin: 0,
        }}
      >
        {blurb}
      </p>
    </div>
  )
}

function CardGrid({ cards }: { cards: Card[] }) {
  const t = ATELIER
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
      {cards.map(({ icon: Icon, title, body }) => (
        <div
          key={title}
          style={{
            padding: '28px',
            background: t.paper,
            border: `1px solid ${t.border}`,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div
            style={{
              width: 40,
              height: 40,
              background: `${t.accent}1a`,
              border: `1px solid ${t.accent}55`,
              color: t.accent,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: 18,
            }}
          >
            <Icon size={18} />
          </div>
          <h3
            style={{
              fontFamily: t.displayFont,
              fontWeight: 400,
              fontStyle: 'italic',
              fontSize: 22,
              margin: '0 0 10px',
              letterSpacing: '-0.01em',
            }}
          >
            {title}
          </h3>
          <p
            style={{
              fontFamily: t.bodyFont,
              fontSize: 14,
              lineHeight: 1.55,
              color: `${t.ink}aa`,
              margin: 0,
            }}
          >
            {body}
          </p>
        </div>
      ))}
    </div>
  )
}

const LIFECYCLE: { title: string; body: string }[] = [
  {
    title: 'Photo uploaded',
    body: 'EXIF metadata is stripped, the file is stored encrypted, a thumbnail is generated, and a background job queues the photo for face indexing.',
  },
  {
    title: 'Faces indexed',
    body: 'Our self-hosted face recognition engine detects each face in the photo and stores a numerical embedding linked to that photo. The original face crop is not kept.',
  },
  {
    title: 'Guest scans',
    body: 'A guest opens the event link, takes a selfie, and we generate a temporary embedding from that selfie. We compare it to embeddings in that event only, return the matches, and discard the selfie.',
  },
  {
    title: 'Photo downloaded',
    body: 'Photos are served through a short-lived signed URL. The URL works for the duration of the event and never points to any other event.',
  },
  {
    title: 'Event ends',
    body: 'When the retention window expires or the organizer deletes the event, every photo, thumbnail, face embedding, and database record tied to that event is purged. There is no backup we keep.',
  },
]

const OPERATOR_ROWS: { icon: typeof EyeOff; title: string; body: React.ReactNode }[] = [
  {
    icon: EyeOff,
    title: 'No customer-photo browser in the app',
    body: (
      <>
        <p>The PicUr admin console only shows event metadata — event name, owner email, photo count, plan. There is no admin feature anywhere in the app that lets staff browse photos from another organizer&apos;s event.</p>
        <p style={{ marginTop: 10 }}><strong>Single exception:</strong> when a user files a written abuse report against a specific photo, an operator can view that one photo to verify the report and decide whether to leave it, quarantine it, or remove it. Every such view is recorded in the event&apos;s own audit log — the audit row names the operator, the photo, the report category, and the reporter context, so an organizer can see every time the carve-out was exercised on their event.</p>
      </>
    ),
  },
  {
    icon: Server,
    title: 'Server access exists, like any cloud service',
    body: <p>A small number of operators have administrative access to the underlying servers and storage — the same way operators of AWS, Google Drive, or any cloud service technically can. We will not pretend this is not true.</p>,
  },
  {
    icon: ShieldCheck,
    title: 'When we actually use that access',
    body: <p>Only to answer your support requests, investigate abuse or security incidents, comply with valid Malaysian legal process, or maintain the service. We do not browse customer events. We do not train AI on your photos. We do not share them with anyone.</p>,
  },
  {
    icon: KeyRound,
    title: 'Audit log',
    body: (
      <p>
        Admin actions through the PicUr console are recorded. You can email{' '}
        <a href="mailto:support@picur.my" style={{ color: ATELIER.accent, borderBottom: `1px solid ${ATELIER.accent}66`, textDecoration: 'none' }}>support@picur.my</a>{' '}
        and ask us to check whether any operator has accessed your event — we will confirm in writing.
      </p>
    ),
  },
]

export default function Security() {
  const t = ATELIER
  return (
    <AtelierLayout>
      <Head>
        <title>Security &amp; Data Handling — PicUr</title>
        <meta
          name="description"
          content="How PicUr stores your photos, handles face recognition data, and protects your event galleries. Encrypted in transit and at rest, self-hosted AI, auto-deletion on schedule."
        />
      </Head>

      <style>{`
        .atelier-sec-h1 { font-size: clamp(40px, 7vw, 88px); line-height: 0.95; letter-spacing: -0.02em; }
      `}</style>

      {/* ========== HERO ========== */}
      <section className="px-6 sm:px-10 lg:px-16 py-16 lg:py-24 text-center">
        <div className="max-w-[1100px] mx-auto">
          <div
            style={{
              display: 'inline-flex',
              width: 60,
              height: 60,
              background: `${t.accent}1a`,
              border: `1px solid ${t.accent}55`,
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: 20,
            }}
          >
            <ShieldCheck size={28} color={t.accent} />
          </div>
          <div
            style={{
              fontFamily: t.monoFont,
              fontSize: 11,
              letterSpacing: '0.22em',
              color: t.accent,
              marginBottom: 16,
              textTransform: 'uppercase',
            }}
          >
            · SECURITY · NO HAND-WAVING
          </div>
          <h1
            className="atelier-sec-h1"
            style={{ fontFamily: t.displayFont, fontWeight: 400, margin: 0 }}
          >
            Your photos. <span style={{ fontStyle: 'italic' }}>Yours alone.</span>
          </h1>
          <p
            className="mx-auto"
            style={{
              fontFamily: t.displayFont,
              fontStyle: 'italic',
              fontSize: 'clamp(18px, 2.2vw, 22px)',
              color: `${t.ink}aa`,
              maxWidth: 620,
              margin: '24px auto 0',
              lineHeight: 1.4,
            }}
          >
            Here is exactly how PicUr stores your photos, what it does with face data, and what happens to it when your event is over.
          </p>
        </div>
      </section>

      {/* ========== ENCRYPTION ========== */}
      <section className="px-6 sm:px-10 lg:px-16 py-12 lg:py-16">
        <div className="max-w-[1280px] mx-auto">
          <SectionHead
            num="I"
            kicker="ENCRYPTION"
            title="Locked from upload"
            italicTail="to download"
            blurb="Everything in motion is encrypted. Everything at rest sits on encrypted storage. No data travels or sits in the clear."
          />
          <CardGrid cards={TRANSIT_CARDS} />
        </div>
      </section>

      {/* ========== PHOTOS ========== */}
      <section className="px-6 sm:px-10 lg:px-16 py-12 lg:py-16">
        <div className="max-w-[1280px] mx-auto">
          <SectionHead
            num="II"
            kicker="HOW PHOTOS ARE STORED"
            title="Private, scrubbed,"
            italicTail="on a timer"
            blurb="Photos uploaded to your event are private to that event, with the camera and GPS fingerprints removed, and they auto-delete when your retention window ends."
          />
          <CardGrid cards={PHOTO_CARDS} />
        </div>
      </section>

      {/* ========== FACE ========== */}
      <section className="px-6 sm:px-10 lg:px-16 py-12 lg:py-16">
        <div className="max-w-[1280px] mx-auto">
          <SectionHead
            num="III"
            kicker="FACE RECOGNITION"
            title="We store math,"
            italicTail="not faces"
            blurb="The AI that matches selfies to event photos works on numerical face embeddings. We never store a separate photo of someone's face, and the embeddings cannot be reversed into a usable image."
          />
          <CardGrid cards={FACE_CARDS} />
        </div>
      </section>

      {/* ========== INFRASTRUCTURE ========== */}
      <section className="px-6 sm:px-10 lg:px-16 py-12 lg:py-16">
        <div className="max-w-[1280px] mx-auto">
          <SectionHead
            num="IV"
            kicker="INFRASTRUCTURE"
            title="Self-hosted AI,"
            italicTail="signed links"
            blurb="No third-party AI vendor sees your photos. Edge protection blocks abuse. Download URLs are signed and expire with the event."
          />
          <CardGrid cards={INFRA_CARDS} />
        </div>
      </section>

      {/* ========== LIFECYCLE ========== */}
      <section
        className="px-6 sm:px-10 lg:px-16 py-16 lg:py-24"
        style={{ background: t.paper }}
      >
        <div className="max-w-[1100px] mx-auto">
          <SectionHead
            num="V"
            kicker="LIFECYCLE"
            title="What happens"
            italicTail="at every stage"
            blurb="From the moment a photo is uploaded to the moment it disappears, here is what is created, used, and destroyed."
          />
          <div style={{ borderTop: `1px solid ${t.ink}` }}>
            {LIFECYCLE.map((step, i) => (
              <div
                key={step.title}
                className="grid grid-cols-[40px_1fr] md:grid-cols-[80px_1fr] gap-4 md:gap-8"
                style={{
                  padding: '24px 0',
                  borderBottom: `1px solid ${t.ink}22`,
                }}
              >
                <div
                  style={{
                    fontFamily: t.monoFont,
                    fontSize: 11,
                    letterSpacing: '0.16em',
                    color: t.accent,
                    paddingTop: 6,
                  }}
                >
                  {String(i + 1).padStart(2, '0')} —
                </div>
                <div>
                  <h3
                    style={{
                      fontFamily: t.displayFont,
                      fontWeight: 400,
                      fontStyle: 'italic',
                      fontSize: 'clamp(22px, 2.4vw, 28px)',
                      margin: '0 0 8px',
                      letterSpacing: '-0.01em',
                    }}
                  >
                    {step.title}
                  </h3>
                  <p
                    style={{
                      fontFamily: t.bodyFont,
                      fontSize: 14.5,
                      lineHeight: 1.55,
                      color: `${t.ink}aa`,
                      margin: 0,
                    }}
                  >
                    {step.body}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ========== OPERATOR ACCESS ========== */}
      <section className="px-6 sm:px-10 lg:px-16 py-16 lg:py-24">
        <div className="max-w-[1100px] mx-auto">
          <SectionHead
            num="VI"
            kicker="OPERATOR ACCESS"
            title="Who at PicUr can"
            italicTail="technically see your data"
            blurb="Total honesty: a small operator team maintains the servers your photos run on. Pretending otherwise would be dishonest. Here is exactly what that means and what we do with that access."
          />
          <div
            style={{
              padding: '32px',
              background: t.paper,
              border: `1px solid ${t.border}`,
              display: 'flex',
              flexDirection: 'column',
              gap: 24,
            }}
          >
            {OPERATOR_ROWS.map(({ icon: Icon, title, body }) => (
              <div key={title} className="grid grid-cols-[44px_1fr] gap-4">
                <div
                  style={{
                    width: 40,
                    height: 40,
                    background: `${t.accent}1a`,
                    border: `1px solid ${t.accent}55`,
                    color: t.accent,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Icon size={18} />
                </div>
                <div
                  style={{
                    fontFamily: t.bodyFont,
                    fontSize: 14.5,
                    lineHeight: 1.55,
                    color: `${t.ink}cc`,
                  }}
                >
                  <div
                    style={{
                      fontFamily: t.displayFont,
                      fontStyle: 'italic',
                      fontSize: 20,
                      color: t.ink,
                      marginBottom: 6,
                    }}
                  >
                    {title}
                  </div>
                  {body}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ========== WHAT WE DO NOT DO ========== */}
      <section
        className="px-6 sm:px-10 lg:px-16 py-16 lg:py-24"
        style={{ background: t.ink, color: t.paper }}
      >
        <div className="max-w-[1100px] mx-auto">
          <div
            style={{
              fontFamily: t.monoFont,
              fontSize: 11,
              letterSpacing: '0.18em',
              color: t.accent,
              marginBottom: 12,
              textTransform: 'uppercase',
            }}
          >
            SECTION VII · WHAT WE DO NOT DO
          </div>
          <h2
            style={{
              fontFamily: t.displayFont,
              fontWeight: 400,
              fontSize: 'clamp(28px, 4vw, 48px)',
              lineHeight: 1.05,
              margin: '0 0 28px',
              letterSpacing: '-0.015em',
            }}
          >
            A short list of things you will{' '}
            <span style={{ fontStyle: 'italic' }}>never find us doing.</span>
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {NEVER_DO.map((line) => (
              <div key={line} className="grid grid-cols-[28px_1fr] gap-3">
                <div
                  style={{
                    width: 22,
                    height: 22,
                    background: `${t.accent}33`,
                    border: `1px solid ${t.accent}88`,
                    color: t.accent,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontFamily: t.bodyFont,
                    fontWeight: 700,
                    fontSize: 14,
                  }}
                >
                  ×
                </div>
                <p
                  style={{
                    fontFamily: t.bodyFont,
                    fontSize: 15,
                    lineHeight: 1.6,
                    color: `${t.paper}cc`,
                    margin: 0,
                  }}
                >
                  {line}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ========== REPORTING ABUSE ========== */}
      <section className="px-6 sm:px-10 lg:px-16 py-16 lg:py-24">
        <div className="max-w-[1280px] mx-auto">
          <SectionHead
            num="VIII"
            kicker="REPORTING ABUSE"
            title="A Report button"
            italicTail="on every photo"
            blurb="If a photo shouldn't be in an event gallery — non-consensual, minor pictured, harassment, copyright — anyone who can see it can flag it. No PicUr account required."
          />
          <CardGrid cards={REPORT_CARDS} />
        </div>
      </section>

      {/* ========== CONTACT CTA ========== */}
      <section className="px-6 sm:px-10 lg:px-16 pb-20 lg:pb-28">
        <div
          className="max-w-[1100px] mx-auto"
          style={{
            padding: '40px',
            background: t.paper,
            border: `1px solid ${t.ink}`,
            textAlign: 'center',
          }}
        >
          <h2
            style={{
              fontFamily: t.displayFont,
              fontWeight: 400,
              fontSize: 'clamp(28px, 4vw, 40px)',
              margin: '0 0 12px',
              letterSpacing: '-0.015em',
            }}
          >
            Found something that <span style={{ fontStyle: 'italic' }}>worries you?</span>
          </h2>
          <p
            style={{
              fontFamily: t.bodyFont,
              fontSize: 15,
              lineHeight: 1.6,
              color: `${t.ink}aa`,
              maxWidth: 560,
              margin: '0 auto 24px',
            }}
          >
            If you spot a security issue, or you want to delete an event, ask about a photo, or exercise any of your rights under our{' '}
            <Link
              href="/privacy"
              style={{
                color: t.accent,
                borderBottom: `1px solid ${t.accent}66`,
                textDecoration: 'none',
              }}
            >
              Privacy Policy
            </Link>
            , email us. We respond personally.
          </p>
          <a
            href="mailto:support@picur.my?subject=Security%20question"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '14px 22px',
              background: t.ink,
              color: t.paper,
              fontFamily: t.bodyFont,
              fontWeight: 600,
              fontSize: 14,
              textDecoration: 'none',
            }}
          >
            <Mail size={16} />
            support@picur.my
          </a>
        </div>
      </section>
    </AtelierLayout>
  )
}
