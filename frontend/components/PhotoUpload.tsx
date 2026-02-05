import { useState, useRef, DragEvent } from 'react'
import { photoService, UploadResult } from '@/lib/photos'
import { Upload, X, Check, FileImage, Loader2, AlertCircle } from 'lucide-react'

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

  const handleRemoveFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index))
  }

  const handleUpload = async () => {
    if (selectedFiles.length === 0) {
      setError('Please select files to upload')
      return
    }

    setIsUploading(true)
    setError('')
    setUploadProgress(0)
    setUploadResult(null)

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
    <div className="glass-card rounded-2xl p-6 mb-8">
      <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
        <Upload className="w-5 h-5 text-blue-400" /> Upload Photos
      </h2>

      <div
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`
          border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all duration-200
          ${isDragging 
            ? 'border-blue-500 bg-blue-500/10 scale-[1.01]' 
            : 'border-white/10 bg-white/5 hover:bg-white/10 hover:border-white/20'
          }
        `}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/jpeg,image/png"
          onChange={handleFileSelect}
          className="hidden"
        />
        <div className="flex flex-col items-center gap-4">
          <div className={`p-4 rounded-full ${isDragging ? 'bg-blue-500/20 text-blue-400' : 'bg-white/10 text-gray-400'}`}>
             <Upload className="w-8 h-8" />
          </div>
          <div>
            <p className="text-lg font-semibold text-white mb-2">
              {isDragging ? 'Drop matching files here' : 'Drag and drop photos here'}
            </p>
            <p className="text-gray-400 text-sm mb-2">or click to browse from your computer</p>
            <p className="text-gray-500 text-xs">
              Supported formats: JPEG, PNG
            </p>
          </div>
        </div>
      </div>

      {selectedFiles.length > 0 && (
        <div className="mt-6 animate-in slide-in-from-top-4 duration-300">
          <div className="flex justify-between items-center mb-4">
             <h3 className="font-semibold text-gray-300 flex items-center gap-2">
                <FileImage className="w-4 h-4" /> Selected Files ({selectedFiles.length})
             </h3>
             <button 
               onClick={() => setSelectedFiles([])}
               className="text-xs text-red-400 hover:text-red-300 transition-colors"
             >
               Clear all
             </button>
          </div>
          
          <div className="max-h-60 overflow-y-auto pr-2 space-y-2 custom-scrollbar">
            {selectedFiles.map((file, index) => (
              <div
                key={index}
                className="flex justify-between items-center p-3 rounded-lg bg-white/5 border border-white/5 hover:bg-white/10 transition-colors group"
              >
                <div className="flex items-center gap-3 overflow-hidden">
                  <div className="w-8 h-8 rounded bg-gray-800 flex items-center justify-center flex-shrink-0">
                     <FileImage className="w-4 h-4 text-gray-400" />
                  </div>
                  <div className="flex flex-col overflow-hidden">
                     <span className="text-sm font-medium text-white truncate">{file.name}</span>
                     <span className="text-xs text-gray-500">{formatFileSize(file.size)}</span>
                  </div>
                </div>
                <button 
                  onClick={(e) => { e.stopPropagation(); handleRemoveFile(index); }}
                  className="p-1 rounded-full hover:bg-white/10 text-gray-500 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {isUploading && (
        <div className="mt-6">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-blue-400 font-medium flex items-center gap-2">
               <Loader2 className="w-3 h-3 animate-spin" /> Uploading...
            </span>
            <span className="text-gray-400">{uploadProgress}%</span>
          </div>
          <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-300 ease-out"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        </div>
      )}

      {error && (
        <div className="mt-6 p-4 bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl flex items-start gap-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {uploadResult && (
        <div className="mt-6 p-4 bg-green-500/10 border border-green-500/20 rounded-xl">
          <div className="flex items-center gap-2 mb-2">
             <Check className="w-5 h-5 text-green-400" />
             <p className="font-bold text-green-400">Upload Complete!</p>
          </div>
          <p className="text-sm text-gray-300 ml-7">
            Successfully uploaded <span className="text-white font-medium">{uploadResult.uploaded.length}</span> photos.
          </p>
          {uploadResult.duplicates.length > 0 && (
            <p className="text-sm text-yellow-500/80 ml-7 mt-1">
              {uploadResult.duplicates.length} duplicates were skipped.
            </p>
          )}
        </div>
      )}

      <button
        onClick={handleUpload}
        disabled={selectedFiles.length === 0 || isUploading}
        className={`
          w-full mt-6 py-3 rounded-xl text-lg font-bold flex items-center justify-center gap-2 transition-all
          ${selectedFiles.length === 0 || isUploading 
            ? 'bg-white/5 text-gray-500 cursor-not-allowed border border-white/5' 
            : 'bg-blue-600 text-white hover:bg-blue-700 shadow-lg shadow-blue-600/20 hover:scale-[1.01] active:scale-[0.99]'
          }
        `}
      >
        {isUploading ? (
           <>
              <Loader2 className="w-5 h-5 animate-spin" /> Processing...
           </>
        ) : (
           <>
              <Upload className="w-5 h-5" />
              Upload {selectedFiles.length > 0 ? `${selectedFiles.length} Photo${selectedFiles.length !== 1 ? 's' : ''}` : 'Photos'}
           </>
        )}
      </button>
    </div>
  )
}
