import { useState, useRef, useEffect, useCallback } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import axios from 'axios'
import api from '@/lib/api'
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
  // Live frame-quality state. Drives the distance gate during pose-confirmed
  // capture and the colored oval guide on the camera preview. Read inside
  // the pose-wait loop, where a React state value would be a stale closure.
  type FrameQuality = 'ok' | 'too_far' | 'too_close' | 'clipped' | 'no_face'
  const frameQualityRef = useRef<FrameQuality>('no_face')
  // Ref-mirror of `stream` state so cleanup functions can stop tracks
  // without depending on a closure over `stream` at the time the
  // effect ran. The init effect runs once on mount when `stream` is
  // still null; reading it from this ref in cleanup gets the latest
  // MediaStream and actually releases the camera on navigation.
  const streamRef = useRef<MediaStream | null>(null)

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
  const [frameQuality, setFrameQuality] = useState<FrameQuality>('no_face')
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
    // Auth state is in the picur_event HttpOnly cookie; JS can't read it.
    // We use the presence of the event_name metadata in sessionStorage
    // (written by [slug].tsx after a successful /auth) as a proxy for
    // "we just authenticated for this event". If it's missing, bounce
    // back to the entry page; the real auth check happens server-side
    // on the next API call.
    const storedEventName = sessionStorage.getItem('event_name')
    const storedAllowDownloads = sessionStorage.getItem('allow_downloads')

    if (!storedEventName) {
      router.push(`/e/${slug}`)
      return
    }

    setEventName(storedEventName || '')
    setAllowDownloads(storedAllowDownloads === 'true')

    // Initialize camera
    initializeCamera()

    return () => {
      // Read from the ref, not the closed-over state. At the time this
      // cleanup function was created, `stream` was null; the ref is
      // updated by initializeCamera once getUserMedia resolves.
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop())
        streamRef.current = null
      }
      if (detectionIntervalRef.current) {
        clearInterval(detectionIntervalRef.current)
        detectionIntervalRef.current = null
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

        // Frame-quality thresholds.
        // AREA_MIN/MAX = bbox area / frame area; outside this band the face
        // is too far (noisy embedding) or too close (clipped padding +
        // wide-angle distortion). EDGE_MARGIN is the fraction of width/height
        // that the bbox must stay inside; touching the edge means the 40%
        // crop padding (matched to the indexer) gets clipped.
        const AREA_MIN = 0.04
        const AREA_MAX = 0.35
        const EDGE_MARGIN = 0.04

        let quality: FrameQuality = 'no_face'

        if (result) {
          setFaceDetected(true)
          lastDetectionRef.current = result.detection

          const box = result.detection.box
          const frameW = overlayCanvas.width || video.videoWidth
          const frameH = overlayCanvas.height || video.videoHeight
          const areaFrac = (box.width * box.height) / (frameW * frameH || 1)
          const marginX = frameW * EDGE_MARGIN
          const marginY = frameH * EDGE_MARGIN
          const clipped =
            box.x < marginX ||
            box.y < marginY ||
            box.x + box.width  > frameW - marginX ||
            box.y + box.height > frameH - marginY

          if (clipped) quality = 'clipped'
          else if (areaFrac < AREA_MIN) quality = 'too_far'
          else if (areaFrac > AREA_MAX) quality = 'too_close'
          else quality = 'ok'

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

        frameQualityRef.current = quality
        setFrameQuality(quality)

        // Target oval. Static position; color reflects current frame quality
        // so the user gets spatial feedback ("am I the right distance from
        // the camera?") without having to read the text prompt.
        if (ctx) {
          const cx = overlayCanvas.width / 2
          const cy = overlayCanvas.height / 2
          const rx = overlayCanvas.width  * 0.20
          const ry = overlayCanvas.height * 0.32
          ctx.lineWidth = Math.max(4, overlayCanvas.width * 0.005)
          ctx.setLineDash([12, 8])
          ctx.strokeStyle =
            quality === 'ok'        ? 'rgba(34, 197, 94, 0.95)'   // green-500
            : quality === 'no_face' ? 'rgba(148, 163, 184, 0.55)' // slate-400, faint
            :                         'rgba(239, 68, 68, 0.95)'   // red-500
          ctx.beginPath()
          ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2)
          ctx.stroke()
          ctx.setLineDash([])
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
      streamRef.current = mediaStream

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
      // 40% padding around the bbox to match the indexer's face_crop_padding_factor
      // on the backend. Probe and gallery crops must use the same context window,
      // otherwise the asymmetry costs a few % of cosine similarity on legitimate
      // matches — which then fall below the 0.90 floor.
      const padding = Math.max(box.width, box.height) * 0.4
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

        const distanceMessage = (q: FrameQuality): string | null => {
          switch (q) {
            case 'too_far':  return 'Move closer'
            case 'too_close': return 'Move back'
            case 'clipped':  return 'Fit your whole face in the oval'
            case 'no_face':  return 'Center your face in the oval'
            default:         return null
          }
        }

        const waitForPose = async (
          test: (yaw: number) => boolean,
          label: string,
          side: 'straight' | 'left' | 'right',
        ): Promise<void> => {
          setScanPhase(label)
          setPoseProgress({ side, hit: false })
          const start = Date.now()
          let consecutive = 0
          let lastShown = label
          while (Date.now() - start < MAX_WAIT_MS) {
            // Use refs, not React state — closures over state values would
            // freeze at the value at handleScan invocation time.
            const quality = frameQualityRef.current
            const distMsg = distanceMessage(quality)
            // Surface distance feedback in the same phase overlay used for
            // pose prompts; revert to the pose prompt once distance is OK.
            const desired = distMsg ?? label
            if (desired !== lastShown) {
              setScanPhase(desired)
              lastShown = desired
            }

            if (lastDetectionRef.current && quality === 'ok' && test(yawRef.current)) {
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
            await new Promise(r => setTimeout(r, POLL_MS))
          }
          // Timeout — capture whatever we have. Consistent with the existing
          // pose-gate fallback: a hard block would punish users in awkward
          // lighting/space who'd otherwise get usable results.
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

      // Send all frames to backend. Auth comes from the picur_event cookie
      // attached automatically (withCredentials: true on the api client).
      const payload: any = {
        image: primaryImage.includes(',') ? primaryImage.split(',')[1] : primaryImage,
      }
      if (additionalFrames.length > 0) {
        payload.additional_frames = additionalFrames.map(f =>
          f.includes(',') ? f.split(',')[1] : f
        )
      }

      const response = await api.post('/scan', payload)

      setScanResult(response.data)
      setScanPhase(null)

      // Hand off to /results via sessionStorage — per-tab, dies on close.
      // Used to be localStorage, which persisted scan matches across tabs
      // and made them readable by any XSS payload on picur.my for as long
      // as the guest didn't clear browser data. The handoff is the only
      // consumer (/results reads it once and removes it), so sessionStorage
      // is functionally equivalent and gives a smaller XSS surface.
      sessionStorage.setItem('scan_results', JSON.stringify(response.data))

      // Release the camera BEFORE routing. Unmount cleanup also stops
      // tracks, but doing it here guarantees the LED is off the moment
      // the user lands on /results — they shouldn't see a "camera
      // active" indicator while browsing their matches.
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop())
        streamRef.current = null
        setStream(null)
      }
      if (detectionIntervalRef.current) {
        clearInterval(detectionIntervalRef.current)
        detectionIntervalRef.current = null
      }

      // Navigate to results
      router.push(`/e/${slug}/results`)

    } catch (err: any) {
      setScanPhase(null)
      if (err.response?.status === 429) {
        setError('Rate limit exceeded. Please wait before scanning again.')
      } else if (err.response?.status === 401) {
        setError('Session expired. Please authenticate again.')
        sessionStorage.removeItem('event_name')
        sessionStorage.removeItem('event_id')
        sessionStorage.removeItem('allow_downloads')
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
    sessionStorage.removeItem('event_id')
    sessionStorage.removeItem('event_name')
    sessionStorage.removeItem('allow_downloads')
    // Cookie is also cleared server-side on the next /e/{slug}/auth call;
    // for an explicit "logout" experience we'd need a /e/logout endpoint.
    // The metadata-wipe + nav back to the entry page is enough for now:
    // any guarded API call after this will 401 against the (still-live)
    // cookie and bounce the user to re-auth.

    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
      setStream(null)
    }

    if (detectionIntervalRef.current) {
      clearInterval(detectionIntervalRef.current)
      detectionIntervalRef.current = null
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
                ) : faceDetected && frameQuality === 'ok' ? (
                  // Face detected and well-framed: green oval + this badge confirm "go".
                  <div className="px-4 py-2 rounded-full backdrop-blur-md bg-green-500/20 border border-green-500/50 flex items-center gap-2 text-green-400 font-bold text-sm shadow-lg">
                    <ScanFace className="w-4 h-4" /> Ready to Scan
                  </div>
                ) : faceDetected ? (
                  // Face detected but distance/framing is off; mirror the in-scan
                  // prompts so users self-correct before hitting Scan.
                  <div className="px-4 py-2 rounded-full backdrop-blur-md bg-amber-500/20 border border-amber-500/50 flex items-center gap-2 text-amber-300 font-semibold text-sm shadow-lg">
                    {frameQuality === 'too_far' && 'Move closer'}
                    {frameQuality === 'too_close' && 'Move back'}
                    {frameQuality === 'clipped' && 'Fit your whole face in the oval'}
                  </div>
                ) : (
                  <div className="px-4 py-2 rounded-full backdrop-blur-md bg-black/60 border border-white/10 text-gray-300 font-medium text-sm">
                    Position your face in the oval
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
