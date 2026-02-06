import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import { ArrowLeft, Check, CheckSquare, Download, Eye, Image as ImageIcon, Loader2, ScanFace, Share2, Link, X } from 'lucide-react'

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
  const [selectedPhoto, setSelectedPhoto] = useState<GalleryPhoto | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [downloading, setDownloading] = useState(false)
  const [shareMenuPhoto, setShareMenuPhoto] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const shareMenuRef = useRef<HTMLDivElement>(null)

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

  // Close share menu on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (shareMenuRef.current && !shareMenuRef.current.contains(e.target as Node)) {
        setShareMenuPhoto(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const loadMore = () => {
    const nextPage = page + 1
    setPage(nextPage)
    setLoadingMore(true)
    fetchGallery(nextPage, true)
  }

  const handleDownload = async (photo: GalleryPhoto) => {
    if (!photo.download_url) return
    try {
      const res = await fetch(photo.download_url)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = photo.filename || `photo_${photo.image_id}.jpg`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      alert('Failed to download photo')
    }
  }

  // ─── Selection & Bulk Download ───────────────────────────────────────

  const toggleSelect = (imageId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(imageId)) next.delete(imageId)
      else next.add(imageId)
      return next
    })
  }

  const selectAll = () => {
    if (selectedIds.size === photos.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(photos.map(p => p.image_id)))
    }
  }

  const handleBulkDownload = async () => {
    if (selectedIds.size === 0) return
    setDownloading(true)
    try {
      const token = localStorage.getItem('event_token')
      const response = await fetch(`${API_URL}/download-zip`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ image_ids: Array.from(selectedIds) })
      })
      if (!response.ok) throw new Error('Download failed')
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'photos.zip'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      alert('Failed to download photos')
    } finally {
      setDownloading(false)
    }
  }

  // ─── Social Sharing ──────────────────────────────────────────────────

  const getShareUrl = (imageId: string) => {
    const eventId = localStorage.getItem('event_id')
    return `${window.location.origin}/share/${eventId}/${imageId}`
  }

  const handleShare = async (photo: GalleryPhoto) => {
    const shareUrl = getShareUrl(photo.image_id)
    const shareText = `Check out this photo from ${eventName}!`

    if (navigator.share) {
      try {
        await navigator.share({ title: eventName, text: shareText, url: shareUrl })
        return
      } catch {
        // fall through
      }
    }
    setShareMenuPhoto(photo.image_id)
    setCopied(false)
  }

  const copyShareLink = async (imageId: string) => {
    const url = getShareUrl(imageId)
    await navigator.clipboard.writeText(url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const shareToWhatsApp = (imageId: string) => {
    const url = getShareUrl(imageId)
    window.open(`https://wa.me/?text=${encodeURIComponent(`Check out this photo from ${eventName}! ${url}`)}`, '_blank')
    setShareMenuPhoto(null)
  }

  const shareToFacebook = (imageId: string) => {
    const url = getShareUrl(imageId)
    window.open(`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`, '_blank')
    setShareMenuPhoto(null)
  }

  const shareToX = (imageId: string) => {
    const url = getShareUrl(imageId)
    window.open(`https://twitter.com/intent/tweet?url=${encodeURIComponent(url)}&text=${encodeURIComponent(`Check out this photo from ${eventName}!`)}`, '_blank')
    setShareMenuPhoto(null)
  }

  const ShareMenu = ({ imageId }: { imageId: string }) => (
    <div ref={shareMenuRef} className="absolute bottom-full mb-2 right-0 glass-card rounded-xl p-2 min-w-[180px] z-30 border border-white/10 shadow-xl">
      <button onClick={() => copyShareLink(imageId)} className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 transition-colors text-sm">
        <Link className="w-4 h-4" /> {copied ? 'Copied!' : 'Copy Link'}
      </button>
      <button onClick={() => shareToWhatsApp(imageId)} className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 transition-colors text-sm">
        <span className="w-4 h-4 text-center">W</span> WhatsApp
      </button>
      <button onClick={() => shareToFacebook(imageId)} className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 transition-colors text-sm">
        <span className="w-4 h-4 text-center">f</span> Facebook
      </button>
      <button onClick={() => shareToX(imageId)} className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 transition-colors text-sm">
        <span className="w-4 h-4 text-center">X</span> X / Twitter
      </button>
    </div>
  )

  // ─── Render ──────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-white animate-spin" />
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

            {/* Selection Toolbar */}
            {allowDownloads && (
              <div className="mb-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 glass-card p-4 rounded-xl">
                <div className="flex items-center gap-4">
                  <button onClick={selectAll} className="flex items-center gap-2 text-sm text-gray-300 hover:text-white transition-colors">
                    <CheckSquare className="w-4 h-4" />
                    {selectedIds.size === photos.length ? 'Deselect All' : 'Select All'}
                  </button>
                  {selectedIds.size > 0 && (
                    <span className="text-sm text-gray-400">{selectedIds.size} selected</span>
                  )}
                </div>
                {selectedIds.size > 0 && (
                  <button
                    onClick={handleBulkDownload}
                    disabled={downloading}
                    className="flex items-center gap-2 bg-white text-black px-5 py-2 rounded-lg font-bold hover:bg-gray-200 transition-colors disabled:opacity-50"
                  >
                    {downloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                    Download {selectedIds.size} {selectedIds.size === 1 ? 'Photo' : 'Photos'}
                  </button>
                )}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {photos.map((photo) => (
                <div key={photo.image_id} className="glass-card rounded-2xl overflow-hidden group hover:bg-white/10 transition-colors">
                  <div
                    className="aspect-[4/3] relative overflow-hidden cursor-pointer"
                    onClick={() => setSelectedPhoto(photo)}
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
                        onClick={(e) => { e.stopPropagation(); toggleSelect(photo.image_id) }}
                      >
                        {selectedIds.has(photo.image_id) && <Check className="w-4 h-4 text-white" />}
                      </div>
                    )}

                    <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                      <Eye className="w-8 h-8 text-white drop-shadow-lg" />
                    </div>
                  </div>

                  <div className="p-4 flex gap-3">
                    <button
                      onClick={() => setSelectedPhoto(photo)}
                      className="flex-1 py-2 bg-white/5 hover:bg-white/10 rounded-lg text-sm font-medium transition-colors border border-white/5 flex items-center justify-center"
                      title="View"
                    >
                      <Eye className="w-4 h-4" />
                    </button>

                    <div className="relative flex-1">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleShare(photo) }}
                        className="w-full py-2 bg-white/5 hover:bg-white/10 rounded-lg text-sm transition-colors border border-white/5 flex items-center justify-center"
                        title="Share"
                      >
                        <Share2 className="w-4 h-4" />
                      </button>
                      {shareMenuPhoto === photo.image_id && <ShareMenu imageId={photo.image_id} />}
                    </div>

                    {allowDownloads && photo.download_url && (
                      <button
                        onClick={() => handleDownload(photo)}
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
      {selectedPhoto && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/95 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={() => setSelectedPhoto(null)}
        >
          <button
            onClick={() => setSelectedPhoto(null)}
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
              <button
                onClick={() => handleShare(selectedPhoto)}
                className="flex items-center gap-2 bg-white/10 text-white px-4 py-2 rounded-lg font-medium hover:bg-white/20 transition-colors"
              >
                <Share2 className="w-4 h-4" /> Share
              </button>

              {allowDownloads && selectedPhoto.download_url && (
                <>
                  <div className="w-px h-6 bg-white/20"></div>
                  <button
                    onClick={() => handleDownload(selectedPhoto)}
                    className="flex items-center gap-2 bg-white text-black px-6 py-2 rounded-lg font-bold hover:bg-gray-200 transition-colors"
                  >
                    <Download className="w-4 h-4" /> Download
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
