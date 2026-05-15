import { useEffect, useRef, useState } from 'react'
import { Flag, Loader2, X } from 'lucide-react'
import { abuseService, ReportFilePayload } from '@/lib/abuse'

const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || ''
const TURNSTILE_SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'

declare global {
  interface Window {
    turnstile?: {
      render: (selector: string | HTMLElement, opts: any) => string
      reset: (widgetId?: string) => void
      remove: (widgetId: string) => void
    }
  }
}

function loadTurnstileScript(): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve()
  if (window.turnstile) return Promise.resolve()
  return new Promise((resolve) => {
    const existing = document.querySelector(`script[src="${TURNSTILE_SCRIPT_SRC}"]`) as HTMLScriptElement | null
    if (existing) {
      existing.addEventListener('load', () => resolve())
      return
    }
    const s = document.createElement('script')
    s.src = TURNSTILE_SCRIPT_SRC
    s.async = true
    s.defer = true
    s.onload = () => resolve()
    document.head.appendChild(s)
  })
}

interface ReportPhotoModalProps {
  open: boolean
  imageId: string
  onClose: () => void
}

const CATEGORIES: Array<{ value: ReportFilePayload['category']; label: string }> = [
  { value: 'csam', label: 'CSAM (child sexual abuse material)' },
  { value: 'nudity', label: 'Nudity without consent' },
  { value: 'harassment', label: 'Harassment' },
  { value: 'copyright', label: 'Copyright violation' },
  { value: 'violence', label: 'Violence or graphic content' },
  { value: 'other', label: 'Other' },
]

export default function ReportPhotoModal({ open, imageId, onClose }: ReportPhotoModalProps) {
  const [category, setCategory] = useState<ReportFilePayload['category'] | ''>('')
  const [description, setDescription] = useState('')
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [turnstileToken, setTurnstileToken] = useState('')
  const turnstileWidgetIdRef = useRef<string | null>(null)
  const turnstileMountRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    setCategory('')
    setDescription('')
    setEmail('')
    setDone(false)
    setError('')
    setTurnstileToken('')
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  // Mount the Turnstile widget when the modal opens (and a site key is
  // configured). Reset on close so the token isn't reused on the next open.
  useEffect(() => {
    if (!open || !TURNSTILE_SITE_KEY) return
    let cancelled = false
    loadTurnstileScript().then(() => {
      if (cancelled || !window.turnstile || !turnstileMountRef.current) return
      // Some browsers preserve the inner DOM between mounts; clear to be safe.
      turnstileMountRef.current.innerHTML = ''
      const id = window.turnstile.render(turnstileMountRef.current, {
        sitekey: TURNSTILE_SITE_KEY,
        theme: 'dark',
        callback: (token: string) => setTurnstileToken(token),
        'expired-callback': () => setTurnstileToken(''),
        'error-callback': () => setTurnstileToken(''),
      })
      turnstileWidgetIdRef.current = id
    })
    return () => {
      cancelled = true
      if (turnstileWidgetIdRef.current && window.turnstile) {
        try { window.turnstile.remove(turnstileWidgetIdRef.current) } catch {}
      }
      turnstileWidgetIdRef.current = null
    }
  }, [open])

  if (!open) return null

  const turnstileEnabled = !!TURNSTILE_SITE_KEY
  const submitDisabled = !category || submitting || (turnstileEnabled && !turnstileToken)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!category) return
    try {
      setSubmitting(true)
      setError('')
      await abuseService.fileReport({
        image_id: imageId,
        category,
        description: description.trim() || undefined,
        reporter_email: email.trim() || undefined,
        turnstile_token: turnstileEnabled ? turnstileToken : undefined,
      })
      setDone(true)
    } catch (err: any) {
      const code = err.response?.status
      if (code === 429) {
        setError('You have submitted too many reports recently. Please try again later.')
      } else if (code === 403) {
        setError('Captcha verification failed. Please try the challenge again.')
        // Reset the widget so the user can retry.
        if (turnstileWidgetIdRef.current && window.turnstile) {
          try { window.turnstile.reset(turnstileWidgetIdRef.current) } catch {}
        }
        setTurnstileToken('')
      } else {
        setError('Could not submit report. Please try again later.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[60] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="glass-card rounded-2xl p-6 max-w-md w-full border border-white/10 text-white"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-2">
            <Flag className="w-5 h-5 text-orange-400" />
            <h3 className="text-lg font-bold">Report this photo</h3>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {done ? (
          <div className="py-6 text-center">
            <p className="text-sm">Thanks. We will review this report shortly.</p>
            <button
              onClick={onClose}
              className="mt-6 px-4 py-2 bg-white text-black rounded-lg font-semibold text-sm hover:bg-gray-100 transition-colors"
            >
              Close
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Category <span className="text-red-400">*</span>
              </label>
              <select
                required
                value={category}
                onChange={(e) => setCategory(e.target.value as ReportFilePayload['category'])}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm focus:border-white/40 focus:outline-none"
              >
                <option value="" disabled>Select a category</option>
                {CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Description <span className="text-gray-500">(optional)</span>
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={2000}
                rows={4}
                placeholder="Tell us what we should look for."
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm focus:border-white/40 focus:outline-none placeholder:text-gray-600"
              />
              <p className="mt-1 text-xs text-gray-500">{description.length}/2000</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Email <span className="text-gray-500">(optional)</span>
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm focus:border-white/40 focus:outline-none placeholder:text-gray-600"
              />
              <p className="mt-1 text-xs text-gray-500">
                We won&apos;t share this with the event organizer — only used if our team needs more info.
              </p>
            </div>

            {/* Honeypot — visually hidden + autocomplete off. Bots that fill
                every field will populate this and the backend silently drops
                the row. Real users never see or touch it. */}
            <input
              type="text"
              name="website"
              tabIndex={-1}
              autoComplete="off"
              aria-hidden="true"
              defaultValue=""
              style={{
                position: 'absolute',
                left: '-10000px',
                opacity: 0,
                height: 0,
                width: 0,
                pointerEvents: 'none',
              }}
            />

            {turnstileEnabled && (
              <div className="pt-2">
                <div ref={turnstileMountRef} />
              </div>
            )}

            {error && (
              <div className="p-2 bg-red-500/10 border border-red-500/20 rounded text-xs text-red-400">
                {error}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                disabled={submitting}
                className="glass-button px-4 py-2 rounded-lg text-sm font-medium"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitDisabled}
                className="px-4 py-2 bg-orange-600 text-white rounded-lg text-sm font-semibold hover:bg-orange-700 transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
                Submit report
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
