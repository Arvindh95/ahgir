import { useState, useRef, DragEvent } from 'react'
import { photoService, UploadResult } from '@/lib/photos'

interface PhotoUploadProps {
  eventId: string
  onUploadComplete: () => void
}

export default function PhotoUpload({ eventId, onUploadComplete }: PhotoUploadProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null)
  const [error, setError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleDragEnter = (e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)

    const files = Array.from(e.dataTransfer.files).filter(
      (file) => file.type === 'image/jpeg' || file.type === 'image/png'
    )
    setSelectedFiles(files)
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files).filter(
        (file) => file.type === 'image/jpeg' || file.type === 'image/png'
      )
      setSelectedFiles(files)
    }
  }

  const handleUpload = async () => {
    if (selectedFiles.length === 0) {
      setError('Please select files to upload')
      return
    }

    setIsUploading(true)
    setError('')
    setUploadProgress(0)

    try {
      // Simulate progress (in real app, use axios onUploadProgress)
      const progressInterval = setInterval(() => {
        setUploadProgress((prev) => Math.min(prev + 10, 90))
      }, 200)

      const result = await photoService.uploadPhotos(eventId, selectedFiles)
      
      clearInterval(progressInterval)
      setUploadProgress(100)
      setUploadResult(result)
      setSelectedFiles([])
      
      setTimeout(() => {
        onUploadComplete()
      }, 1000)
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Upload failed')
    } finally {
      setIsUploading(false)
    }
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  }

  return (
    <div style={{ backgroundColor: 'white', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
      <h2 style={{ marginTop: 0 }}>Upload Photos</h2>

      <div
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        style={{
          border: `2px dashed ${isDragging ? '#0070f3' : '#ddd'}`,
          borderRadius: '8px',
          padding: '40px',
          textAlign: 'center',
          cursor: 'pointer',
          backgroundColor: isDragging ? '#f0f8ff' : '#fafafa',
          marginBottom: '20px',
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/jpeg,image/png"
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />
        <p style={{ fontSize: '18px', marginBottom: '10px' }}>
          {isDragging ? 'Drop files here' : 'Drag and drop photos here'}
        </p>
        <p style={{ color: '#666', fontSize: '14px' }}>or click to select files</p>
        <p style={{ color: '#999', fontSize: '12px', marginTop: '10px' }}>
          Supported formats: JPEG, PNG
        </p>
      </div>

      {selectedFiles.length > 0 && (
        <div style={{ marginBottom: '20px' }}>
          <h3>Selected Files ({selectedFiles.length})</h3>
          <div style={{ maxHeight: '200px', overflowY: 'auto', border: '1px solid #ddd', borderRadius: '4px', padding: '10px' }}>
            {selectedFiles.map((file, index) => (
              <div
                key={index}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: '8px',
                  borderBottom: index < selectedFiles.length - 1 ? '1px solid #eee' : 'none',
                }}
              >
                <span style={{ fontSize: '14px' }}>{file.name}</span>
                <span style={{ fontSize: '14px', color: '#666' }}>{formatFileSize(file.size)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {isUploading && (
        <div style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}>
            <span>Uploading...</span>
            <span>{uploadProgress}%</span>
          </div>
          <div style={{ width: '100%', height: '20px', backgroundColor: '#e0e0e0', borderRadius: '10px', overflow: 'hidden' }}>
            <div
              style={{
                width: `${uploadProgress}%`,
                height: '100%',
                backgroundColor: '#0070f3',
                transition: 'width 0.3s',
              }}
            />
          </div>
        </div>
      )}

      {error && (
        <div style={{ color: 'red', marginBottom: '20px', padding: '10px', backgroundColor: '#ffebee', borderRadius: '4px' }}>
          {error}
        </div>
      )}

      {uploadResult && (
        <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#e8f5e9', borderRadius: '4px' }}>
          <p style={{ margin: '0 0 10px 0', fontWeight: 'bold', color: '#28a745' }}>
            Upload Complete!
          </p>
          <p style={{ margin: '0 0 5px 0', fontSize: '14px' }}>
            Uploaded: {uploadResult.uploaded.length} photos
          </p>
          {uploadResult.duplicates.length > 0 && (
            <p style={{ margin: '0', fontSize: '14px', color: '#ff9800' }}>
              Duplicates skipped: {uploadResult.duplicates.length}
            </p>
          )}
        </div>
      )}

      <button
        onClick={handleUpload}
        disabled={selectedFiles.length === 0 || isUploading}
        style={{
          width: '100%',
          padding: '12px',
          backgroundColor: selectedFiles.length === 0 || isUploading ? '#ccc' : '#0070f3',
          color: 'white',
          border: 'none',
          borderRadius: '4px',
          cursor: selectedFiles.length === 0 || isUploading ? 'not-allowed' : 'pointer',
          fontSize: '16px',
        }}
      >
        {isUploading ? 'Uploading...' : `Upload ${selectedFiles.length} Photo${selectedFiles.length !== 1 ? 's' : ''}`}
      </button>
    </div>
  )
}
