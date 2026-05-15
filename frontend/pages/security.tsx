import Head from 'next/head'
import Link from 'next/link'
import PublicLayout from '@/components/PublicLayout'
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
} from 'lucide-react'

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

function SectionHeading({ kicker, title, blurb }: { kicker: string; title: string; blurb: string }) {
  return (
    <div className="mb-8">
      <div className="text-xs font-bold text-blue-400 tracking-wider mb-2">{kicker}</div>
      <h2 className="text-2xl md:text-3xl font-bold mb-3">{title}</h2>
      <p className="text-gray-400 max-w-2xl">{blurb}</p>
    </div>
  )
}

function CardGrid({ cards }: { cards: Card[] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
      {cards.map(({ icon: Icon, title, body }) => (
        <div key={title} className="glass-card rounded-2xl p-6 flex flex-col">
          <div className="w-10 h-10 rounded-xl bg-blue-500/15 text-blue-300 flex items-center justify-center mb-4">
            <Icon className="w-5 h-5" />
          </div>
          <h3 className="text-base font-semibold mb-2">{title}</h3>
          <p className="text-sm text-gray-400 leading-relaxed">{body}</p>
        </div>
      ))}
    </div>
  )
}

export default function Security() {
  return (
    <PublicLayout>
      <Head>
        <title>Security & Data Handling — PicUr</title>
        <meta
          name="description"
          content="How PicUr stores your photos, handles face recognition data, and protects your event galleries. Encrypted in transit and at rest, self-hosted AI, auto-deletion on schedule."
        />
      </Head>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-16 md:py-24">
        {/* Hero */}
        <div className="text-center mb-16 md:mb-20">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-blue-500/15 text-blue-300 mb-5">
            <ShieldCheck className="w-7 h-7" />
          </div>
          <h1 className="text-3xl md:text-5xl font-bold mb-4">Your photos. Your event. Yours alone.</h1>
          <p className="text-gray-400 text-lg max-w-2xl mx-auto">
            Here is exactly how PicUr stores your photos, what it does with face data, and what happens to it when
            your event is over.
          </p>
        </div>

        {/* Transit + at-rest encryption */}
        <section className="mb-16 md:mb-20">
          <SectionHeading
            kicker="ENCRYPTION"
            title="Locked from upload to download"
            blurb="Everything in motion is encrypted. Everything at rest sits on encrypted storage. No data travels or sits in the clear."
          />
          <CardGrid cards={TRANSIT_CARDS} />
        </section>

        {/* Photo handling */}
        <section className="mb-16 md:mb-20">
          <SectionHeading
            kicker="HOW PHOTOS ARE STORED"
            title="Private to one event, scrubbed of metadata, on a timer"
            blurb="Photos uploaded to your event are private to that event, with the camera and GPS fingerprints removed, and they auto-delete when your retention window ends."
          />
          <CardGrid cards={PHOTO_CARDS} />
        </section>

        {/* Face recognition */}
        <section className="mb-16 md:mb-20">
          <SectionHeading
            kicker="FACE RECOGNITION"
            title="We store math, not faces"
            blurb="The AI that matches selfies to event photos works on numerical face embeddings. We never store a separate photo of someone's face, and the embeddings cannot be reversed into a usable image."
          />
          <CardGrid cards={FACE_CARDS} />
        </section>

        {/* Infrastructure */}
        <section className="mb-16 md:mb-20">
          <SectionHeading
            kicker="INFRASTRUCTURE"
            title="Self-hosted AI, hardened edge, signed links"
            blurb="No third-party AI vendor sees your photos. Edge protection blocks abuse. Download URLs are signed and expire with the event."
          />
          <CardGrid cards={INFRA_CARDS} />
        </section>

        {/* Lifecycle timeline */}
        <section className="mb-16 md:mb-20">
          <SectionHeading
            kicker="LIFECYCLE"
            title="What happens at every stage"
            blurb="From the moment a photo is uploaded to the moment it disappears, here is what is created, used, and destroyed."
          />
          <div className="glass-card rounded-2xl p-6 md:p-8 space-y-4 text-sm md:text-base">
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-500/15 text-blue-300 flex items-center justify-center text-xs font-bold">1</div>
              <div>
                <div className="font-semibold text-white mb-0.5">Photo uploaded</div>
                <p className="text-gray-400">EXIF metadata is stripped, the file is stored encrypted, a thumbnail is generated, and a background job queues the photo for face indexing.</p>
              </div>
            </div>
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-500/15 text-blue-300 flex items-center justify-center text-xs font-bold">2</div>
              <div>
                <div className="font-semibold text-white mb-0.5">Faces indexed</div>
                <p className="text-gray-400">Our self-hosted face recognition engine detects each face in the photo and stores a numerical embedding linked to that photo. The original face crop is not kept.</p>
              </div>
            </div>
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-500/15 text-blue-300 flex items-center justify-center text-xs font-bold">3</div>
              <div>
                <div className="font-semibold text-white mb-0.5">Guest scans</div>
                <p className="text-gray-400">A guest opens the event link, takes a selfie, and we generate a temporary embedding from that selfie. We compare it to embeddings in that event only, return the matches, and discard the selfie.</p>
              </div>
            </div>
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-500/15 text-blue-300 flex items-center justify-center text-xs font-bold">4</div>
              <div>
                <div className="font-semibold text-white mb-0.5">Photo downloaded</div>
                <p className="text-gray-400">Photos are served through a short-lived signed URL. The URL works for the duration of the event and never points to any other event.</p>
              </div>
            </div>
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-500/15 text-blue-300 flex items-center justify-center text-xs font-bold">5</div>
              <div>
                <div className="font-semibold text-white mb-0.5">Event ends</div>
                <p className="text-gray-400">When the retention window expires or the organizer deletes the event, every photo, thumbnail, face embedding, and database record tied to that event is purged. There is no backup we keep.</p>
              </div>
            </div>
          </div>
        </section>

        {/* Operator access */}
        <section className="mb-16 md:mb-20">
          <SectionHeading
            kicker="OPERATOR ACCESS"
            title="Who at PicUr can technically see your data"
            blurb="Total honesty: a small operator team maintains the servers your photos run on. Pretending otherwise would be dishonest. Here is exactly what that means and what we do with that access."
          />
          <div className="glass-card rounded-2xl p-6 md:p-8 space-y-4 text-sm md:text-base">
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-500/15 text-blue-300 flex items-center justify-center"><EyeOff className="w-4 h-4" /></div>
              <div>
                <div className="font-semibold text-white mb-0.5">No customer-photo browser in the app</div>
                <p className="text-gray-400">The PicUr admin console only shows event metadata — event name, owner email, photo count, plan. There is no admin feature anywhere in the app that lets staff browse photos from another organizer&apos;s event.</p>
                <p className="text-gray-400 mt-2"><span className="text-white">Single exception:</span> when a user files a written abuse report against a specific photo, an operator can view that one photo to verify the report and decide whether to leave it, quarantine it, or remove it. Every such view is recorded in the event&apos;s own audit log — the audit row names the operator, the photo, the report category, and the reporter context, so an organizer can see every time the carve-out was exercised on their event.</p>
              </div>
            </div>
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-500/15 text-blue-300 flex items-center justify-center"><Server className="w-4 h-4" /></div>
              <div>
                <div className="font-semibold text-white mb-0.5">Server access exists, like any cloud service</div>
                <p className="text-gray-400">A small number of operators have administrative access to the underlying servers and storage — the same way operators of AWS, Google Drive, or any cloud service technically can. We will not pretend this is not true.</p>
              </div>
            </div>
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-500/15 text-blue-300 flex items-center justify-center"><ShieldCheck className="w-4 h-4" /></div>
              <div>
                <div className="font-semibold text-white mb-0.5">When we actually use that access</div>
                <p className="text-gray-400">Only to answer your support requests, investigate abuse or security incidents, comply with valid Malaysian legal process, or maintain the service. We do not browse customer events. We do not train AI on your photos. We do not share them with anyone.</p>
              </div>
            </div>
            <div className="flex gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-500/15 text-blue-300 flex items-center justify-center"><KeyRound className="w-4 h-4" /></div>
              <div>
                <div className="font-semibold text-white mb-0.5">Audit log</div>
                <p className="text-gray-400">Admin actions through the PicUr console are recorded. You can email <a href="mailto:support@picur.my" className="text-blue-400 hover:text-blue-300 underline">support@picur.my</a> and ask us to check whether any operator has accessed your event — we will confirm in writing.</p>
              </div>
            </div>
          </div>
        </section>

        {/* What we do NOT do */}
        <section className="mb-16 md:mb-20">
          <SectionHeading
            kicker="WHAT WE DO NOT DO"
            title="A short list of things you will never find us doing"
            blurb="The clearest way to explain a privacy posture is to say what is off the table."
          />
          <div className="glass-card rounded-2xl p-6 md:p-8 space-y-3 text-sm md:text-base">
            {[
              'We do not sell or share your photos, face data, or contact details with any third party.',
              'We do not use your photos or face data to train any AI model, ours or anyone else’s.',
              'We do not maintain a global face database across events. Each event is isolated.',
              'We do not allow other organizers, guests, or anonymous internet users to discover your event.',
              'We do not log GPS coordinates from photos — they are stripped before storage.',
              'We do not keep selfies from guest scans. They are deleted as soon as the match is returned.',
            ].map((line) => (
              <div key={line} className="flex gap-3">
                <div className="flex-shrink-0 w-5 h-5 rounded-full bg-red-500/15 text-red-300 flex items-center justify-center text-xs font-bold mt-0.5">×</div>
                <p className="text-gray-300">{line}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Reporting + contact */}
        <section>
          <div className="glass-card rounded-2xl p-8 md:p-10 text-center border border-blue-500/20">
            <h2 className="text-2xl font-bold mb-3">Found something that worries you?</h2>
            <p className="text-gray-400 mb-6 max-w-xl mx-auto">
              If you spot a security issue, or you want to delete an event, ask about a photo, or exercise any of your
              rights under our <Link href="/privacy" className="text-blue-400 hover:text-blue-300 underline">Privacy Policy</Link>,
              email us. We respond personally.
            </p>
            <a
              href="mailto:support@picur.my?subject=Security%20question"
              className="inline-flex items-center gap-2 bg-white text-black px-6 py-3 rounded-xl font-semibold text-sm hover:bg-gray-100 transition-colors"
            >
              <Mail className="w-4 h-4" />
              support@picur.my
            </a>
          </div>
        </section>
      </div>
    </PublicLayout>
  )
}
