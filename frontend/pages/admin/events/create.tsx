import { useState, FormEvent, useEffect } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import { eventService } from '@/lib/events'
import { paymentService } from '@/lib/payments'
import { Calendar, Type, Lock, Download, Trash2, ArrowLeft, Loader2, Save } from 'lucide-react'

export default function CreateEventPage() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [date, setDate] = useState('')
  const [passcode, setPasscode] = useState('')
  const [allowDownloads, setAllowDownloads] = useState(true)
  // Tier ceiling is loaded from /payments/my-tier; until then we cap input
  // conservatively so a Free user never sees a default they cannot actually keep.
  const [tierMaxRetention, setTierMaxRetention] = useState<number | null>(null)
  const [tierName, setTierName] = useState<string>('')
  const [retentionDays, setRetentionDays] = useState(30)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    paymentService
      .getMyTier()
      .then((tier) => {
        const ceiling = tier.retention_days || 30
        setTierMaxRetention(ceiling)
        setTierName(tier.tier_name)
        // Default to the ceiling so the user keeps their photos for as long
        // as their plan permits unless they explicitly shorten it.
        setRetentionDays(ceiling)
      })
      .catch(() => {
        // If the tier lookup fails, fall back to the conservative Free ceiling.
        setTierMaxRetention(30)
      })
  }, [])

  const validateForm = (): boolean => {
    if (!name || !date) {
      setError('Name and date are required')
      return false
    }

    const ceiling = tierMaxRetention ?? 30
    if (retentionDays < 1 || retentionDays > ceiling) {
      setError(`Retention days must be between 1 and ${ceiling} (your ${tierName || 'plan'} ceiling)`)
      return false
    }

    return true
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')

    if (!validateForm()) {
      return
    }

    setIsLoading(true)

    try {
      const event = await eventService.createEvent({
        name,
        date,
        passcode: passcode || undefined,
        allow_downloads: allowDownloads,
        retention_days: retentionDays,
      })
      router.push(`/admin/events/${event.event_id}`)
    } catch (err: any) {
      const detail = err.response?.data?.detail
      if (typeof detail === 'object' && detail?.code === 'EVENT_LIMIT_REACHED') {
        setError(detail.message)
      } else {
        setError(typeof detail === 'string' ? detail : err.response?.data?.error?.message || 'Failed to create event')
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <ProtectedRoute>
      <Head><title>Create Event - PicUr</title></Head>
      <AdminLayout>
        <div className="max-w-2xl mx-auto">
          <div className="flex items-center gap-4 mb-8">
            <button
              onClick={() => router.push('/admin/events')}
              className="p-2 rounded-lg hover:bg-white/10 transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <h1 className="text-3xl font-bold">Create Event</h1>
          </div>

          <form onSubmit={handleSubmit} className="glass-card p-8 rounded-2xl space-y-6">
            <div className="space-y-2">
              <label htmlFor="name" className="block text-sm font-medium text-gray-300 ml-1">
                Event Name *
              </label>
              <div className="relative">
                <Type className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  id="name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Smith Wedding"
                  className="glass-input w-full pl-12 pr-4 py-3 rounded-xl bg-white/5 border border-white/10 focus:ring-2 focus:ring-white/20 transition-all placeholder:text-gray-600"
                  disabled={isLoading}
                />
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="date" className="block text-sm font-medium text-gray-300 ml-1">
                Event Date *
              </label>
              <div className="relative">
                <Calendar className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  id="date"
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="glass-input w-full pl-12 pr-4 py-3 rounded-xl bg-white/5 border border-white/10 focus:ring-2 focus:ring-white/20 transition-all placeholder:text-gray-600 appearance-none" // appearance-none needed for some browsers to accept dark mode on date
                  disabled={isLoading}
                />
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="passcode" className="block text-sm font-medium text-gray-300 ml-1">
                Passcode (optional)
              </label>
              <div className="relative">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  id="passcode"
                  type="text"
                  value={passcode}
                  onChange={(e) => setPasscode(e.target.value)}
                  placeholder="Leave empty for no passcode"
                  className="glass-input w-full pl-12 pr-4 py-3 rounded-xl bg-white/5 border border-white/10 focus:ring-2 focus:ring-white/20 transition-all placeholder:text-gray-600"
                  disabled={isLoading}
                />
              </div>
              <p className="text-xs text-gray-500 ml-1">Guests will need this passcode to access the event</p>
            </div>

            <div className="space-y-2">
              <label htmlFor="retentionDays" className="block text-sm font-medium text-gray-300 ml-1">
                Retention Days
              </label>
              <div className="relative">
                <Trash2 className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  id="retentionDays"
                  type="number"
                  value={retentionDays}
                  onChange={(e) => setRetentionDays(parseInt(e.target.value))}
                  min="1"
                  max={tierMaxRetention ?? 30}
                  className="glass-input w-full pl-12 pr-4 py-3 rounded-xl bg-white/5 border border-white/10 focus:ring-2 focus:ring-white/20 transition-all placeholder:text-gray-600"
                  disabled={isLoading || tierMaxRetention === null}
                />
              </div>
              <p className="text-xs text-gray-500 ml-1">
                {tierMaxRetention === null
                  ? 'Loading your plan…'
                  : (
                    <>
                      How long to keep this event&apos;s photos before auto-delete (1&ndash;{tierMaxRetention} days).
                      Your <span className="text-gray-300 capitalize">{tierName}</span> plan allows up to <span className="text-gray-300">{tierMaxRetention} days</span>.
                      {tierName === 'free' || tierName === 'starter' ? ' Upgrade to keep events longer.' : ''}
                    </>
                  )}
              </p>
            </div>

            <div className="flex items-center gap-3 p-4 rounded-xl bg-white/5 border border-white/10">
              <div className="flex items-center h-5">
                <input
                  id="allowDownloads"
                  type="checkbox"
                  checked={allowDownloads}
                  onChange={(e) => setAllowDownloads(e.target.checked)}
                  className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500 focus:ring-offset-gray-900"
                  disabled={isLoading}
                />
              </div>
              <label htmlFor="allowDownloads" className="flex items-center gap-2 text-sm font-medium text-gray-300 cursor-pointer select-none">
                <Download className="w-4 h-4" />
                Allow guests to download photos
              </label>
            </div>

            {error && (
              <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl text-sm">
                {error}
              </div>
            )}

            <div className="flex gap-4 pt-4">
              <button
                type="submit"
                disabled={isLoading}
                className="flex-1 flex items-center justify-center gap-2 bg-white text-black font-semibold py-3 px-4 rounded-xl hover:bg-gray-100 transition-all active:scale-[0.98]"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" /> Creating...
                  </>
                ) : (
                  <>
                    <Save className="w-5 h-5" /> Create Event
                  </>
                )}
              </button>
              <button
                type="button"
                onClick={() => router.push('/admin/events')}
                disabled={isLoading}
                className="flex items-center justify-center px-6 py-3 rounded-xl bg-transparent border border-white/10 text-white hover:bg-white/5 transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      </AdminLayout>
    </ProtectedRoute>
  )
}
