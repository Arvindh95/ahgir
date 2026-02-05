import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import PhotoUpload from '@/components/PhotoUpload'
import { photoService, Photo } from '@/lib/photos'
import { ArrowLeft, Trash2, Filter, Loader2, Image as ImageIcon, CheckCircle, AlertTriangle, Clock, XCircle } from 'lucide-react'

export default function EventPhotosPage() {
  const router = useRouter()
  const { id } = router.query
  const [photos, setPhotos] = useState<Photo[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  useEffect(() => {
    if (id && typeof id === 'string') {
      loadPhotos(id)
    }
  }, [id, statusFilter, page])

  const loadPhotos = async (eventId: string) => {
    try {
      setIsLoading(true)
      const data = await photoService.getPhotos(eventId, page, 50, statusFilter || undefined)
      setPhotos(data.photos)
      setTotal(data.total)
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to load photos')
    } finally {
      setIsLoading(false)
    }
  }

  const handleDelete = async (imageId: string) => {
    if (!id || typeof id !== 'string' || !confirm('Delete this photo?')) {
      return
    }

    try {
      await photoService.deletePhoto(id, imageId)
      loadPhotos(id)
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to delete photo')
    }
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
      <AdminLayout>
        <div className="max-w-7xl mx-auto">
          <div className="flex justify-between items-center mb-8">
            <div className="flex items-center gap-4">
              <button 
                onClick={() => router.push(`/admin/events/${id}`)}
                className="p-2 rounded-lg hover:bg-white/10 transition-colors"
               >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <h1 className="text-3xl font-bold">Manage Photos</h1>
            </div>
          </div>

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
              <div className="flex items-center gap-2 bg-white/5 px-3 py-1.5 rounded-lg border border-white/10 w-full sm:w-auto">
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

            {error && (
              <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl">
                {error}
              </div>
            )}

            {isLoading ? (
               <div className="flex justify-center p-12">
                  <Loader2 className="w-8 h-8 animate-spin text-white" />
               </div>
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
                      className="bg-white/5 border border-white/10 rounded-xl overflow-hidden hover:border-white/20 transition-colors group"
                    >
                      <div className="aspect-square relative bg-black/40">
                        <img
                          src={photo.thumbnail_url}
                          alt={photo.filename}
                          className="w-full h-full object-cover"
                        />
                        <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                           <button
                             onClick={() => handleDelete(photo.image_id)}
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
      </AdminLayout>
    </ProtectedRoute>
  )
}
