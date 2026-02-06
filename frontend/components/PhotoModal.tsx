import { useEffect, useRef, useCallback } from 'react'
import { Download, Share2, X, ChevronLeft, ChevronRight } from 'lucide-react'

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
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/95 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      {/* Close button */}
      <button
        onClick={onClose}
        className="absolute top-6 right-6 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors z-50"
      >
        <X className="w-6 h-6" />
      </button>

      {/* Previous arrow */}
      {hasPrev && (
        <button
          onClick={(e) => { e.stopPropagation(); goPrev() }}
          className="absolute left-4 top-1/2 -translate-y-1/2 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors z-50 hidden sm:flex"
        >
          <ChevronLeft className="w-6 h-6" />
        </button>
      )}

      {/* Next arrow */}
      {hasNext && (
        <button
          onClick={(e) => { e.stopPropagation(); goNext() }}
          className="absolute right-4 top-1/2 -translate-y-1/2 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors z-50 hidden sm:flex"
        >
          <ChevronRight className="w-6 h-6" />
        </button>
      )}

      <div
        className="relative max-w-6xl w-full max-h-screen flex flex-col items-center"
        onClick={(e) => e.stopPropagation()}
      >
        <img
          src={photo.original_url}
          alt="Full size photo"
          className="max-w-full max-h-[85vh] object-contain rounded-lg shadow-2xl"
        />

        <div className="mt-6 flex items-center gap-4 bg-black/50 backdrop-blur-xl px-6 py-4 rounded-2xl border border-white/10">
          {/* Photo counter */}
          <span className="text-sm text-gray-400 font-medium">
            {currentIndex + 1} / {photos.length}
          </span>
          <div className="w-px h-6 bg-white/20"></div>

          {photo.similarity !== undefined && (
            <>
              <div className="text-lg font-bold">
                Match: <span className="text-green-400">{Math.round(photo.similarity * 100)}%</span>
              </div>
              <div className="w-px h-6 bg-white/20"></div>
            </>
          )}

          <button
            onClick={() => onShare(photo.image_id)}
            className="flex items-center gap-2 bg-white/10 text-white px-4 py-2 rounded-lg font-medium hover:bg-white/20 transition-colors"
          >
            <Share2 className="w-4 h-4" /> Share
          </button>

          {allowDownloads && photo.download_url && (
            <>
              <div className="w-px h-6 bg-white/20"></div>
              <button
                onClick={() => onDownload(photo)}
                className="flex items-center gap-2 bg-white text-black px-6 py-2 rounded-lg font-bold hover:bg-gray-200 transition-colors"
              >
                <Download className="w-4 h-4" /> Download
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
