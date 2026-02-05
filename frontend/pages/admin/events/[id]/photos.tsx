import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import PhotoUpload from '@/components/PhotoUpload'
import { photoService, Photo } from '@/lib/photos'

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

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'indexed':
        return '#28a745'
      case 'pending':
        return '#ff9800'
      case 'no_faces':
        return '#666'
      case 'failed':
        return '#dc3545'
      default:
        return '#999'
    }
  }

  const getStatusBadgeStyle = (status: string) => ({
    display: 'inline-block',
    padding: '4px 8px',
    borderRadius: '4px',
    fontSize: '12px',
    fontWeight: 'bold',
    color: 'white',
    backgroundColor: getStatusColor(status),
  })

  return (
    <ProtectedRoute>
      <AdminLayout>
        <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h1>Manage Photos</h1>
            <button
              onClick={() => router.push(`/admin/events/${id}`)}
              style={{
                backgroundColor: '#f5f5f5',
                color: '#333',
                border: '1px solid #ddd',
                padding: '10px 20px',
                borderRadius: '4px',
                cursor: 'pointer',
              }}
            >
              Back to Event
            </button>
          </div>

          {id && typeof id === 'string' && (
            <PhotoUpload
              eventId={id}
              onUploadComplete={() => loadPhotos(id)}
            />
          )}

          <div style={{ backgroundColor: 'white', padding: '20px', borderRadius: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ margin: 0 }}>Photos ({total})</h2>
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <label htmlFor="statusFilter" style={{ fontSize: '14px' }}>Filter:</label>
                <select
                  id="statusFilter"
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value)
                    setPage(1)
                  }}
                  style={{
                    padding: '8px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    fontSize: '14px',
                  }}
                >
                  <option value="">All</option>
                  <option value="pending">Pending</option>
                  <option value="indexed">Indexed</option>
                  <option value="no_faces">No Faces</option>
                  <option value="failed">Failed</option>
                </select>
              </div>
            </div>

            {error && (
              <div style={{ color: 'red', marginBottom: '20px', padding: '10px', backgroundColor: '#ffebee', borderRadius: '4px' }}>
                {error}
              </div>
            )}

            {isLoading ? (
              <p>Loading photos...</p>
            ) : photos.length === 0 ? (
              <p style={{ textAlign: 'center', color: '#666', padding: '40px' }}>
                No photos found
              </p>
            ) : (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '15px' }}>
                  {photos.map((photo) => (
                    <div
                      key={photo.image_id}
                      style={{
                        border: '1px solid #ddd',
                        borderRadius: '8px',
                        overflow: 'hidden',
                        backgroundColor: '#fafafa',
                      }}
                    >
                      <div style={{ position: 'relative', paddingTop: '100%', backgroundColor: '#e0e0e0' }}>
                        <img
                          src={photo.thumbnail_url}
                          alt={photo.filename}
                          style={{
                            position: 'absolute',
                            top: 0,
                            left: 0,
                            width: '100%',
                            height: '100%',
                            objectFit: 'cover',
                          }}
                        />
                      </div>
                      <div style={{ padding: '10px' }}>
                        <div style={{ fontSize: '12px', marginBottom: '5px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {photo.filename}
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                          <span style={getStatusBadgeStyle(photo.status)}>
                            {photo.status}
                          </span>
                          {photo.status === 'indexed' && (
                            <span style={{ fontSize: '12px', color: '#666' }}>
                              {photo.face_count} face{photo.face_count !== 1 ? 's' : ''}
                            </span>
                          )}
                        </div>
                        <button
                          onClick={() => handleDelete(photo.image_id)}
                          style={{
                            width: '100%',
                            padding: '6px',
                            backgroundColor: '#dc3545',
                            color: 'white',
                            border: 'none',
                            borderRadius: '4px',
                            cursor: 'pointer',
                            fontSize: '12px',
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                {total > 50 && (
                  <div style={{ display: 'flex', justifyContent: 'center', gap: '10px', marginTop: '20px' }}>
                    <button
                      onClick={() => setPage(page - 1)}
                      disabled={page === 1}
                      style={{
                        padding: '8px 16px',
                        backgroundColor: page === 1 ? '#ccc' : '#0070f3',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: page === 1 ? 'not-allowed' : 'pointer',
                      }}
                    >
                      Previous
                    </button>
                    <span style={{ padding: '8px 16px', display: 'flex', alignItems: 'center' }}>
                      Page {page} of {Math.ceil(total / 50)}
                    </span>
                    <button
                      onClick={() => setPage(page + 1)}
                      disabled={page >= Math.ceil(total / 50)}
                      style={{
                        padding: '8px 16px',
                        backgroundColor: page >= Math.ceil(total / 50) ? '#ccc' : '#0070f3',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: page >= Math.ceil(total / 50) ? 'not-allowed' : 'pointer',
                      }}
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
