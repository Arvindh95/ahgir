import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import { ArrowLeft, Download, Eye, Image as ImageIcon, Loader2, X } from 'lucide-react'

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
  const [selectedPhoto, setSelectedPhoto] = useState<MatchedPhoto | null>(null)

  useEffect(() => {
    // Check authentication
    const token = localStorage.getItem('event_token')
    if (!token) {
      router.push(`/e/${slug}`)
      return
    }
    
    // Load scan results
    const resultsStr = localStorage.getItem('scan_results')
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
    localStorage.removeItem('scan_results')
    router.push(`/e/${slug}/scan`)
  }

  const handleDownload = async (photo: MatchedPhoto) => {
    if (!photo.download_url) return

    try {
      const res = await fetch(photo.download_url)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `photo_${photo.image_id}.jpg`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Download error:', err)
      alert('Failed to download photo')
    }
  }

  const handleViewOriginal = (photo: MatchedPhoto) => {
    setSelectedPhoto(photo)
  }

  const closeModal = () => {
    setSelectedPhoto(null)
  }

  if (!scanResult) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-white animate-spin" />
      </div>
    )
  }

  return (
    <div className="min-h-screen relative bg-black text-white">
      {/* Background Ambience */}
      <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-black via-[#0a0a0a] to-[#050505] z-0 fixed"></div>
      
      <div className="relative z-10 max-w-7xl mx-auto px-4 py-8">
        <div className="flex flex-col sm:flex-row justify-between items-center gap-4 mb-8 glass-card p-4 rounded-xl">
          <h1 className="text-xl font-bold">{eventName}</h1>
          <button 
             onClick={handleBackToScanner} 
             className="flex items-center gap-2 text-blue-400 hover:text-blue-300 transition-colors font-medium"
          >
            <ArrowLeft className="w-5 h-5" />
            Back to Scanner
          </button>
        </div>

        {scanResult.total_matches === 0 ? (
          <div className="glass-card p-12 rounded-2xl text-center max-w-2xl mx-auto">
            <div className="w-24 h-24 bg-white/5 rounded-full flex items-center justify-center mx-auto mb-6">
               <ImageIcon className="w-12 h-12 text-gray-500" />
            </div>
            <h2 className="text-2xl font-bold mb-4">No Photos Found</h2>
            <p className="text-gray-400 mb-8 max-w-md mx-auto">
              We couldn't find any photos matching your face. It's possible your photos haven't been uploaded yet or the match confidence was too low.
            </p>
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
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {scanResult.matches.map((photo) => (
                <div key={photo.image_id} className="glass-card rounded-2xl overflow-hidden group hover:bg-white/10 transition-colors">
                  <div 
                     className="aspect-[4/3] relative overflow-hidden cursor-pointer"
                     onClick={() => handleViewOriginal(photo)}
                  >
                    <img
                      src={photo.thumbnail_url}
                      alt="Matched photo"
                      className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                    />
                    <div className="absolute top-3 right-3 bg-black/60 backdrop-blur-md px-3 py-1 rounded-full text-xs font-bold border border-white/10 flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-green-500"></span>
                      {Math.round(photo.similarity * 100)}%
                    </div>
                    
                    {/* Hover Overlay */}
                    <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                       <Eye className="w-8 h-8 text-white drop-shadow-lg" />
                    </div>
                  </div>
                  
                  <div className="p-4 flex gap-3">
                    <button
                      onClick={() => handleViewOriginal(photo)}
                      className="flex-1 py-2 bg-white/5 hover:bg-white/10 rounded-lg text-sm font-medium transition-colors border border-white/5"
                    >
                      View
                    </button>
                    
                    {allowDownloads && photo.download_url && (
                      <button
                        onClick={() => handleDownload(photo)}
                        className="flex-1 py-2 bg-white text-black hover:bg-gray-200 rounded-lg text-sm font-bold transition-colors flex items-center justify-center gap-2"
                      >
                        <Download className="w-4 h-4" /> Download
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Modal for viewing full-size photo */}
      {selectedPhoto && (
        <div 
           className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/95 backdrop-blur-sm animate-in fade-in duration-200"
           onClick={closeModal}
        >
          <button 
             onClick={closeModal} 
             className="absolute top-6 right-6 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors z-50"
          >
            <X className="w-6 h-6" />
          </button>
          
          <div 
             className="relative max-w-6xl w-full max-h-screen flex flex-col items-center" 
             onClick={(e) => e.stopPropagation()}
          >
            <img
              src={selectedPhoto.original_url}
              alt="Full size photo"
              className="max-w-full max-h-[85vh] object-contain rounded-lg shadow-2xl"
            />
            
            <div className="mt-6 flex items-center gap-4 bg-black/50 backdrop-blur-xl px-6 py-4 rounded-2xl border border-white/10">
              <div className="text-lg font-bold">
                 Match Confidence: <span className="text-green-400">{Math.round(selectedPhoto.similarity * 100)}%</span>
              </div>
              
              {allowDownloads && selectedPhoto.download_url && (
                <>
                  <div className="w-px h-6 bg-white/20"></div>
                  <button
                    onClick={() => handleDownload(selectedPhoto)}
                    className="flex items-center gap-2 bg-white text-black px-6 py-2 rounded-lg font-bold hover:bg-gray-200 transition-colors"
                  >
                    <Download className="w-4 h-4" /> Download Photo
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
