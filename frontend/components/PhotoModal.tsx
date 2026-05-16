import { useEffect, useRef, useCallback, useState } from 'react'
import Image from 'next/image'
import { Download, Share2, X, ChevronLeft, ChevronRight, Flag, Loader2 } from 'lucide-react'
import ReportPhotoModal from '@/components/ReportPhotoModal'

interface Photo {
  original_url: string
  image_id: string
  similarity?: number
  download_url?: string
}

interface PhotoModalProps {
  photos: Photo[]
  currentIndex: number
  onClose: () => void
  onShare: (imageId: string) => void
  onDownload: (photo: Photo) => void
  onNavigate: (index: number) => void
  allowDownloads: boolean
}

export default function PhotoModal({
  photos,
  currentIndex,
  onClose,
  onShare,
  onDownload,
  onNavigate,
  allowDownloads,
}: PhotoModalProps) {
  const touchStartX = useRef<number | null>(null)
  const [reportOpen, setReportOpen] = useState(false)
  const [imageLoaded, setImageLoaded] = useState(false)
  const photo = photos[currentIndex]
  const hasPrev = currentIndex > 0
  const hasNext = currentIndex < photos.length - 1

  const goPrev = useCallback(() => {
    if (hasPrev) onNavigate(currentIndex - 1)
  }, [hasPrev, currentIndex, onNavigate])

  const goNext = useCallback(() => {
    if (hasNext) onNavigate(currentIndex + 1)
  }, [hasNext, currentIndex, onNavigate])

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowLeft') goPrev()
      else if (e.key === 'ArrowRight') goNext()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose, goPrev, goNext])

  // Lock body scroll
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [])

  // Reset the loaded state whenever the active photo changes so the
  // spinner shows again until the new image finishes decoding.
  useEffect(() => {
    setImageLoaded(false)
  }, [currentIndex])

  // Preload the adjacent photos into the browser HTTP cache so that
  // pressing next/prev hits a warm cache and renders instantly. Signed
  // URLs are 15-min HMAC URLs, so the cache key (URL + signature) is
  // stable for the life of the gallery view.
  useEffect(() => {
    const preload = (url?: string) => {
      if (!url) return
      const img = new window.Image()
      img.src = url
    }
    preload(photos[currentIndex + 1]?.original_url)
    preload(photos[currentIndex - 1]?.original_url)
    // Also one further ahead — pays off for users who scroll quickly.
    preload(photos[currentIndex + 2]?.original_url)
  }, [currentIndex, photos])

  // Touch swipe handlers
  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX
  }

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (touchStartX.current === null) return
    const delta = e.changedTouches[0].clientX - touchStartX.current
    touchStartX.current = null
    if (delta > 50) goPrev()
    else if (delta < -50) goNext()
  }

  if (!photo) return null

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/95 backdrop-blur-sm animate-in fade-in duration-200"
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      {/* Close button — anchored top-right, doesn't take a row of its own. */}
      <button
        onClick={onClose}
        aria-label="Close"
        className="absolute top-3 right-3 sm:top-5 sm:right-5 p-2.5 sm:p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors z-50"
      >
        <X className="w-5 h-5 sm:w-6 sm:h-6" />
      </button>

      {/* Image area — flex-1 so the photo gets every remaining pixel of
          screen real estate. object-contain keeps the photo whole; the
          parent's full width/height bound it so portraits no longer fit
          inside a 16:10 letterbox. */}
      <div
        className="relative flex-1 min-h-0 w-full"
        onClick={onClose}
      >
        <Image
          src={photo.original_url}
          alt="Full size photo"
          fill
          priority
          sizes="100vw"
          className={`object-contain transition-opacity duration-200 ${imageLoaded ? 'opacity-100' : 'opacity-0'}`}
          onLoadingComplete={() => setImageLoaded(true)}
          // key forces a fresh <img> on slide so the opacity transition
          // restarts and the previous photo doesn't briefly stay visible.
          key={photo.image_id}
        />
        {!imageLoaded && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <Loader2 className="w-10 h-10 text-white/60 animate-spin" />
          </div>
        )}

        {/* Previous arrow */}
        {hasPrev && (
          <button
            onClick={(e) => { e.stopPropagation(); goPrev() }}
            aria-label="Previous"
            className="absolute left-2 sm:left-4 top-1/2 -translate-y-1/2 p-2.5 sm:p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors z-50 hidden sm:flex"
          >
            <ChevronLeft className="w-5 h-5 sm:w-6 sm:h-6" />
          </button>
        )}

        {/* Next arrow */}
        {hasNext && (
          <button
            onClick={(e) => { e.stopPropagation(); goNext() }}
            aria-label="Next"
            className="absolute right-2 sm:right-4 top-1/2 -translate-y-1/2 p-2.5 sm:p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors z-50 hidden sm:flex"
          >
            <ChevronRight className="w-5 h-5 sm:w-6 sm:h-6" />
          </button>
        )}
      </div>

      {/* Bottom action bar — full-width strip; doesn't compete with the
          image for space. */}
      <div
        className="flex items-center justify-center gap-2 sm:gap-3 px-3 py-2 sm:py-3 bg-black/55 backdrop-blur-xl border-t border-white/10"
        onClick={(e) => e.stopPropagation()}
      >
        <span className="text-xs sm:text-sm text-gray-400 font-medium">
          {currentIndex + 1} / {photos.length}
        </span>
        <div className="w-px h-5 bg-white/15"></div>

        {photo.similarity !== undefined && (
          <>
            <div className="text-xs sm:text-sm font-bold">
              Match: <span className="text-green-400">{Math.round(photo.similarity * 100)}%</span>
            </div>
            <div className="w-px h-5 bg-white/15"></div>
          </>
        )}

        <button
          onClick={() => onShare(photo.image_id)}
          className="p-2 sm:p-2.5 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors"
          title="Share"
          aria-label="Share"
        >
          <Share2 className="w-4 h-4 sm:w-5 sm:h-5" />
        </button>

        {allowDownloads && photo.download_url && (
          <button
            onClick={() => onDownload(photo)}
            className="p-2 sm:p-2.5 bg-white text-black rounded-lg hover:bg-gray-200 transition-colors"
            title="Download"
            aria-label="Download"
          >
            <Download className="w-4 h-4 sm:w-5 sm:h-5" />
          </button>
        )}

        <button
          onClick={() => setReportOpen(true)}
          className="p-2 sm:p-2.5 bg-white/5 text-gray-400 hover:text-orange-400 hover:bg-orange-500/10 rounded-lg transition-colors"
          title="Report this photo"
          aria-label="Report this photo"
        >
          <Flag className="w-4 h-4 sm:w-5 sm:h-5" />
        </button>
      </div>

      <ReportPhotoModal
        open={reportOpen}
        imageId={photo.image_id}
        onClose={() => setReportOpen(false)}
      />
    </div>
  )
}
