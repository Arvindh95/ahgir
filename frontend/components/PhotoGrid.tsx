import { Check, Download, Eye, Share2 } from 'lucide-react'
import { ShareMenu } from './ShareMenu'

interface Photo {
  image_id: string
  thumbnail_url: string
  original_url: string
  download_url?: string
  similarity?: number
}

interface PhotoGridProps {
  photos: Photo[]
  selectedIds: Set<string>
  allowDownloads: boolean
  eventName: string
  shareMenuPhoto: string | null
  showSimilarity?: boolean
  onSelect: (imageId: string) => void
  onView: (photo: Photo) => void
  onShare: (imageId: string) => void
  onDownload: (photo: Photo) => void
  onShareMenuClose: () => void
}

export default function PhotoGrid({
  photos,
  selectedIds,
  allowDownloads,
  eventName,
  shareMenuPhoto,
  showSimilarity = false,
  onSelect,
  onView,
  onShare,
  onDownload,
  onShareMenuClose,
}: PhotoGridProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
      {photos.map((photo) => (
        <div key={photo.image_id} className="glass-card rounded-2xl overflow-hidden group hover:bg-white/10 transition-colors">
          <div
            className="aspect-[4/3] relative overflow-hidden cursor-pointer"
            onClick={() => onView(photo)}
          >
            <img
              src={photo.thumbnail_url}
              alt="Event photo"
              loading="lazy"
              className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
            />

            {/* Selection Checkbox */}
            {allowDownloads && (
              <div
                className={`absolute top-3 left-3 w-6 h-6 rounded border-2 flex items-center justify-center cursor-pointer z-10 transition-all ${
                  selectedIds.has(photo.image_id)
                    ? 'bg-blue-600 border-blue-600'
                    : 'bg-black/40 border-white/40 hover:border-white/70'
                }`}
                onClick={(e) => { e.stopPropagation(); onSelect(photo.image_id) }}
              >
                {selectedIds.has(photo.image_id) && <Check className="w-4 h-4 text-white" />}
              </div>
            )}

            {/* Similarity Badge */}
            {showSimilarity && photo.similarity !== undefined && (
              <div className="absolute top-3 right-3 bg-black/60 backdrop-blur-md px-3 py-1 rounded-full text-xs font-bold border border-white/10 flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-green-500"></span>
                {Math.round(photo.similarity * 100)}%
              </div>
            )}

            <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
              <Eye className="w-8 h-8 text-white drop-shadow-lg" />
            </div>
          </div>

          <div className="p-4 flex gap-3">
            <button
              onClick={() => onView(photo)}
              className="flex-1 py-2 bg-white/5 hover:bg-white/10 rounded-lg text-sm font-medium transition-colors border border-white/5 flex items-center justify-center"
              title="View"
            >
              <Eye className="w-4 h-4" />
            </button>

            <div className="relative flex-1">
              <button
                onClick={(e) => { e.stopPropagation(); onShare(photo.image_id) }}
                className="w-full py-2 bg-white/5 hover:bg-white/10 rounded-lg text-sm transition-colors border border-white/5 flex items-center justify-center"
                title="Share"
              >
                <Share2 className="w-4 h-4" />
              </button>
              {shareMenuPhoto === photo.image_id && (
                <ShareMenu imageId={photo.image_id} eventName={eventName} onClose={onShareMenuClose} />
              )}
            </div>

            {allowDownloads && photo.download_url && (
              <button
                onClick={() => onDownload(photo)}
                className="flex-1 py-2 bg-white text-black hover:bg-gray-200 rounded-lg text-sm font-bold transition-colors flex items-center justify-center"
                title="Download"
              >
                <Download className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
