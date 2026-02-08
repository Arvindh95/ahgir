import { useRouter } from 'next/router'
import Head from 'next/head'
import Image from 'next/image'
import { Camera } from 'lucide-react'
import { GetServerSideProps } from 'next'

interface ShareInfo {
  event_name: string
  image_url: string
  thumbnail_url: string
  event_slug: string
}

interface SharedPhotoProps {
  shareInfo: ShareInfo | null
  error: boolean
}

export const getServerSideProps: GetServerSideProps<SharedPhotoProps> = async (context) => {
  const { event_id, image_id } = context.params!

  // Use internal Docker URL for server-side fetch, fall back to public URL
  const serverApiUrl = process.env.SERVER_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

  try {
    const res = await fetch(`${serverApiUrl}/share/${event_id}/${image_id}`)
    if (!res.ok) {
      return { props: { shareInfo: null, error: true } }
    }
    const shareInfo: ShareInfo = await res.json()
    return { props: { shareInfo, error: false } }
  } catch {
    return { props: { shareInfo: null, error: true } }
  }
}

export default function SharedPhoto({ shareInfo, error }: SharedPhotoProps) {
  const router = useRouter()

  if (error || !shareInfo) {
    return (
      <>
        <Head>
          <meta name="page-title" content="Photo Unavailable - PicUr" />
        </Head>
        <div className="min-h-screen bg-black flex items-center justify-center text-white">
          <div className="glass-card p-12 rounded-2xl text-center max-w-md">
            <h1 className="text-2xl font-bold mb-4">Photo Unavailable</h1>
            <p className="text-gray-400">This photo could not be found.</p>
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      <Head>
        <meta name="page-title" content={`${shareInfo.event_name} - PicUr`} />
        <meta property="og:title" content={`Photo from ${shareInfo.event_name}`} />
        <meta property="og:image" content={shareInfo.thumbnail_url} />
        <meta property="og:type" content="website" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={`Photo from ${shareInfo.event_name}`} />
        <meta name="twitter:image" content={shareInfo.thumbnail_url} />
      </Head>

      <div className="min-h-screen relative bg-black text-white">
        <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-black via-[#0a0a0a] to-[#050505] z-0 fixed"></div>

        <div className="relative z-10 max-w-4xl mx-auto px-4 py-8 flex flex-col items-center min-h-screen justify-center">
          <h1 className="text-2xl md:text-3xl font-bold mb-2 text-center">{shareInfo.event_name}</h1>
          <p className="text-gray-400 mb-8 text-center">Shared Photo</p>

          <div className="glass-card rounded-2xl overflow-hidden max-w-3xl w-full">
            <div className="relative w-full" style={{ maxHeight: '70vh', aspectRatio: '4/3' }}>
              <Image
                src={shareInfo.image_url}
                alt={`Photo from ${shareInfo.event_name}`}
                fill
                priority
                sizes="100vw"
                className="object-contain"
              />
            </div>
          </div>

          <div className="mt-8">
            <button
              onClick={() => router.push(`/e/${shareInfo.event_slug}`)}
              className="flex items-center gap-3 bg-white text-black px-8 py-3 rounded-xl font-bold hover:bg-gray-200 transition-colors shadow-lg"
            >
              <Camera className="w-5 h-5" />
              Find Your Photos
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
