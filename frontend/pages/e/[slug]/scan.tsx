import { useState, useRef, useEffect, useCallback } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

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

interface FaceDetection {
  box: {
    x: number
    y: number
    width: number
    height: number
  }
}

export default function FaceScanner() {
  const router = useRouter()
  const { slug } = router.query

  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null)
  const faceApiRef = useRef<any>(null)
  const detectionIntervalRef = useRef<number | null>(null)
  const lastDetectionRef = useRef<any>(null)

  const [stream, setStream] = useState<MediaStream | null>(null)
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState('')
  const [eventName, setEventName] = useState('')
  const [allowDownloads, setAllowDownloads] = useState(false)
  const [scanResult, setScanResult] = useState<ScanResult | null>(null)
  const [cameraReady, setCameraReady] = useState(false)
  const [useUpload, setUseUpload] = useState(false)
  const [faceDetected, setFaceDetected] = useState(false)
  const [modelsLoaded, setModelsLoaded] = useState(false)
  const [loadingModels, setLoadingModels] = useState(true)
  const [fileSelected, setFileSelected] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Load face-api.js models
  useEffect(() => {
    const loadFaceApi = async () => {
      try {
        // Dynamically import face-api.js (only works in browser)
        const faceapi = await import('face-api.js')
        faceApiRef.current = faceapi

        // Load models from CDN
        const MODEL_URL = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model'

        await Promise.all([
          faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
        ])

        setModelsLoaded(true)
        setLoadingModels(false)
        console.log('Face detection models loaded')
      } catch (err) {
        console.error('Failed to load face-api models:', err)
        setLoadingModels(false)
        // Continue without client-side detection
      }
    }

    loadFaceApi()
  }, [])

  useEffect(() => {
    // Check authentication
    const token = localStorage.getItem('event_token')
    const storedEventName = localStorage.getItem('event_name')
    const storedAllowDownloads = localStorage.getItem('allow_downloads')

    if (!token) {
      router.push(`/e/${slug}`)
      return
    }

    setEventName(storedEventName || '')
    setAllowDownloads(storedAllowDownloads === 'true')

    // Initialize camera
    initializeCamera()

    return () => {
      if (stream) {
        stream.getTracks().forEach(track => track.stop())
      }
      if (detectionIntervalRef.current) {
        clearInterval(detectionIntervalRef.current)
      }
    }
  }, [slug, router])

  // Start face detection loop when camera and models are ready
  useEffect(() => {
    if (cameraReady && modelsLoaded && !useUpload && videoRef.current) {
      startFaceDetection()
    }

    return () => {
      if (detectionIntervalRef.current) {
        clearInterval(detectionIntervalRef.current)
      }
    }
  }, [cameraReady, modelsLoaded, useUpload])

  const startFaceDetection = useCallback(() => {
    if (!faceApiRef.current || !videoRef.current || !overlayCanvasRef.current) return

    const faceapi = faceApiRef.current
    const video = videoRef.current
    const overlayCanvas = overlayCanvasRef.current

    // Match canvas size to video display size
    const updateCanvasSize = () => {
      if (video.videoWidth && video.videoHeight) {
        overlayCanvas.width = video.videoWidth
        overlayCanvas.height = video.videoHeight
      }
    }

    updateCanvasSize()

    // Detection loop
    const detect = async () => {
      if (!video || video.paused || video.ended) return

      try {
        const detections = await faceapi.detectAllFaces(
          video,
          new faceapi.TinyFaceDetectorOptions({
            inputSize: 320,
            scoreThreshold: 0.5
          })
        )

        // Draw on overlay canvas
        const ctx = overlayCanvas.getContext('2d')
        if (ctx) {
          ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height)

          if (detections.length > 0) {
            setFaceDetected(true)
            // Store the first detected face for cropping later
            lastDetectionRef.current = detections[0]

            // Draw green box around detected face
            detections.forEach((detection: any) => {
              const box = detection.box
              ctx.strokeStyle = '#00ff00'
              ctx.lineWidth = 3
              ctx.strokeRect(box.x, box.y, box.width, box.height)

              // Draw label
              ctx.fillStyle = '#00ff00'
              ctx.font = '16px Arial'
              ctx.fillText('Face detected', box.x, box.y - 5)
            })
          } else {
            setFaceDetected(false)
            lastDetectionRef.current = null
          }
        }
      } catch (err) {
        console.error('Face detection error:', err)
      }
    }

    // Run detection every 200ms
    detectionIntervalRef.current = window.setInterval(detect, 200)
  }, [])

  const initializeCamera = async () => {
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'user',
          width: { ideal: 1280 },
          height: { ideal: 720 }
        }
      })

      setStream(mediaStream)

      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream
        videoRef.current.onloadedmetadata = () => {
          setCameraReady(true)
        }
      }

      setError('')
    } catch (err: any) {
      setError('Failed to access camera. Please grant camera permissions.')
      console.error('Camera error:', err)
    }
  }

  const captureFrame = (): string | null => {
    if (!videoRef.current || !canvasRef.current) return null

    const video = videoRef.current
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return null

    // If we have a face detection, crop just the face region with padding
    if (lastDetectionRef.current) {
      const box = lastDetectionRef.current.box
      // Add 50% padding around face for better detection
      const padding = Math.max(box.width, box.height) * 0.5
      const x = Math.max(0, box.x - padding)
      const y = Math.max(0, box.y - padding)
      const width = Math.min(video.videoWidth - x, box.width + padding * 2)
      const height = Math.min(video.videoHeight - y, box.height + padding * 2)

      // Set canvas to cropped size (but at least 400x400 for quality)
      const minSize = 400
      const scale = Math.max(minSize / width, minSize / height, 1)
      canvas.width = width * scale
      canvas.height = height * scale

      // Draw only the face region, scaled up
      ctx.drawImage(
        video,
        x, y, width, height,  // Source rectangle
        0, 0, canvas.width, canvas.height  // Destination rectangle
      )

      console.log(`Captured face crop: ${canvas.width}x${canvas.height} from region (${Math.round(x)},${Math.round(y)},${Math.round(width)},${Math.round(height)})`)
    } else {
      // Fallback: capture full frame
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    }

    // Convert to base64
    return canvas.toDataURL('image/jpeg', 0.9)
  }

  const handleScan = async () => {
    if (scanning) return
    if (!useUpload && !cameraReady) return

    try {
      setScanning(true)
      setError('')
      setScanResult(null)

      let imageData: string | null = null

      if (useUpload) {
        // Use uploaded file
        const file = fileInputRef.current?.files?.[0]
        if (!file) {
          setError('Please select an image file')
          setScanning(false)
          return
        }

        imageData = await new Promise((resolve) => {
          const reader = new FileReader()
          reader.onload = () => resolve(reader.result as string)
          reader.readAsDataURL(file)
        })
      } else {
        // Capture from camera - capture 1-3 frames
        const frames: string[] = []
        for (let i = 0; i < 3; i++) {
          const frame = captureFrame()
          if (frame) {
            frames.push(frame)
          }
          // Small delay between captures
          await new Promise(resolve => setTimeout(resolve, 200))
        }

        if (frames.length === 0) {
          setError('Failed to capture frames from camera')
          setScanning(false)
          return
        }

        imageData = frames[0]
      }

      if (!imageData) {
        setError('Failed to get image data')
        setScanning(false)
        return
      }

      // Send first frame to backend (can be enhanced to send all frames)
      const token = localStorage.getItem('event_token')

      const response = await axios.post(
        `${API_URL}/scan`,
        { image: imageData.split(',')[1] }, // Remove data:image/jpeg;base64, prefix
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      )

      setScanResult(response.data)

      // Store results in localStorage for results page
      localStorage.setItem('scan_results', JSON.stringify(response.data))

      // Navigate to results
      router.push(`/e/${slug}/results`)

    } catch (err: any) {
      if (err.response?.status === 429) {
        setError('Rate limit exceeded. Please wait before scanning again.')
      } else if (err.response?.status === 401) {
        setError('Session expired. Please authenticate again.')
        localStorage.removeItem('event_token')
        router.push(`/e/${slug}`)
      } else if (err.response?.data?.error?.message) {
        setError(err.response.data.error.message)
      } else {
        setError('Failed to scan face. Please try again.')
      }
      console.error('Scan error:', err)
    } finally {
      setScanning(false)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('event_token')
    localStorage.removeItem('event_id')
    localStorage.removeItem('event_name')
    localStorage.removeItem('allow_downloads')

    if (stream) {
      stream.getTracks().forEach(track => track.stop())
    }

    if (detectionIntervalRef.current) {
      clearInterval(detectionIntervalRef.current)
    }

    router.push(`/e/${slug}`)
  }

  // Determine if scan button should be enabled
  const canScan = useUpload
    ? fileSelected
    : (cameraReady && (faceDetected || !modelsLoaded))

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.title}>{eventName}</h1>
        <button onClick={handleLogout} style={styles.logoutButton}>
          Exit
        </button>
      </div>

      <div style={styles.content}>
        <div style={styles.modeToggle}>
          <button
            onClick={() => setUseUpload(false)}
            style={{
              ...styles.modeButton,
              ...(useUpload ? {} : styles.modeButtonActive)
            }}
          >
            Use Camera
          </button>
          <button
            onClick={() => setUseUpload(true)}
            style={{
              ...styles.modeButton,
              ...(!useUpload ? {} : styles.modeButtonActive)
            }}
          >
            Upload Photo
          </button>
        </div>

        {!useUpload ? (
          <div style={styles.videoContainer}>
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              style={styles.video}
            />
            <canvas
              ref={overlayCanvasRef}
              style={styles.overlayCanvas}
            />
            <canvas ref={canvasRef} style={{ display: 'none' }} />

            {/* Status indicator */}
            <div style={styles.statusIndicator}>
              {loadingModels ? (
                <span style={styles.statusLoading}>Loading face detection...</span>
              ) : !cameraReady ? (
                <span style={styles.statusLoading}>Initializing camera...</span>
              ) : faceDetected ? (
                <span style={styles.statusSuccess}>Face detected - Ready to scan!</span>
              ) : (
                <span style={styles.statusWarning}>Position your face in the frame</span>
              )}
            </div>

            {!cameraReady && !error && (
              <div style={styles.overlay}>
                <p>Initializing camera...</p>
              </div>
            )}
          </div>
        ) : (
          <div style={styles.uploadContainer}>
            <input
              type="file"
              ref={fileInputRef}
              accept="image/*"
              style={styles.fileInput}
              onChange={(e) => {
                if (e.target.files?.[0]) {
                  setError('')
                  setFileSelected(true)
                } else {
                  setFileSelected(false)
                }
              }}
            />
            <p style={styles.uploadText}>Select a photo with your face</p>
          </div>
        )}

        <div style={styles.instructions}>
          <h2 style={styles.instructionsTitle}>How to scan:</h2>
          <ol style={styles.instructionsList}>
            <li>Position your face in the camera frame</li>
            <li>Wait for the green "Face detected" indicator</li>
            <li>Click the "Scan My Face" button</li>
            <li>Wait while we search for your photos</li>
          </ol>
        </div>

        {error && (
          <div style={styles.errorBox}>
            <p style={styles.error}>{error}</p>
          </div>
        )}

        <button
          onClick={handleScan}
          disabled={!canScan || scanning}
          style={{
            ...styles.scanButton,
            ...((!canScan || scanning) && styles.scanButtonDisabled)
          }}
        >
          {scanning ? 'Scanning...' : faceDetected || useUpload ? 'Scan My Face' : 'Waiting for face...'}
        </button>
      </div>
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
    maxWidth: '1200px',
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
  logoutButton: {
    padding: '8px 16px',
    fontSize: '14px',
    color: '#666',
    backgroundColor: 'transparent',
    border: '1px solid #ddd',
    borderRadius: '4px',
    cursor: 'pointer',
  } as React.CSSProperties,
  content: {
    maxWidth: '1200px',
    margin: '0 auto',
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
  } as React.CSSProperties,
  modeToggle: {
    display: 'flex',
    gap: '10px',
    justifyContent: 'center',
  } as React.CSSProperties,
  modeButton: {
    padding: '12px 24px',
    fontSize: '16px',
    border: '2px solid #ddd',
    borderRadius: '8px',
    backgroundColor: 'white',
    cursor: 'pointer',
    transition: 'all 0.2s',
  } as React.CSSProperties,
  modeButtonActive: {
    borderColor: '#007bff',
    backgroundColor: '#e7f1ff',
    color: '#007bff',
  } as React.CSSProperties,
  videoContainer: {
    position: 'relative',
    backgroundColor: 'black',
    borderRadius: '8px',
    overflow: 'hidden',
    aspectRatio: '16/9',
    maxHeight: '500px',
  } as React.CSSProperties,
  uploadContainer: {
    backgroundColor: 'white',
    borderRadius: '8px',
    padding: '40px',
    textAlign: 'center',
    border: '2px dashed #ddd',
  } as React.CSSProperties,
  fileInput: {
    fontSize: '16px',
    marginBottom: '10px',
  } as React.CSSProperties,
  uploadText: {
    color: '#666',
    margin: 0,
  } as React.CSSProperties,
  video: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
    transform: 'scaleX(-1)', // Mirror the video for selfie view
  } as React.CSSProperties,
  overlayCanvas: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
    pointerEvents: 'none',
    transform: 'scaleX(-1)', // Mirror to match video
  } as React.CSSProperties,
  statusIndicator: {
    position: 'absolute',
    bottom: '20px',
    left: '50%',
    transform: 'translateX(-50%)',
    padding: '10px 20px',
    borderRadius: '20px',
    fontSize: '14px',
    fontWeight: '600',
    backgroundColor: 'rgba(0,0,0,0.7)',
  } as React.CSSProperties,
  statusLoading: {
    color: '#ffc107',
  } as React.CSSProperties,
  statusSuccess: {
    color: '#00ff00',
  } as React.CSSProperties,
  statusWarning: {
    color: '#ff9800',
  } as React.CSSProperties,
  overlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.7)',
    color: 'white',
    fontSize: '18px',
  } as React.CSSProperties,
  instructions: {
    backgroundColor: 'white',
    padding: '20px',
    borderRadius: '8px',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
  } as React.CSSProperties,
  instructionsTitle: {
    fontSize: '18px',
    fontWeight: 'bold',
    marginBottom: '12px',
    color: '#333',
  } as React.CSSProperties,
  instructionsList: {
    margin: 0,
    paddingLeft: '20px',
    color: '#555',
    lineHeight: '1.8',
  } as React.CSSProperties,
  errorBox: {
    backgroundColor: '#fff3cd',
    border: '1px solid #ffc107',
    borderRadius: '4px',
    padding: '12px',
  } as React.CSSProperties,
  error: {
    color: '#856404',
    margin: 0,
    fontSize: '14px',
  } as React.CSSProperties,
  scanButton: {
    padding: '16px',
    fontSize: '18px',
    fontWeight: '600',
    color: 'white',
    backgroundColor: '#007bff',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  } as React.CSSProperties,
  scanButtonDisabled: {
    backgroundColor: '#ccc',
    cursor: 'not-allowed',
  } as React.CSSProperties,
}
