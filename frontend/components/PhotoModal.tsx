import { Download, Share2, X } from 'lucide-react'

interface PhotoModalProps {
  photo: {
    original_url: string
    image_id: string
    similarity?: number
    download_url?: string
  }
  onClose: () => void
  onShare: () => void
  onDownload: () => void
  allowDownloads: boolean
}

export default function PhotoModal({ photo, onClose, onShare, onDownload, allowDownloads }: PhotoModalProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/95 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
    >
      <button
        onClick={onClose}
        className="absolute top-6 right-6 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors z-50"
      >
        <X className="w-6 h-6" />
      </button>

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
          {photo.similarity !== undefined && (
            <>
              <div className="text-lg font-bold">
                Match: <span className="text-green-400">{Math.round(photo.similarity * 100)}%</span>
              </div>
              <div className="w-px h-6 bg-white/20"></div>
            </>
          )}

          <button
            onClick={onShare}
            className="flex items-center gap-2 bg-white/10 text-white px-4 py-2 rounded-lg font-medium hover:bg-white/20 transition-colors"
          >
            <Share2 className="w-4 h-4" /> Share
          </button>

          {allowDownloads && photo.download_url && (
            <>
              <div className="w-px h-6 bg-white/20"></div>
              <button
                onClick={onDownload}
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
