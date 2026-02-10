import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import PhotoUpload from '@/components/PhotoUpload'
import ConfirmModal from '@/components/ConfirmModal'
import { photoService, Photo } from '@/lib/photos'
import { useToast } from '@/hooks/useToast'
import PhotoGridSkeleton from '@/components/skeletons/PhotoGridSkeleton'
import Breadcrumbs from '@/components/Breadcrumbs'
import { eventService } from '@/lib/events'
import Image from 'next/image'
import { Trash2, Filter, Image as ImageIcon, CheckCircle, AlertTriangle, Clock, XCircle, Download, Check, Loader2 } from 'lucide-react'

export default function EventPhotosPage() {
  const router = useRouter()
  const { id } = router.query
  const { toast } = useToast()
  const [photos, setPhotos] = useState<Photo[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [isDeleteLoading, setIsDeleteLoading] = useState(false)
  const [eventName, setEventName] = useState('')
  const [selectedPhotos, setSelectedPhotos] = useState<Set<string>>(new Set())
  const [showBulkDeleteConfirm, setShowBulkDeleteConfirm] = useState(false)
  const [isBulkDeleting, setIsBulkDeleting] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)

  useEffect(() => {
    if (id && typeof id === 'string') {
      loadPhotos(id)
      eventService.getEvent(id).then(e => setEventName(e.name)).catch(() => { })
    }
  }, [id, statusFilter, page])

  const loadPhotos = async (eventId: string) => {
    try {
      setIsLoading(true)
      const data = await photoService.getPhotos(eventId, page, 50, statusFilter || undefined)
      setPhotos(data.photos)
      setTotal(data.total)
    } catch (err: any) {
      toast(err.response?.data?.error?.message || 'Failed to load photos', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!id || typeof id !== 'string' || !deleteTarget) return
    try {
      setIsDeleteLoading(true)
      await photoService.deletePhoto(id, deleteTarget)
      toast('Photo deleted', 'success')
      setDeleteTarget(null)
      loadPhotos(id)
    } catch (err: any) {
      toast(err.response?.data?.error?.message || 'Failed to delete photo', 'error')
    } finally {
      setIsDeleteLoading(false)
    }
  }

  const toggleSelect = (imageId: string) => {
    setSelectedPhotos(prev => {
      const next = new Set(prev)
      if (next.has(imageId)) next.delete(imageId)
      else next.add(imageId)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedPhotos.size === photos.length) {
      setSelectedPhotos(new Set())
    } else {
      setSelectedPhotos(new Set(photos.map(p => p.image_id)))
    }
  }

  const handleBulkDelete = async () => {
    if (!id || typeof id !== 'string') return
    try {
      setIsBulkDeleting(true)
      const result = await photoService.bulkDeletePhotos(id, Array.from(selectedPhotos))
      toast(`Deleted ${result.deleted} photos`, 'success')
      setShowBulkDeleteConfirm(false)
      setSelectedPhotos(new Set())
      loadPhotos(id)
    } catch (err: any) {
      toast(err.response?.data?.detail || 'Failed to delete photos', 'error')
    } finally {
      setIsBulkDeleting(false)
    }
  }

  const triggerDownload = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const handleDownloadSelected = async () => {
    if (!id || typeof id !== 'string') return
    try {
      setIsDownloading(true)
      const blob = await photoService.downloadZip(id, Array.from(selectedPhotos))
      const safeName = (eventName || 'photos').replace(/\s+/g, '_')
      triggerDownload(blob, `${safeName}_selected.zip`)
      toast(`Downloading ${selectedPhotos.size} photos`, 'success')
    } catch (err: any) {
      toast(err.response?.data?.detail || 'Failed to download photos', 'error')
    } finally {
      setIsDownloading(false)
    }
  }

  const handleDownloadAll = async () => {
    if (!id || typeof id !== 'string') return
    try {
      setIsDownloading(true)
      const blob = await photoService.downloadAllZip(id)
      const safeName = (eventName || 'photos').replace(/\s+/g, '_')
      triggerDownload(blob, `${safeName}_all.zip`)
      toast('Downloading all photos', 'success')
    } catch (err: any) {
      toast(err.response?.data?.detail || 'Failed to download photos', 'error')
    } finally {
      setIsDownloading(false)
    }
  }

  const handleSingleDownload = (photo: Photo) => {
    const a = document.createElement('a')
    a.href = photo.download_url
    a.download = photo.filename
    a.target = '_blank'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'indexed':
        return (
          <span className="flex items-center gap-1 bg-green-500/20 text-green-400 px-2 py-0.5 rounded text-xs font-bold">
            <CheckCircle className="w-3 h-3" /> Indexed
          </span>
        )
      case 'pending':
        return (
          <span className="flex items-center gap-1 bg-orange-500/20 text-orange-400 px-2 py-0.5 rounded text-xs font-bold">
            <Clock className="w-3 h-3" /> Pending
          </span>
        )
      case 'no_faces':
        return (
          <span className="flex items-center gap-1 bg-gray-500/20 text-gray-400 px-2 py-0.5 rounded text-xs font-bold">
            <AlertTriangle className="w-3 h-3" /> No Faces
          </span>
        )
      case 'failed':
        return (
          <span className="flex items-center gap-1 bg-red-500/20 text-red-400 px-2 py-0.5 rounded text-xs font-bold">
            <XCircle className="w-3 h-3" /> Failed
          </span>
        )
      default:
        return (
          <span className="flex items-center gap-1 bg-gray-500/20 text-gray-400 px-2 py-0.5 rounded text-xs font-bold">
            {status}
          </span>
        )
    }
  }

  return (
    <ProtectedRoute>
      <Head><title>Photos - PicUr</title></Head>
      <AdminLayout>
        <div className="max-w-7xl mx-auto">
          <Breadcrumbs crumbs={[
            { label: 'Events', href: '/admin/events' },
            { label: eventName || 'Event', href: `/admin/events/${id}` },
            { label: 'Photos' },
          ]} />
          <h1 className="text-3xl font-bold mb-8">Manage Photos</h1>

          {id && typeof id === 'string' && (
            <PhotoUpload
              eventId={id}
              onUploadComplete={() => loadPhotos(id)}
            />
          )}

          <div className="glass-card p-6 rounded-2xl mt-8">
            <div className="flex flex-col sm:flex-row justify-between items-center gap-4 mb-6">
              <h2 className="text-xl font-bold flex items-center gap-2">
                <ImageIcon className="w-5 h-5" /> Photos <span className="text-gray-500 text-sm font-normal">({total})</span>
              </h2>
              <div className="flex items-center gap-3 w-full sm:w-auto">
                {/* Download All button */}
                {photos.length > 0 && (
                  <button
                    onClick={handleDownloadAll}
                    disabled={isDownloading}
                    className="flex items-center gap-2 bg-white/5 hover:bg-white/10 border border-white/10 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                    title="Download all photos as ZIP"
                  >
                    {isDownloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                    <span className="hidden sm:inline">Download All</span>
                  </button>
                )}
                <div className="flex items-center gap-2 bg-white/5 px-3 py-1.5 rounded-lg border border-white/10 flex-1 sm:flex-initial">
                  <Filter className="w-4 h-4 text-gray-400" />
                  <label htmlFor="statusFilter" className="text-sm text-gray-400">Filter:</label>
                  <select
                    id="statusFilter"
                    value={statusFilter}
                    onChange={(e) => {
                      setStatusFilter(e.target.value)
                      setPage(1)
                    }}
                    className="bg-transparent border-none text-sm text-white focus:ring-0 cursor-pointer w-full focus:outline-none"
                  >
                    <option value="" className="bg-black">All Photos</option>
                    <option value="pending" className="bg-black">Pending</option>
                    <option value="indexed" className="bg-black">Indexed</option>
                    <option value="no_faces" className="bg-black">No Faces</option>
                    <option value="failed" className="bg-black">Failed</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Bulk actions toolbar */}
            {selectedPhotos.size > 0 && (
              <div className="mb-6 flex flex-col sm:flex-row items-center justify-between gap-3 glass-card p-4 rounded-xl">
                <div className="flex items-center gap-4">
                  <button onClick={toggleSelectAll} className="text-sm text-gray-300 hover:text-white transition-colors">
                    {selectedPhotos.size === photos.length ? 'Deselect All' : 'Select All'}
                  </button>
                  <span className="text-sm text-gray-400">{selectedPhotos.size} selected</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleDownloadSelected}
                    disabled={isDownloading}
                    className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg font-semibold hover:bg-blue-700 transition-colors text-sm disabled:opacity-50"
                  >
                    {isDownloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                    Download Selected
                  </button>
                  <button
                    onClick={() => setShowBulkDeleteConfirm(true)}
                    className="flex items-center gap-2 bg-red-600 text-white px-4 py-2 rounded-lg font-semibold hover:bg-red-700 transition-colors text-sm"
                  >
                    <Trash2 className="w-4 h-4" />
                    Delete Selected
                  </button>
                </div>
              </div>
            )}

            {isLoading ? (
              <PhotoGridSkeleton count={10} columns="grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5" />
            ) : photos.length === 0 ? (
              <div className="text-center py-12 bg-white/5 rounded-xl border border-white/5 border-dashed">
                <div className="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center mx-auto mb-4">
                  <ImageIcon className="w-8 h-8 text-gray-500" />
                </div>
                <p className="text-lg text-gray-300 font-medium">No photos found</p>
                <p className="text-gray-500 text-sm">Upload some photos to get started</p>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                  {photos.map((photo) => (
                    <div
                      key={photo.image_id}
                      className={`bg-white/5 border rounded-xl overflow-hidden hover:border-white/20 transition-colors group ${
                        selectedPhotos.has(photo.image_id) ? 'border-blue-500 ring-1 ring-blue-500/50' : 'border-white/10'
                      }`}
                    >
                      <div className="aspect-square relative bg-black/40">
                        <Image
                          src={photo.thumbnail_url}
                          alt={photo.filename}
                          fill
                          sizes="(max-width: 768px) 50vw, (max-width: 1024px) 33vw, 20vw"
                          className="object-cover"
                        />
                        {/* Selection checkbox */}
                        <div
                          className="absolute top-2 left-2 z-10 cursor-pointer p-1"
                          onClick={() => toggleSelect(photo.image_id)}
                        >
                          <div
                            className={`w-6 h-6 rounded border-2 flex items-center justify-center transition-all ${
                              selectedPhotos.has(photo.image_id)
                                ? 'bg-blue-600 border-blue-600'
                                : selectedPhotos.size > 0
                                  ? 'bg-black/60 border-white/30 opacity-80 hover:opacity-100'
                                  : 'bg-black/60 border-white/30 opacity-0 group-hover:opacity-100'
                            }`}
                          >
                            {selectedPhotos.has(photo.image_id) && <Check className="w-4 h-4 text-white" />}
                          </div>
                        </div>
                        {/* Hover actions */}
                        <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                          <button
                            onClick={() => handleSingleDownload(photo)}
                            className="bg-blue-500 hover:bg-blue-600 text-white p-2 rounded-lg transition-colors"
                            title="Download photo"
                          >
                            <Download className="w-5 h-5" />
                          </button>
                          <button
                            onClick={() => setDeleteTarget(photo.image_id)}
                            className="bg-red-500 hover:bg-red-600 text-white p-2 rounded-lg transition-colors"
                            title="Delete photo"
                          >
                            <Trash2 className="w-5 h-5" />
                          </button>
                        </div>
                      </div>
                      <div className="p-3">
                        <div className="text-xs text-gray-400 mb-2 truncate" title={photo.filename}>
                          {photo.filename}
                        </div>
                        <div className="flex justify-between items-center">
                          {getStatusBadge(photo.status)}
                          {photo.status === 'indexed' && (
                            <span className="text-xs text-gray-500">
                              {photo.face_count} face{photo.face_count !== 1 ? 's' : ''}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {total > 50 && (
                  <div className="flex justify-center gap-2 mt-8">
                    <button
                      onClick={() => setPage(page - 1)}
                      disabled={page === 1}
                      className="px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      Previous
                    </button>
                    <span className="px-4 py-2 text-sm text-gray-400">
                      Page {page} of {Math.ceil(total / 50)}
                    </span>
                    <button
                      onClick={() => setPage(page + 1)}
                      disabled={page >= Math.ceil(total / 50)}
                      className="px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      Next
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        <ConfirmModal
          open={!!deleteTarget}
          title="Delete Photo"
          message="Are you sure you want to delete this photo? This action cannot be undone."
          confirmLabel="Delete Photo"
          variant="danger"
          loading={isDeleteLoading}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
        />

        <ConfirmModal
          open={showBulkDeleteConfirm}
          title="Delete Photos"
          message={`Are you sure you want to delete ${selectedPhotos.size} photo${selectedPhotos.size !== 1 ? 's' : ''}? This action cannot be undone.`}
          confirmLabel="Delete Photos"
          variant="danger"
          loading={isBulkDeleting}
          onConfirm={handleBulkDelete}
          onCancel={() => setShowBulkDeleteConfirm(false)}
        />
      </AdminLayout>
    </ProtectedRoute>
  )
}
