import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'

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
      // Open download URL in new tab
      window.open(photo.download_url, '_blank')
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
      <div style={styles.container}>
        <p>Loading results...</p>
      </div>
    )
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.title}>{eventName}</h1>
        <button onClick={handleBackToScanner} style={styles.backButton}>
          ← Back to Scanner
        </button>
      </div>

      <div style={styles.content}>
        {scanResult.total_matches === 0 ? (
          <div style={styles.emptyState}>
            <div style={styles.emptyIcon}>📷</div>
            <h2 style={styles.emptyTitle}>No Photos Found</h2>
            <p style={styles.emptyText}>
              We couldn't find any photos matching your face in this event.
              This could be because:
            </p>
            <ul style={styles.emptyList}>
              <li>Your photos haven't been uploaded yet</li>
              <li>The lighting conditions were different</li>
              <li>You were wearing different accessories (glasses, hat, etc.)</li>
            </ul>
            <button onClick={handleBackToScanner} style={styles.tryAgainButton}>
              Try Scanning Again
            </button>
          </div>
        ) : (
          <>
            <div style={styles.resultsHeader}>
              <h2 style={styles.resultsTitle}>
                Found {scanResult.total_matches} {scanResult.total_matches === 1 ? 'Photo' : 'Photos'}
              </h2>
              <p style={styles.resultsSubtitle}>
                Photos are sorted by similarity to your face
              </p>
            </div>

            <div style={styles.gallery}>
              {scanResult.matches.map((photo) => (
                <div key={photo.image_id} style={styles.photoCard}>
                  <div style={styles.photoContainer}>
                    <img
                      src={photo.thumbnail_url}
                      alt="Matched photo"
                      style={styles.photo}
                      onClick={() => handleViewOriginal(photo)}
                    />
                    <div style={styles.similarityBadge}>
                      {Math.round(photo.similarity * 100)}% match
                    </div>
                  </div>
                  
                  <div style={styles.photoActions}>
                    <button
                      onClick={() => handleViewOriginal(photo)}
                      style={styles.viewButton}
                    >
                      View Full Size
                    </button>
                    
                    {allowDownloads && photo.download_url && (
                      <button
                        onClick={() => handleDownload(photo)}
                        style={styles.downloadButton}
                      >
                        Download
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
        <div style={styles.modal} onClick={closeModal}>
          <div style={styles.modalContent} onClick={(e) => e.stopPropagation()}>
            <button onClick={closeModal} style={styles.closeButton}>
              ✕
            </button>
            <img
              src={selectedPhoto.original_url}
              alt="Full size photo"
              style={styles.modalImage}
            />
            <div style={styles.modalActions}>
              <div style={styles.modalSimilarity}>
                {Math.round(selectedPhoto.similarity * 100)}% match
              </div>
              {allowDownloads && selectedPhoto.download_url && (
                <button
                  onClick={() => handleDownload(selectedPhoto)}
                  style={styles.modalDownloadButton}
                >
                  Download Photo
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const styles = {
  container: {
    minHeight: '100vh',
    backgroundColor: '#f5f5f5',
    padding: '20px',
  } as React.CSSProperties,
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    maxWidth: '1400px',
    margin: '0 auto 30px',
    padding: '20px',
    backgroundColor: 'white',
    borderRadius: '8px',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
  } as React.CSSProperties,
  title: {
    fontSize: '24px',
    fontWeight: 'bold',
    color: '#333',
    margin: 0,
  } as React.CSSProperties,
  backButton: {
    padding: '8px 16px',
    fontSize: '14px',
    color: '#007bff',
    backgroundColor: 'transparent',
    border: '1px solid #007bff',
    borderRadius: '4px',
    cursor: 'pointer',
  } as React.CSSProperties,
  content: {
    maxWidth: '1400px',
    margin: '0 auto',
  } as React.CSSProperties,
  emptyState: {
    backgroundColor: 'white',
    borderRadius: '8px',
    padding: '60px 40px',
    textAlign: 'center',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
  } as React.CSSProperties,
  emptyIcon: {
    fontSize: '64px',
    marginBottom: '20px',
  } as React.CSSProperties,
  emptyTitle: {
    fontSize: '24px',
    fontWeight: 'bold',
    color: '#333',
    marginBottom: '12px',
  } as React.CSSProperties,
  emptyText: {
    fontSize: '16px',
    color: '#666',
    marginBottom: '16px',
    lineHeight: '1.5',
  } as React.CSSProperties,
  emptyList: {
    textAlign: 'left',
    display: 'inline-block',
    color: '#666',
    marginBottom: '30px',
    lineHeight: '1.8',
  } as React.CSSProperties,
  tryAgainButton: {
    padding: '12px 24px',
    fontSize: '16px',
    fontWeight: '600',
    color: 'white',
    backgroundColor: '#007bff',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
  } as React.CSSProperties,
  resultsHeader: {
    backgroundColor: 'white',
    borderRadius: '8px',
    padding: '20px',
    marginBottom: '20px',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
  } as React.CSSProperties,
  resultsTitle: {
    fontSize: '24px',
    fontWeight: 'bold',
    color: '#333',
    marginBottom: '8px',
  } as React.CSSProperties,
  resultsSubtitle: {
    fontSize: '14px',
    color: '#666',
    margin: 0,
  } as React.CSSProperties,
  gallery: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
    gap: '20px',
  } as React.CSSProperties,
  photoCard: {
    backgroundColor: 'white',
    borderRadius: '8px',
    overflow: 'hidden',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
    transition: 'transform 0.2s, box-shadow 0.2s',
  } as React.CSSProperties,
  photoContainer: {
    position: 'relative',
    aspectRatio: '4/3',
    overflow: 'hidden',
    cursor: 'pointer',
  } as React.CSSProperties,
  photo: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
    transition: 'transform 0.2s',
  } as React.CSSProperties,
  similarityBadge: {
    position: 'absolute',
    top: '10px',
    right: '10px',
    backgroundColor: 'rgba(0, 123, 255, 0.9)',
    color: 'white',
    padding: '6px 12px',
    borderRadius: '20px',
    fontSize: '12px',
    fontWeight: '600',
  } as React.CSSProperties,
  photoActions: {
    padding: '12px',
    display: 'flex',
    gap: '8px',
  } as React.CSSProperties,
  viewButton: {
    flex: 1,
    padding: '10px',
    fontSize: '14px',
    color: '#007bff',
    backgroundColor: 'transparent',
    border: '1px solid #007bff',
    borderRadius: '4px',
    cursor: 'pointer',
  } as React.CSSProperties,
  downloadButton: {
    flex: 1,
    padding: '10px',
    fontSize: '14px',
    color: 'white',
    backgroundColor: '#28a745',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
  } as React.CSSProperties,
  modal: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.9)',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 1000,
    padding: '20px',
  } as React.CSSProperties,
  modalContent: {
    position: 'relative',
    maxWidth: '90vw',
    maxHeight: '90vh',
    backgroundColor: 'white',
    borderRadius: '8px',
    overflow: 'hidden',
  } as React.CSSProperties,
  closeButton: {
    position: 'absolute',
    top: '10px',
    right: '10px',
    width: '40px',
    height: '40px',
    fontSize: '24px',
    color: 'white',
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    border: 'none',
    borderRadius: '50%',
    cursor: 'pointer',
    zIndex: 1001,
  } as React.CSSProperties,
  modalImage: {
    width: '100%',
    height: 'auto',
    maxHeight: 'calc(90vh - 80px)',
    objectFit: 'contain',
  } as React.CSSProperties,
  modalActions: {
    padding: '16px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#f8f9fa',
  } as React.CSSProperties,
  modalSimilarity: {
    fontSize: '16px',
    fontWeight: '600',
    color: '#007bff',
  } as React.CSSProperties,
  modalDownloadButton: {
    padding: '10px 20px',
    fontSize: '14px',
    fontWeight: '600',
    color: 'white',
    backgroundColor: '#28a745',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
  } as React.CSSProperties,
}
