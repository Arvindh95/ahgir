import { useState, useRef, useEffect, useCallback } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import axios from 'axios'
import { Camera, Upload, LogOut, Loader2, ScanFace, Image as ImageIcon } from 'lucide-react'
import ScannerOnboarding from '@/components/ScannerOnboarding'

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
  // Live head-yaw estimate: -1 (turned to one side) ... 0 (straight) ... +1 (other side).
  // Computed each detection tick from the 68-point face landmarks.
  const yawRef = useRef<number>(0)

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
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [scanPhase, setScanPhase] = useState<string | null>(null) // guided capture phase text
  const [poseProgress, setPoseProgress] = useState<{ side: 'straight' | 'left' | 'right' | null; hit: boolean }>({ side: null, hit: false })
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Load @vladmandic/face-api models
  useEffect(() => {
    const loadFaceApi = async () => {
      try {
        // Dynamically import face-api (browser-only). Vladmandic's fork is
        // API-compatible with the original face-api.js but drops the
        // node-fetch / @tensorflow/tfjs-core dependency chain that pinned us
        // to the legacy package.
        const faceapi = await import('@vladmandic/face-api')
        faceApiRef.current = faceapi

        // Load models from CDN
        const MODEL_URL = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model'

        await Promise.all([
          faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
          faceapi.nets.faceLandmark68TinyNet.loadFromUri(MODEL_URL),
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

    // Detection loop. Runs face detection + 68-point landmarks so we can
    // estimate head yaw (rotation left/right) for pose-gated capture.
    const detect = async () => {
      if (!video || video.paused || video.ended) return

      try {
        const result = await faceapi
          .detectSingleFace(
            video,
            new faceapi.TinyFaceDetectorOptions({
              inputSize: 320,
              scoreThreshold: 0.5,
            })
          )
          .withFaceLandmarks(true) // tiny landmark model

        const ctx = overlayCanvas.getContext('2d')
        if (ctx) ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height)

        if (result) {
          setFaceDetected(true)
          lastDetectionRef.current = result.detection

          // Yaw heuristic from 68-point landmarks:
          //   point 30  = nose tip
          //   point 0   = left jaw corner
          //   point 16  = right jaw corner
          // When the head turns, the nose tip drifts toward one jaw corner.
          // yaw_score = (right_dist - left_dist) / face_width
          //   ~0      → looking straight ahead
          //   negative → turned toward one side
          //   positive → turned toward the other side
          // We don't label "left" vs "right" semantically because the camera
          // is mirrored on most devices; what matters is the SIGN to ensure
          // the second and third frames are on opposite sides.
          try {
            const lm = result.landmarks.positions
            const nose = lm[30]
            const leftJaw = lm[0]
            const rightJaw = lm[16]
            const leftDist = Math.abs(nose.x - leftJaw.x)
            const rightDist = Math.abs(nose.x - rightJaw.x)
            const faceWidth = Math.abs(rightJaw.x - leftJaw.x) || 1
            yawRef.current = (rightDist - leftDist) / faceWidth
          } catch {
            yawRef.current = 0
          }
        } else {
          setFaceDetected(false)
          lastDetectionRef.current = null
          yawRef.current = 0
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
      console.error('Camera error:', err)
      if (err.name === 'NotAllowedError') {
        setError('Camera access was denied. Please allow camera access in your browser settings (look for the camera icon in the address bar), then reload the page.')
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setError('No camera found on this device. You can use the Upload option instead.')
      } else {
        setError('Failed to access camera. Try using the Upload option instead.')
      }
      setUseUpload(true)
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

      let primaryImage: string | null = null
      let additionalFrames: string[] = []

      if (useUpload) {
        // Use uploaded file (single frame)
        const file = fileInputRef.current?.files?.[0]
        if (!file) {
          setError('Please select an image file')
          setScanning(false)
          return
        }

        primaryImage = await new Promise((resolve) => {
          const reader = new FileReader()
          reader.onload = () => resolve(reader.result as string)
          reader.readAsDataURL(file)
        })
      } else {
        // Pose-gated multi-angle capture: wait for the user to actually
        // hit each pose target before snapping. Falls back to capturing
        // whatever pose they're in after a per-phase timeout, so users
        // who can't or won't turn still get something usable.
        //
        // Yaw thresholds:
        //   |yaw| < STRAIGHT_THRESH → looking ahead
        //   yaw  >  TURN_THRESH     → turned toward "+" side
        //   yaw  < -TURN_THRESH     → turned toward "-" side
        const STRAIGHT_THRESH = 0.10
        const TURN_THRESH = 0.18
        const HOLD_TICKS = 3 // require 3 consecutive ticks (=300ms) within target to avoid jitter capture
        const MAX_WAIT_MS = 6000
        const POLL_MS = 100

        const waitForPose = async (
          test: (yaw: number) => boolean,
          label: string,
          side: 'straight' | 'left' | 'right',
        ): Promise<void> => {
          setScanPhase(label)
          setPoseProgress({ side, hit: false })
          const start = Date.now()
          let consecutive = 0
          while (Date.now() - start < MAX_WAIT_MS) {
            // Use the ref, not the React state — closures over `faceDetected`
            // would freeze at the value at handleScan invocation time.
            if (lastDetectionRef.current) {
              if (test(yawRef.current)) {
                consecutive += 1
                if (consecutive >= HOLD_TICKS) {
                  setPoseProgress({ side, hit: true })
                  // Brief flash so the user sees the check before we snap.
                  await new Promise(r => setTimeout(r, 150))
                  return
                }
              } else {
                consecutive = 0
              }
            }
            await new Promise(r => setTimeout(r, POLL_MS))
          }
          // Timeout — capture whatever we have.
          setPoseProgress({ side, hit: false })
        }

        const frames: string[] = []
        // 1. Straight on
        await waitForPose(y => Math.abs(y) < STRAIGHT_THRESH, 'Look straight ahead', 'straight')
        let f = captureFrame()
        if (f) frames.push(f)

        // 2. First side — whichever direction the user naturally turns first
        let firstSideSign = 0
        await waitForPose(
          y => {
            if (Math.abs(y) > TURN_THRESH) {
              firstSideSign = y > 0 ? 1 : -1
              return true
            }
            return false
          },
          'Turn your head slowly to one side',
          'right',
        )
        f = captureFrame()
        if (f) frames.push(f)

        // 3. Opposite side — whatever the OTHER direction is
        const otherSign = firstSideSign === 0 ? -1 : -firstSideSign
        await waitForPose(
          y => Math.abs(y) > TURN_THRESH && Math.sign(y) === otherSign,
          'Now turn the other way',
          'left',
        )
        f = captureFrame()
        if (f) frames.push(f)

        setScanPhase('Matching...')
        setPoseProgress({ side: null, hit: false })

        if (frames.length === 0) {
          setError('Failed to capture frames from camera')
          setScanning(false)
          setScanPhase(null)
          return
        }

        primaryImage = frames[0]
        additionalFrames = frames.slice(1)
      }

      if (!primaryImage) {
        setError('Failed to get image data')
        setScanning(false)
        setScanPhase(null)
        return
      }

      // Send all frames to backend
      const token = localStorage.getItem('event_token')
      const payload: any = {
        image: primaryImage.includes(',') ? primaryImage.split(',')[1] : primaryImage,
      }
      if (additionalFrames.length > 0) {
        payload.additional_frames = additionalFrames.map(f =>
          f.includes(',') ? f.split(',')[1] : f
        )
      }

      const response = await axios.post(
        `${API_URL}/scan`,
        payload,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      )

      setScanResult(response.data)
      setScanPhase(null)

      // Store results in localStorage for results page
      localStorage.setItem('scan_results', JSON.stringify(response.data))

      // Navigate to results
      router.push(`/e/${slug}/results`)

    } catch (err: any) {
      setScanPhase(null)
      if (err.response?.status === 429) {
        setError('Rate limit exceeded. Please wait before scanning again.')
      } else if (err.response?.status === 401) {
        setError('Session expired. Please authenticate again.')
        localStorage.removeItem('event_token')
        router.push(`/e/${slug}`)
      } else {
        const msg = err.response?.data?.error?.message?.toLowerCase() || ''
        if (msg.includes('no face') || msg.includes('face could not') || msg.includes('face not')) {
          setError('No face detected. Try removing sunglasses, improving lighting, and facing the camera directly.')
        } else if (msg) {
          setError(err.response.data.error.message)
        } else {
          setError('Scan failed. Please try again.')
        }
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
    <div className="min-h-screen relative overflow-hidden bg-black text-white">
      <Head><title>Scan - PicUr</title></Head>
      <ScannerOnboarding />
      {/* Background Ambience */}
      <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-black via-[#0a0a0a] to-[#050505] z-0"></div>
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-500/10 rounded-full blur-[120px] z-0"></div>

      <div className="relative z-10 max-w-4xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex justify-between items-center mb-8 glass-card p-4 rounded-xl">
          <h1 className="text-xl font-bold truncate pr-4">{eventName}</h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => router.push(`/e/${slug}/gallery`)}
              className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors flex items-center gap-2"
            >
              <ImageIcon className="w-5 h-5" />
              <span className="hidden sm:inline">Gallery</span>
            </button>
            <button
              onClick={handleLogout}
              className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors flex items-center gap-2"
            >
              <LogOut className="w-5 h-5" />
              <span className="hidden sm:inline">Exit</span>
            </button>
          </div>
        </div>

        <div className="glass-card p-6 md:p-8 rounded-2xl">
          {/* Mode Toggle */}
          <div className="flex justify-center gap-4 mb-8">
            <button
              onClick={() => setUseUpload(false)}
              className={`flex items-center gap-2 px-6 py-3 rounded-xl font-medium transition-all ${!useUpload
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20'
                  : 'bg-white/5 text-gray-400 hover:bg-white/10'
                }`}
            >
              <Camera className="w-5 h-5" />
              Camera
            </button>
            <button
              onClick={() => setUseUpload(true)}
              className={`flex items-center gap-2 px-6 py-3 rounded-xl font-medium transition-all ${useUpload
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20'
                  : 'bg-white/5 text-gray-400 hover:bg-white/10'
                }`}
            >
              <Upload className="w-5 h-5" />
              Upload
            </button>
          </div>

          {!useUpload ? (
            <div className={`
                relative rounded-xl overflow-hidden aspect-[4/3] md:aspect-video bg-black shadow-2xl mb-6 border-4
                ${faceDetected ? 'border-green-500 shadow-[0_0_20px_rgba(34,197,94,0.5)]' : 'border-transparent'}
                transition-all duration-300
              `}>
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-cover scale-x-[-1]"
              />
              <canvas
                ref={overlayCanvasRef}
                className="absolute top-0 left-0 w-full h-full pointer-events-none scale-x-[-1]"
              />
              <canvas ref={canvasRef} style={{ display: 'none' }} />

              {/* Guided scan phase overlay (pose-gated) */}
              {scanPhase && scanning && (
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
                  <div
                    className={`px-6 py-3 rounded-2xl backdrop-blur-md border text-white font-bold text-lg shadow-lg flex items-center gap-2 transition-colors ${
                      poseProgress.hit
                        ? 'bg-green-600/85 border-green-400/60'
                        : 'bg-blue-600/80 border-blue-400/50 animate-pulse'
                    }`}
                  >
                    {poseProgress.hit ? <span className="text-2xl leading-none">✓</span> : null}
                    <span>{scanPhase}</span>
                  </div>
                </div>
              )}

              {/* Status indicator - Moved to be subtle and non-blocking */}
              <div className="absolute bottom-4 left-0 w-full flex justify-center pointer-events-none">
                {loadingModels ? (
                  <div className="px-4 py-2 rounded-full backdrop-blur-md bg-black/60 border border-white/10 flex items-center gap-2 text-yellow-500 font-semibold text-sm">
                    <Loader2 className="w-4 h-4 animate-spin" /> Loading AI models...
                  </div>
                ) : !cameraReady ? (
                  <div className="px-4 py-2 rounded-full backdrop-blur-md bg-black/60 border border-white/10 flex items-center gap-2 text-yellow-500 font-semibold text-sm">
                    <Loader2 className="w-4 h-4 animate-spin" /> Starting camera...
                  </div>
                ) : faceDetected ? (
                  // Face detected, green frame is the main indicator, show minimal text
                  <div className="px-4 py-2 rounded-full backdrop-blur-md bg-green-500/20 border border-green-500/50 flex items-center gap-2 text-green-400 font-bold text-sm shadow-lg">
                    <ScanFace className="w-4 h-4" /> Ready to Scan
                  </div>
                ) : (
                  <div className="px-4 py-2 rounded-full backdrop-blur-md bg-black/60 border border-white/10 text-gray-300 font-medium text-sm">
                    Position your face in the frame
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="border-2 border-dashed border-white/10 rounded-xl p-12 mb-6 text-center hover:border-white/20 transition-colors bg-white/5">
              <input
                type="file"
                ref={fileInputRef}
                accept="image/*"
                onChange={(e) => {
                  if (e.target.files?.[0]) {
                    setError('')
                    setFileSelected(true)
                    if (previewUrl) URL.revokeObjectURL(previewUrl)
                    setPreviewUrl(URL.createObjectURL(e.target.files[0]))
                  } else {
                    setFileSelected(false)
                    if (previewUrl) URL.revokeObjectURL(previewUrl)
                    setPreviewUrl(null)
                  }
                }}
                className="hidden"
                id="file-upload"
              />
              {previewUrl ? (
                <div className="flex flex-col items-center gap-4">
                  <div className="relative rounded-xl overflow-hidden aspect-[4/3] max-w-sm w-full mx-auto">
                    <img src={previewUrl} alt="Selected photo" className="w-full h-full object-cover" />
                  </div>
                  <p className="text-gray-400 text-sm">{fileInputRef.current?.files?.[0]?.name}</p>
                  <label htmlFor="file-upload" className="cursor-pointer bg-white/10 text-white px-6 py-2 rounded-lg font-medium hover:bg-white/20 transition-colors">
                    Change Photo
                  </label>
                </div>
              ) : (
                <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center gap-4">
                  <div className="w-20 h-20 rounded-full bg-white/5 flex items-center justify-center">
                    <ImageIcon className="w-10 h-10 text-gray-400" />
                  </div>
                  <div>
                    <p className="text-xl font-semibold mb-2 text-white">Select a photo</p>
                    <p className="text-gray-400 text-sm">JPG or PNG with your face visible</p>
                  </div>
                  <div className="bg-white/10 text-white px-6 py-2 rounded-lg font-medium hover:bg-white/20 transition-colors">
                    Browse Files
                  </div>
                </label>
              )}
            </div>
          )}

          {error && (
            <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl text-center">
              {error}
            </div>
          )}

          {/* Action Button - Moved ABOVE instructions */}
          <button
            onClick={handleScan}
            disabled={!canScan || scanning}
            className={`w-full py-4 rounded-xl text-lg font-bold flex items-center justify-center gap-2 transition-all mb-8 ${!canScan || scanning
                ? 'bg-white/10 text-gray-500 cursor-not-allowed'
                : 'bg-gradient-to-r from-blue-600 to-blue-500 text-white hover:shadow-lg hover:shadow-blue-500/30 hover:scale-[1.02] active:scale-[0.98]'
              }`}
          >
            {scanning ? (
              <>
                <Loader2 className="w-6 h-6 animate-spin" /> {scanPhase || 'Scanning...'}
              </>
            ) : (
              <>
                <ScanFace className="w-6 h-6" /> {faceDetected || useUpload ? 'Scan My Face' : 'Waiting for face...'}
              </>
            )}
          </button>

          {/* Instructions */}
          <div className="bg-white/5 rounded-xl p-6 border border-white/5">
            <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
              <ScanFace className="w-5 h-5 text-blue-400" /> How to scan
            </h2>
            <ol className="list-decimal list-inside space-y-2 text-gray-300 ml-2">
              <li>Position your face clearly in the frame and wait for the green border</li>
              <li>Click <span className="text-white font-medium">&quot;Scan My Face&quot;</span></li>
              <li>The app will guide you through three quick captures:
                <ul className="list-disc list-inside ml-5 mt-1 space-y-1 text-gray-400">
                  <li><span className="text-white">Look straight ahead</span> — hold for a moment</li>
                  <li><span className="text-white">Turn your head slowly to one side</span></li>
                  <li><span className="text-white">Turn the other way</span></li>
                </ul>
              </li>
              <li className="text-gray-400">If you can&apos;t turn, just hold still — the scan still works with one angle, you&apos;ll just match fewer photos.</li>
            </ol>
          </div>

        </div>
      </div>
    </div>
  )
}
