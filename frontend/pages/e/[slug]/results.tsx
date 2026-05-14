import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import PhotoGridSkeleton from '@/components/skeletons/PhotoGridSkeleton'
import { ArrowLeft, Image as ImageIcon } from 'lucide-react'
import PhotoGrid from '@/components/PhotoGrid'
import PhotoModal from '@/components/PhotoModal'
import SelectionToolbar from '@/components/SelectionToolbar'
import { useShare } from '@/components/ShareMenu'
import { usePhotoActions } from '@/hooks/usePhotoActions'

interface MatchedPhoto {
  image_id: string
  similarity: number
  thumbnail_url: string
  original_url: string
  download_url?: string
  face_bbox: number[]
}

interface ScanResult {
  matches: MatchedPhoto[]
  scan_id: string
  total_matches: number
}

export default function ScanResults() {
  const router = useRouter()
  const { slug } = router.query

  const [scanResult, setScanResult] = useState<ScanResult | null>(null)
  const [eventName, setEventName] = useState('')
  const [allowDownloads, setAllowDownloads] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)

  const { selectedIds, toggleSelect, selectAll, handleDownload, handleBulkDownload, downloading } = usePhotoActions()
  const { shareMenuPhoto, setShareMenuPhoto, handleShare } = useShare(eventName)

  useEffect(() => {
    const token = localStorage.getItem('event_token')
    if (!token) {
      router.push(`/e/${slug}`)
      return
    }

    const resultsStr = sessionStorage.getItem('scan_results')
    if (!resultsStr) {
      router.push(`/e/${slug}/scan`)
      return
    }

    try {
      const results = JSON.parse(resultsStr)
      setScanResult(results)
    } catch (err) {
      console.error('Failed to parse scan results:', err)
      router.push(`/e/${slug}/scan`)
      return
    }

    const storedEventName = localStorage.getItem('event_name')
    const storedAllowDownloads = localStorage.getItem('allow_downloads')

    setEventName(storedEventName || '')
    setAllowDownloads(storedAllowDownloads === 'true')
  }, [slug, router])

  const handleBackToScanner = () => {
    sessionStorage.removeItem('scan_results')
    router.push(`/e/${slug}/scan`)
  }

  if (!scanResult) {
    return (
      <div className="min-h-screen bg-black">
        <div className="max-w-7xl mx-auto px-4 py-8">
          <PhotoGridSkeleton count={8} />
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen relative bg-black text-white">
      <Head><title>Results - PicUr</title></Head>
      <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-black via-[#0a0a0a] to-[#050505] z-0 fixed"></div>

      <div className="relative z-10 max-w-7xl mx-auto px-4 py-8">
        <div className="flex flex-col sm:flex-row justify-between items-center gap-4 mb-8 glass-card p-4 rounded-xl">
          <h1 className="text-xl font-bold">{eventName}</h1>
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push(`/e/${slug}/gallery`)}
              className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors font-medium"
            >
              <ImageIcon className="w-5 h-5" />
              All Photos
            </button>
            <button
              onClick={handleBackToScanner}
              className="flex items-center gap-2 text-blue-400 hover:text-blue-300 transition-colors font-medium"
            >
              <ArrowLeft className="w-5 h-5" />
              Back to Scanner
            </button>
          </div>
        </div>

        {scanResult.total_matches === 0 ? (
          <div className="glass-card p-12 rounded-2xl text-center max-w-2xl mx-auto">
            <div className="w-24 h-24 bg-white/5 rounded-full flex items-center justify-center mx-auto mb-6">
              <ImageIcon className="w-12 h-12 text-gray-500" />
            </div>
            <h2 className="text-2xl font-bold mb-4">No Photos Found</h2>
            <p className="text-gray-400 mb-4 max-w-md mx-auto">
              Your face was recognized but no matching photos were found yet. This could mean your photos haven&apos;t been uploaded or the match confidence was too low.
            </p>
            <ul className="text-gray-500 text-sm mb-8 max-w-sm mx-auto text-left space-y-2">
              <li>• Remove sunglasses or hats and try again</li>
              <li>• Ensure good, even lighting on your face</li>
              <li>• Face the camera directly</li>
              <li>• Check back later — more photos may be uploaded soon</li>
            </ul>
            <button
              onClick={handleBackToScanner}
              className="bg-blue-600 text-white px-8 py-3 rounded-xl font-bold hover:bg-blue-700 transition-colors shadow-lg shadow-blue-600/20"
            >
              Try Scanning Again
            </button>
          </div>
        ) : (
          <>
            <div className="mb-6 flex items-end justify-between px-2">
              <div>
                <h2 className="text-2xl font-bold flex items-center gap-2">
                  Found {scanResult.total_matches} {scanResult.total_matches === 1 ? 'Photo' : 'Photos'}
                </h2>
                <p className="text-gray-400 text-sm mt-1">Sorted by match confidence</p>
                <p className="text-gray-500 text-xs mt-1">
                  Heads up: your event doppelganger may have crashed the party.
                </p>
              </div>
            </div>

            <SelectionToolbar
              selectedCount={selectedIds.size}
              totalCount={scanResult.matches.length}
              onSelectAll={() => selectAll(scanResult.matches.map(p => p.image_id))}
              onBulkDownload={handleBulkDownload}
              downloading={downloading}
              allowDownloads={allowDownloads}
            />

            <PhotoGrid
              photos={scanResult.matches}
              selectedIds={selectedIds}
              allowDownloads={allowDownloads}
              eventName={eventName}
              shareMenuPhoto={shareMenuPhoto}
              showSimilarity
              onSelect={toggleSelect}
              onView={(_photo, index) => setSelectedIndex(index)}
              onShare={handleShare}
              onDownload={handleDownload}
              onShareMenuClose={() => setShareMenuPhoto(null)}
            />
          </>
        )}
      </div>

      {/* Modal */}
      {selectedIndex !== null && (
        <PhotoModal
          photos={scanResult.matches}
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
