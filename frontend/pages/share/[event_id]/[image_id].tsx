import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { Camera, Loader2 } from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface ShareInfo {
  event_name: string
  image_url: string
  thumbnail_url: string
  event_slug: string
}

export default function SharedPhoto() {
  const router = useRouter()
  const { event_id, image_id } = router.query

  const [shareInfo, setShareInfo] = useState<ShareInfo | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!event_id || !image_id) return

    const fetchShareInfo = async () => {
      try {
        const res = await fetch(`${API_URL}/share/${event_id}/${image_id}`)
        if (!res.ok) throw new Error('Photo not found')
        const data = await res.json()
        setShareInfo(data)
      } catch {
        setError('This photo is no longer available.')
      } finally {
        setLoading(false)
      }
    }

    fetchShareInfo()
  }, [event_id, image_id])

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-white animate-spin" />
      </div>
    )
  }

  if (error || !shareInfo) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center text-white">
        <div className="glass-card p-12 rounded-2xl text-center max-w-md">
          <h1 className="text-2xl font-bold mb-4">Photo Unavailable</h1>
          <p className="text-gray-400">{error || 'This photo could not be found.'}</p>
        </div>
      </div>
    )
  }

  return (
    <>
      <Head>
        <title>{shareInfo.event_name} - Shared Photo</title>
        <meta property="og:title" content={`Photo from ${shareInfo.event_name}`} />
        <meta property="og:image" content={shareInfo.thumbnail_url} />
        <meta property="og:type" content="website" />
        <meta property="og:url" content={typeof window !== 'undefined' ? window.location.href : ''} />
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
            <img
              src={shareInfo.image_url}
              alt={`Photo from ${shareInfo.event_name}`}
              className="w-full max-h-[70vh] object-contain"
            />
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
