import { useState, useRef, useEffect, useCallback, type CSSProperties } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import axios from 'axios'
import api from '@/lib/api'
import { Camera, Upload, LogOut, Loader2, ScanFace, Image as ImageIcon, HelpCircle, X } from 'lucide-react'
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

  // Guided walkthrough state machine. The scan runs through align → front →
  // left → right → matching, with a brief confirmation flash between each
  // capture. Refs mirror the values so the detection loop (which runs on a
  // setInterval and would close over stale state) and the async waitForPose
  // loop can read them cheaply.
  type ScanStep =
    | 'align'           // step 1: face must center in the oval
    | 'aligned_ok'      // brief confirmation flash before front capture
    | 'capture_front'   // step 2: hold still, looking ahead — snap
    | 'captured_front'  // confirmation flash
    | 'prompt_left'     // step 3a: arrow prompt to turn left
    | 'capture_left'    // step 3b: waiting for pose then snap
    | 'captured_left'   // confirmation flash
    | 'prompt_right'    // step 4a: arrow prompt to turn right
    | 'capture_right'   // step 4b: waiting for pose then snap
    | 'captured_right'  // confirmation flash
    | 'matching'        // backend call
  const [scanStep, setScanStep] = useState<ScanStep | null>(null)
  const scanStepRef = useRef<ScanStep | null>(null)
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
  const [frameQuality, setFrameQuality] = useState<FrameQuality>('no_face')
  // 0..3 — how many of the multi-pose frames have been captured so far. Drives
  // the three progress dots at the top of the camera viewport.
  const [framesCaptured, setFramesCaptured] = useState(0)
  const [showHelp, setShowHelp] = useState(false)
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

  // Camera lifecycle on Camera/Upload toggle. The conditional render
  // unmounts the <video> element when the user flips to Upload, so on
  // flip back its ref is fresh and srcObject is null. Re-attach the
  // existing MediaStream if it's still live; otherwise (first mount,
  // or stream was stopped) ask getUserMedia for a new one.
  useEffect(() => {
    if (useUpload) return
    const video = videoRef.current
    if (!video) return

    const stream = streamRef.current
    const hasLiveStream = !!stream && stream.getTracks().some(t => t.readyState === 'live')

    if (hasLiveStream && stream) {
      if (video.srcObject !== stream) {
        video.srcObject = stream
        // metadata already loaded on the original bind so onloadedmetadata
        // won't refire; mark ready manually so the detection-loop effect picks up.
        setCameraReady(true)
        video.play().catch(() => {})
      }
    } else {
      initializeCamera()
    }
  }, [useUpload])

  // Release the camera when this tab goes background and reacquire on
  // return. Without this, two open picur.my tabs fight over the single
  // camera device and only one shows a live feed. Browsers only allow
  // ONE active getUserMedia consumer per camera; holding the stream in
  // the hidden tab makes the visible tab fail with NotReadableError.
  useEffect(() => {
    if (useUpload) return
    const handleVisibility = () => {
      if (document.hidden) {
        if (streamRef.current) {
          streamRef.current.getTracks().forEach(t => t.stop())
          streamRef.current = null
          setStream(null)
          setCameraReady(false)
        }
        if (detectionIntervalRef.current) {
          clearInterval(detectionIntervalRef.current)
          detectionIntervalRef.current = null
        }
      } else {
        // Tab visible again — kick getUserMedia. If the other tab is still
        // holding the camera the initializeCamera error handler will surface
        // a "Camera in use" message.
        if (!streamRef.current && videoRef.current) {
          initializeCamera()
        }
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [useUpload])

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

    // Match canvas pixel resolution to the live video stream. Important
    // for two reasons: (a) drawing on a 300x150 default canvas that CSS
    // then stretches to fill a portrait viewport elongates the oval, and
    // (b) face-bbox coords come from face-api in video-pixel space, so
    // the canvas must share that coord system for overlay alignment.
    //
    // Called every detect tick (cheap — just two property checks) so the
    // canvas resyncs when the camera is reattached after Upload→Camera
    // toggle: the new <canvas> element starts at the HTML default size
    // until something resizes it.
    const updateCanvasSize = () => {
      if (
        video.videoWidth && video.videoHeight &&
        (overlayCanvas.width !== video.videoWidth || overlayCanvas.height !== video.videoHeight)
      ) {
        overlayCanvas.width = video.videoWidth
        overlayCanvas.height = video.videoHeight
      }
    }

    updateCanvasSize()

    // Detection loop. Runs face detection + 68-point landmarks so we can
    // estimate head yaw (rotation left/right) for pose-gated capture.
    const detect = async () => {
      if (!video || video.paused || video.ended) return
      updateCanvasSize()

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

        // Target oval. Static position; color reflects current frame quality.
        // Only drawn when (a) the user is on the idle preview (no scan running)
        // or (b) we're inside the explicit "align your face" step of the
        // walkthrough. Capture/prompt/confirmation phases hide the oval so the
        // viewport reads as a clean snapshot moment, not a setup screen.
        //
        // Sizing: anchored to min(width, height) with a fixed face-proportion
        // ratio (rx:ry ≈ 3:4). Per-axis percentages would stretch the oval
        // into a tall pill on portrait viewports and a flat puck on wide
        // landscape viewports — neither matches the shape of a human face.
        const step = scanStepRef.current
        const showOval = step === null || step === 'align'
        if (ctx && showOval) {
          const cx = overlayCanvas.width / 2
          const cy = overlayCanvas.height / 2
          const minDim = Math.min(overlayCanvas.width, overlayCanvas.height)
          const rx = minDim * 0.32
          const ry = minDim * 0.42
          ctx.lineWidth = Math.max(4, minDim * 0.006)
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
        setUseUpload(true)
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setError('No camera found on this device. You can use the Upload option instead.')
        setUseUpload(true)
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        // Another tab/app is already using the camera. Don't auto-switch to
        // Upload — the user can close the other tab and toggle back.
        setError('Camera is in use by another tab or app. Close it and tap Camera again to retry.')
      } else {
        setError('Failed to access camera. Try using the Upload option instead.')
        setUseUpload(true)
      }
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
        // Guided walkthrough capture. Runs through align → front → left →
        // right with explicit confirmation flashes between each step. Falls
        // back to capturing whatever pose the user holds after a per-step
        // timeout so users who can't / won't turn still get usable frames.
        //
        // Yaw sign convention (un-mirrored camera frame, ibug-68 landmarks):
        //   yaw  > +TURN_THRESH → user turned head to their RIGHT
        //   yaw  < -TURN_THRESH → user turned head to their LEFT
        //   |yaw| < STRAIGHT_THRESH → looking ahead
        const STRAIGHT_THRESH = 0.10
        const TURN_THRESH = 0.18
        const HOLD_TICKS = 3 // 3 consecutive ticks (~300ms) to avoid jitter capture
        const MAX_WAIT_MS = 6000
        const POLL_MS = 100
        const CONFIRM_FLASH_MS = 700  // duration of the green check overlay
        const PROMPT_HOLD_MS = 600    // arrow prompt visible before yaw-wait begins

        const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

        const setStep = (s: ScanStep) => {
          scanStepRef.current = s
          setScanStep(s)
        }

        const distanceMessage = (q: FrameQuality): string | null => {
          switch (q) {
            case 'too_far':  return 'Move closer'
            case 'too_close': return 'Move back'
            case 'clipped':  return 'Fit your whole face in the frame'
            case 'no_face':  return 'Center your face'
            default:         return null
          }
        }

        const waitForCondition = async (
          test: () => boolean,
          label: string,
          holdTicks: number = HOLD_TICKS,
        ): Promise<void> => {
          setScanPhase(label)
          const start = Date.now()
          let consecutive = 0
          let lastShown = label
          while (Date.now() - start < MAX_WAIT_MS) {
            const quality = frameQualityRef.current
            const distMsg = distanceMessage(quality)
            const desired = distMsg ?? label
            if (desired !== lastShown) {
              setScanPhase(desired)
              lastShown = desired
            }
            if (lastDetectionRef.current && quality === 'ok' && test()) {
              consecutive += 1
              if (consecutive >= holdTicks) return
            } else {
              consecutive = 0
            }
            await sleep(POLL_MS)
          }
          // Timeout — let the caller capture whatever frame we have. Hard-
          // failing here would punish users in awkward lighting / cramped
          // spaces who'd otherwise get usable results.
        }

        const frames: string[] = []
        setFramesCaptured(0)

        // --- Step 1: ALIGN ---
        // Wait for the user to put their face in the oval at the right
        // distance. No yaw constraint — they can be looking anywhere.
        setStep('align')
        await waitForCondition(() => true, 'Center your face in the oval')

        // --- Confirmation flash before front capture ---
        setStep('aligned_ok')
        setScanPhase('Great! Get ready...')
        await sleep(CONFIRM_FLASH_MS)

        // --- Step 2: CAPTURE FRONT ---
        setStep('capture_front')
        await waitForCondition(
          () => Math.abs(yawRef.current) < STRAIGHT_THRESH,
          'Look straight ahead',
        )
        let f = captureFrame()
        if (f) { frames.push(f); setFramesCaptured(1) }
        setStep('captured_front')
        setScanPhase('Front captured')
        await sleep(CONFIRM_FLASH_MS)

        // --- Step 3: PROMPT LEFT then CAPTURE LEFT ---
        setStep('prompt_left')
        setScanPhase('Turn your head to the LEFT')
        await sleep(PROMPT_HOLD_MS)
        setStep('capture_left')
        await waitForCondition(
          () => yawRef.current < -TURN_THRESH,
          'Turn your head to the LEFT',
        )
        f = captureFrame()
        if (f) { frames.push(f); setFramesCaptured(2) }
        setStep('captured_left')
        setScanPhase('Left captured')
        await sleep(CONFIRM_FLASH_MS)

        // --- Step 4: PROMPT RIGHT then CAPTURE RIGHT ---
        setStep('prompt_right')
        setScanPhase('Now turn to the RIGHT')
        await sleep(PROMPT_HOLD_MS)
        setStep('capture_right')
        await waitForCondition(
          () => yawRef.current > TURN_THRESH,
          'Now turn to the RIGHT',
        )
        f = captureFrame()
        if (f) { frames.push(f); setFramesCaptured(3) }
        setStep('captured_right')
        setScanPhase('Right captured')
        await sleep(CONFIRM_FLASH_MS)

        // --- Step 5: MATCHING ---
        setStep('matching')
        setScanPhase('Finding your photos...')

        if (frames.length === 0) {
          setError('Failed to capture frames from camera')
          setScanning(false)
          setScanPhase(null)
          scanStepRef.current = null
          setScanStep(null)
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
      scanStepRef.current = null
      setScanStep(null)

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
      scanStepRef.current = null
      setScanStep(null)
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

      <div className="relative z-10 max-w-4xl mx-auto px-3 py-3 sm:px-4 sm:py-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-3 sm:mb-4 glass-card p-3 sm:p-4 rounded-xl">
          <h1 className="text-base sm:text-xl font-bold truncate pr-3">{eventName}</h1>
          <div className="flex items-center gap-1 sm:gap-2">
            <button
              onClick={() => setShowHelp(true)}
              aria-label="How to scan"
              className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors flex items-center gap-2"
            >
              <HelpCircle className="w-5 h-5" />
              <span className="hidden sm:inline">Help</span>
            </button>
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

        <div className="glass-card p-3 sm:p-6 md:p-8 rounded-2xl">
          {/* Mode Toggle — compact pill-pair, hugs top-right corner of card */}
          <div className="flex justify-end mb-3">
            <div className="inline-flex bg-white/5 rounded-full p-0.5 border border-white/10">
              <button
                onClick={() => setUseUpload(false)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${!useUpload
                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30'
                    : 'text-gray-400 hover:text-white'
                  }`}
              >
                <Camera className="w-3.5 h-3.5" />
                Camera
              </button>
              <button
                onClick={() => setUseUpload(true)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${useUpload
                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30'
                    : 'text-gray-400 hover:text-white'
                  }`}
              >
                <Upload className="w-3.5 h-3.5" />
                Upload
              </button>
            </div>
          </div>

          {!useUpload ? (
            <div className={`
                relative rounded-xl overflow-hidden aspect-[4/5] sm:aspect-[4/3] md:aspect-video bg-black mb-4 border-4
                transition-all duration-300
                ${faceDetected && frameQuality === 'ok'
                  ? 'border-green-500 shadow-[0_0_60px_rgba(34,197,94,0.45),inset_0_0_40px_rgba(34,197,94,0.12)]'
                  : faceDetected
                    ? 'border-red-500/80 shadow-[0_0_30px_rgba(239,68,68,0.35)]'
                    : 'border-white/10 shadow-2xl'}
              `}>
              {/* Component-scoped animations for the futuristic capture UI */}
              <style>{`
                @keyframes picurScanSweep {
                  0%   { top: 18%;  opacity: 0; }
                  10%  { opacity: 1; }
                  90%  { opacity: 1; }
                  100% { top: 82%;  opacity: 0; }
                }
                @keyframes picurBracketPulse {
                  0%, 100% { opacity: 0.85; }
                  50%      { opacity: 1; }
                }
                @keyframes picurCheckPop {
                  0%   { transform: scale(0.4); opacity: 0; }
                  60%  { transform: scale(1.15); opacity: 1; }
                  100% { transform: scale(1);    opacity: 1; }
                }
                @keyframes picurArrowBounce {
                  0%, 100% { transform: translateX(0); opacity: 0.85; }
                  50%      { transform: translateX(-14px); opacity: 1; }
                }
                @keyframes picurArrowBounceRight {
                  0%, 100% { transform: translateX(0); opacity: 0.85; }
                  50%      { transform: translateX(14px); opacity: 1; }
                }
                @keyframes picurConfirmFlash {
                  0%, 100% { background-color: rgba(34,197,94,0.0); }
                  40%      { background-color: rgba(34,197,94,0.18); }
                }
                .picur-scan-line {
                  animation: picurScanSweep 1.6s ease-in-out infinite;
                }
                .picur-bracket {
                  animation: picurBracketPulse 2.2s ease-in-out infinite;
                }
                .picur-check-pop {
                  animation: picurCheckPop 420ms cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
                }
                .picur-arrow-left  { animation: picurArrowBounce 900ms ease-in-out infinite; }
                .picur-arrow-right { animation: picurArrowBounceRight 900ms ease-in-out infinite; }
                .picur-confirm-flash {
                  animation: picurConfirmFlash 600ms ease-out forwards;
                }
              `}</style>

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

              {/* Corner brackets framing a fixed face-proportion box. The box
                  is centered, sized to ~74% of the viewport height with a 3:4
                  width:height aspect ratio so it always matches face shape,
                  no matter whether the viewport is portrait or landscape.
                  Color tracks frame quality so the brackets read as
                  "locked on" when green. */}
              {cameraReady && modelsLoaded && (() => {
                const color =
                  frameQuality === 'ok'         ? 'rgb(34, 197, 94)'
                  : frameQuality === 'no_face'  ? 'rgba(148, 163, 184, 0.7)'
                  :                               'rgb(239, 68, 68)'
                const stroke = '3px solid currentColor'
                const armSize = '18%'
                const arms: Array<CSSProperties> = [
                  { top: 0,    left: 0,    borderTop: stroke,    borderLeft: stroke,  borderTopLeftRadius: 8 },
                  { top: 0,    right: 0,   borderTop: stroke,    borderRight: stroke, borderTopRightRadius: 8 },
                  { bottom: 0, left: 0,    borderBottom: stroke, borderLeft: stroke,  borderBottomLeftRadius: 8 },
                  { bottom: 0, right: 0,   borderBottom: stroke, borderRight: stroke, borderBottomRightRadius: 8 },
                ]
                return (
                  <div
                    className="absolute pointer-events-none"
                    style={{
                      left: '50%',
                      top: '50%',
                      transform: 'translate(-50%, -50%)',
                      height: '78%',
                      aspectRatio: '3 / 4',
                      maxWidth: '75%',
                      color,
                    }}
                  >
                    {arms.map((armStyle, i) => (
                      <div
                        key={i}
                        className="picur-bracket absolute transition-colors duration-200"
                        style={{
                          width: armSize,
                          height: armSize,
                          ...armStyle,
                        }}
                      />
                    ))}
                  </div>
                )
              })()}

              {/* Scanning sweep line — only during the actual snap moments
                  (capture_* steps), not during align/prompt/confirm phases.
                  Skip when distance is off so users don't see it in error states. */}
              {scanning &&
                frameQuality === 'ok' &&
                (scanStep === 'capture_front' || scanStep === 'capture_left' || scanStep === 'capture_right') && (
                  <div
                    className="picur-scan-line absolute left-[24%] right-[24%] h-[2px] pointer-events-none"
                    style={{
                      background: 'linear-gradient(90deg, transparent 0%, rgba(34,197,94,0.0) 8%, rgba(34,197,94,0.95) 50%, rgba(34,197,94,0.0) 92%, transparent 100%)',
                      boxShadow: '0 0 18px rgba(34,197,94,0.85), 0 0 36px rgba(34,197,94,0.45)',
                    }}
                  />
                )}

              {/* Walkthrough step indicator — compact dots + label at the top
                  of the viewport. One small line, doesn't crowd the face. */}
              {scanning && !useUpload && (() => {
                const stages: { key: string; label: string; matches: ScanStep[] }[] = [
                  { key: 'align',  label: 'Align', matches: ['align', 'aligned_ok'] },
                  { key: 'front',  label: 'Front', matches: ['capture_front', 'captured_front'] },
                  { key: 'left',   label: 'Left',  matches: ['prompt_left', 'capture_left', 'captured_left'] },
                  { key: 'right',  label: 'Right', matches: ['prompt_right', 'capture_right', 'captured_right'] },
                ]
                const currentIndex = stages.findIndex(s => scanStep !== null && s.matches.includes(scanStep))
                const current = stages[currentIndex]
                return (
                  <div className="absolute top-2 left-1/2 -translate-x-1/2 flex items-center gap-2 pointer-events-none z-10">
                    <div className="flex gap-1">
                      {stages.map((s, i) => {
                        const done = currentIndex > i
                        const active = currentIndex === i
                        return (
                          <div
                            key={s.key}
                            className={`w-1.5 h-1.5 rounded-full transition-all ${
                              done
                                ? 'bg-green-400'
                                : active
                                  ? 'bg-blue-400 shadow-[0_0_6px_rgba(96,165,250,0.9)] w-3'
                                  : 'bg-white/30'
                            }`}
                          />
                        )
                      })}
                    </div>
                    {current && (
                      <span className="text-[10px] uppercase tracking-wider text-white/70 font-semibold drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]">
                        {currentIndex + 1}/{stages.length} · {current.label}
                      </span>
                    )}
                  </div>
                )
              })()}

              {/* Step-aware overlays. Designed to stay OFF the face: instruction
                  bubble pinned to the bottom strip, confirm check as a corner
                  badge, arrow prompts anchored to the edges. Matching spinner
                  is centered because the capture sequence is done by then. */}
              {scanning && scanStep && (() => {
                const isConfirm =
                  scanStep === 'aligned_ok' ||
                  scanStep === 'captured_front' ||
                  scanStep === 'captured_left' ||
                  scanStep === 'captured_right'
                const isPromptLeft  = scanStep === 'prompt_left'
                const isPromptRight = scanStep === 'prompt_right'
                const isMatching    = scanStep === 'matching'
                const isInstruct =
                  scanStep === 'align' ||
                  scanStep === 'capture_front' ||
                  scanStep === 'capture_left' ||
                  scanStep === 'capture_right'

                return (
                  <>
                    {/* Very faint green wash on confirm — kept subtle so it
                        reads as "saved" feedback, not a blocking flash. */}
                    {isConfirm && (
                      <div className="picur-confirm-flash absolute inset-0 pointer-events-none z-[5]" />
                    )}

                    {/* Corner check badge — small, top-right, doesn't cover face. */}
                    {isConfirm && (
                      <div className="absolute top-9 right-3 pointer-events-none z-10" key={scanStep}>
                        <div className="picur-check-pop flex items-center gap-1.5 px-2 py-1 rounded-full bg-green-500/90 border border-green-300/70 shadow-[0_0_18px_rgba(34,197,94,0.55)]">
                          <span className="text-white text-sm font-black leading-none">✓</span>
                          {scanPhase && (
                            <span className="text-white text-[11px] font-bold uppercase tracking-wider pr-1">
                              {scanPhase}
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Edge-anchored arrow prompt: arrow on the side the user
                        is supposed to turn toward, instruction at the bottom.
                        Leaves the center clear. */}
                    {(isPromptLeft || isPromptRight) && (
                      <>
                        <div
                          className={`absolute top-1/2 -translate-y-1/2 ${
                            isPromptLeft ? 'left-2' : 'right-2'
                          } text-4xl text-blue-300 drop-shadow-[0_0_10px_rgba(59,130,246,0.85)] leading-none pointer-events-none z-10 ${
                            isPromptLeft ? 'picur-arrow-left' : 'picur-arrow-right'
                          }`}
                          key={scanStep}
                        >
                          {isPromptLeft ? '←' : '→'}
                        </div>
                      </>
                    )}

                    {/* Bottom instruction strip — single small bubble, away
                        from the face. Used for align, capture_*, prompt_*. */}
                    {(isInstruct || isPromptLeft || isPromptRight) && scanPhase && (
                      <div className="absolute bottom-3 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded-full backdrop-blur-md bg-black/55 border border-white/15 text-white text-xs font-semibold shadow-lg pointer-events-none z-10 max-w-[85%] text-center">
                        {scanPhase}
                      </div>
                    )}

                    {/* Matching spinner — centered is fine, capture's done. */}
                    {isMatching && (
                      <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
                        <div className="flex flex-col items-center gap-2">
                          <Loader2 className="w-10 h-10 text-blue-400 animate-spin" />
                          <div className="px-3 py-1.5 rounded-full bg-black/65 backdrop-blur-md border border-blue-400/30 text-white text-xs font-semibold">
                            {scanPhase || 'Finding your photos...'}
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                )
              })()}

              {/* Idle status indicator. Hidden during scanning so it doesn't
                  collide with the walkthrough's bottom instruction strip. */}
              {!scanning && (
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
              )}
            </div>
          ) : (
            <div className="border-2 border-dashed border-white/10 rounded-xl p-6 sm:p-10 mb-4 text-center hover:border-white/20 transition-colors bg-white/5">
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
            <div className="mb-3 p-3 bg-red-500/10 border border-red-500/20 text-red-400 rounded-xl text-center text-sm">
              {error}
            </div>
          )}

          <button
            onClick={handleScan}
            disabled={!canScan || scanning}
            className={`w-full py-3 sm:py-4 rounded-xl text-base sm:text-lg font-bold flex items-center justify-center gap-2 transition-all ${!canScan || scanning
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

        </div>
      </div>

      {/* Help modal — same content as the old "How to scan" panel, now
          surfaced via the header "?" button so it doesn't take up
          permanent vertical space below the viewport. */}
      {showHelp && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/70 backdrop-blur-sm p-3 sm:p-4 animate-in fade-in duration-200"
          onClick={() => setShowHelp(false)}
        >
          <div
            className="glass-card rounded-2xl p-5 sm:p-6 max-w-md w-full max-h-[85vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-bold flex items-center gap-2">
                <ScanFace className="w-5 h-5 text-blue-400" /> How to scan
              </h2>
              <button
                onClick={() => setShowHelp(false)}
                aria-label="Close"
                className="p-1.5 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className="text-gray-400 text-sm mb-4">
              Tap <span className="text-white font-medium">&quot;Scan My Face&quot;</span> and follow the on-screen walkthrough. Four quick steps:
            </p>
            <ol className="space-y-3 text-gray-300">
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-500/20 border border-blue-400/40 text-blue-300 text-xs font-bold flex items-center justify-center">1</span>
                <div className="text-sm">
                  <span className="text-white font-medium">Align</span> — center your face in the oval until it glows green.
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-500/20 border border-blue-400/40 text-blue-300 text-xs font-bold flex items-center justify-center">2</span>
                <div className="text-sm">
                  <span className="text-white font-medium">Front</span> — look straight ahead and hold still.
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-500/20 border border-blue-400/40 text-blue-300 text-xs font-bold flex items-center justify-center">3</span>
                <div className="text-sm">
                  <span className="text-white font-medium">Left</span> — when the <span className="font-mono text-blue-300">←</span> arrow appears, turn your head to your left.
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-500/20 border border-blue-400/40 text-blue-300 text-xs font-bold flex items-center justify-center">4</span>
                <div className="text-sm">
                  <span className="text-white font-medium">Right</span> — when the <span className="font-mono text-blue-300">→</span> arrow appears, turn your head to your right.
                </div>
              </li>
            </ol>
            <p className="text-gray-500 text-xs mt-4">
              Can&apos;t turn? Hold still — the scan still works with one angle, you&apos;ll just match fewer photos.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
