import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import PhotoGridSkeleton from '@/components/skeletons/PhotoGridSkeleton'
import { ArrowLeft, Image as ImageIcon, Loader2, ScanFace } from 'lucide-react'
import PhotoGrid from '@/components/PhotoGrid'
import PhotoModal from '@/components/PhotoModal'
import SelectionToolbar from '@/components/SelectionToolbar'
import { useShare } from '@/components/ShareMenu'
import { usePhotoActions } from '@/hooks/usePhotoActions'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface GalleryPhoto {
  image_id: string
  thumbnail_url: string
  original_url: string
  download_url?: string
  filename: string
  uploaded_at: string
}

export default function Gallery() {
  const router = useRouter()
  const { slug } = router.query

  const [photos, setPhotos] = useState<GalleryPhoto[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [eventName, setEventName] = useState('')
  const [allowDownloads, setAllowDownloads] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)

  const { selectedIds, toggleSelect, selectAll, handleDownload, handleBulkDownload, downloading } = usePhotoActions()
  const { shareMenuPhoto, setShareMenuPhoto, handleShare } = useShare(eventName)

  const fetchGallery = async (pageNum: number, append = false) => {
    const token = localStorage.getItem('event_token')
    if (!token) {
      router.push(`/e/${slug}`)
      return
    }

    try {
      const res = await fetch(`${API_URL}/gallery?page=${pageNum}&limit=24`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.status === 401) {
        localStorage.removeItem('event_token')
        router.push(`/e/${slug}`)
        return
      }
      if (!res.ok) throw new Error('Failed to load gallery')
      const data = await res.json()

      setPhotos(prev => append ? [...prev, ...data.photos] : data.photos)
      setTotal(data.total)
      setEventName(data.event_name)
      setAllowDownloads(data.allow_downloads)
    } catch (err) {
      console.error('Gallery error:', err)
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }

  useEffect(() => {
    if (!slug) return
    const token = localStorage.getItem('event_token')
    if (!token) {
      router.push(`/e/${slug}`)
      return
    }
    fetchGallery(1)
  }, [slug])

  const loadMore = () => {
    const nextPage = page + 1
    setPage(nextPage)
    setLoadingMore(true)
    fetchGallery(nextPage, true)
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-black">
        <div className="max-w-7xl mx-auto px-4 py-8">
          <PhotoGridSkeleton count={12} />
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen relative bg-black text-white">
      <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-black via-[#0a0a0a] to-[#050505] z-0 fixed"></div>

      <div className="relative z-10 max-w-7xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-center gap-4 mb-8 glass-card p-4 rounded-xl">
          <h1 className="text-xl font-bold">{eventName} - Gallery</h1>
          <div className="flex items-center gap-4">
            {localStorage.getItem('scan_results') && (
              <button
                onClick={() => router.push(`/e/${slug}/results`)}
                className="flex items-center gap-2 text-green-400 hover:text-green-300 transition-colors font-medium"
              >
                <ScanFace className="w-5 h-5" />
                My Photos
              </button>
            )}
            <button
              onClick={() => router.push(`/e/${slug}/scan`)}
              className="flex items-center gap-2 text-blue-400 hover:text-blue-300 transition-colors font-medium"
            >
              <ArrowLeft className="w-5 h-5" />
              Back to Scanner
            </button>
          </div>
        </div>

        {photos.length === 0 ? (
          <div className="glass-card p-12 rounded-2xl text-center max-w-2xl mx-auto">
            <div className="w-24 h-24 bg-white/5 rounded-full flex items-center justify-center mx-auto mb-6">
               <ImageIcon className="w-12 h-12 text-gray-500" />
            </div>
            <h2 className="text-2xl font-bold mb-4">No Photos Yet</h2>
            <p className="text-gray-400">Photos will appear here once they have been uploaded and processed.</p>
          </div>
        ) : (
          <>
            <div className="mb-6 flex items-end justify-between px-2">
              <div>
                <h2 className="text-2xl font-bold">{total} {total === 1 ? 'Photo' : 'Photos'}</h2>
                <p className="text-gray-400 text-sm mt-1">All event photos</p>
              </div>
            </div>

            <SelectionToolbar
              selectedCount={selectedIds.size}
              totalCount={photos.length}
              onSelectAll={() => selectAll(photos.map(p => p.image_id))}
              onBulkDownload={handleBulkDownload}
              downloading={downloading}
              allowDownloads={allowDownloads}
            />

            <PhotoGrid
              photos={photos}
              selectedIds={selectedIds}
              allowDownloads={allowDownloads}
              eventName={eventName}
              shareMenuPhoto={shareMenuPhoto}
              onSelect={toggleSelect}
              onView={(_photo, index) => setSelectedIndex(index)}
              onShare={handleShare}
              onDownload={handleDownload}
              onShareMenuClose={() => setShareMenuPhoto(null)}
            />

            {/* Load More */}
            {photos.length < total && (
              <div className="text-center mt-10">
                <button
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="bg-white/10 text-white px-8 py-3 rounded-xl font-bold hover:bg-white/15 transition-colors disabled:opacity-50"
                >
                  {loadingMore ? (
                    <span className="flex items-center gap-2"><Loader2 className="w-5 h-5 animate-spin" /> Loading...</span>
                  ) : (
                    `Load More (${photos.length} of ${total})`
                  )}
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Modal */}
      {selectedIndex !== null && (
        <PhotoModal
          photos={photos}
          currentIndex={selectedIndex}
          onClose={() => setSelectedIndex(null)}
          onShare={handleShare}
          onDownload={handleDownload}
          onNavigate={setSelectedIndex}
          allowDownloads={allowDownloads}
        />
      )}
    </div>
  )
}
