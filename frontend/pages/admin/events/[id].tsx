import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import EventMonitoring from '@/components/EventMonitoring'
import EventAnalytics from '@/components/EventAnalytics'
import ConfirmModal from '@/components/ConfirmModal'
import { eventService, EventDetails } from '@/lib/events'
import { useToast } from '@/hooks/useToast'
import api from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'
import { Loader2, ArrowLeft, Image as ImageIcon, Trash2, Calendar, Link as LinkIcon, Download, Clock, QrCode, Copy, Pencil, Save, MapPin, Upload } from 'lucide-react'
import Image from 'next/image'
import EventDetailSkeleton from '@/components/skeletons/EventDetailSkeleton'
import Breadcrumbs from '@/components/Breadcrumbs'
import { useRef } from 'react'

export default function EventDetailsPage() {
  const router = useRouter()
  const { id } = router.query
  const { toast } = useToast()
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [isDeleting, setIsDeleting] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [qrCodeUrl, setQrCodeUrl] = useState<string | null>(null)
  const [editingLink, setEditingLink] = useState(false)
  const [guestLinkValue, setGuestLinkValue] = useState('')
  const [isSavingLink, setIsSavingLink] = useState(false)
  const [location, setLocation] = useState('')
  const [description, setDescription] = useState('')
  const [coverImageUrl, setCoverImageUrl] = useState<string | null>(null)
  const [isSavingDetails, setIsSavingDetails] = useState(false)
  const [isUploadingCover, setIsUploadingCover] = useState(false)
  const coverInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (id && typeof id === 'string') {
      loadEvent(id)
    }
  }, [id])

  // Handle payment redirect
  useEffect(() => {
    const { payment } = router.query
    if (payment === 'success') {
      toast('Payment successful! Your plan has been upgraded.', 'success')
      router.replace(`/admin/events/${id}`, undefined, { shallow: true })
    } else if (payment === 'cancelled') {
      toast('Payment was cancelled.', 'error')
      router.replace(`/admin/events/${id}`, undefined, { shallow: true })
    }
  }, [router.query.payment])

  const loadEvent = async (eventId: string) => {
    try {
      setIsLoading(true)
      const data = await eventService.getEvent(eventId)
      setEvent(data)
      setGuestLinkValue(data.guest_link)
      setLocation(data.location || '')
      setDescription(data.description || '')
      setCoverImageUrl(data.cover_image_url || null)
      fetchQrCode(eventId)
    } catch (err: any) {
      setError(getErrorMessage(err, 'loading event details'))
    } finally {
      setIsLoading(false)
    }
  }

  const fetchQrCode = async (eventId: string) => {
    try {
      const response = await api.get(`/events/${eventId}/qr`, { responseType: 'blob' })
      const url = URL.createObjectURL(response.data)
      setQrCodeUrl(url)
    } catch (err) {
      console.error('Failed to fetch QR code:', err)
    }
  }

  const handleSaveLink = async () => {
    if (!event) return
    const match = guestLinkValue.match(/\/e\/([^/]+)$/)
    if (!match) {
      toast('Invalid guest link format. Should be like https://domain/e/your-slug', 'error')
      return
    }
    const newSlug = match[1]
    if (newSlug === event.slug) {
      setEditingLink(false)
      return
    }
    try {
      setIsSavingLink(true)
      await api.patch(`/events/${event.event_id}`, { slug: newSlug })
      setEvent(prev => prev ? { ...prev, slug: newSlug, guest_link: guestLinkValue } : prev)
      setEditingLink(false)
      fetchQrCode(event.event_id)
      toast('Guest link updated', 'success')
    } catch (err: any) {
      toast(err.response?.data?.detail || 'Failed to update guest link', 'error')
    } finally {
      setIsSavingLink(false)
    }
  }

  const handleDelete = async () => {
    if (!event) return
    try {
      setIsDeleting(true)
      await eventService.deleteEvent(event.event_id)
      toast('Event deleted', 'success')
      router.push('/admin/events')
    } catch (err: any) {
      toast(err.response?.data?.error?.message || 'Failed to delete event', 'error')
      setIsDeleting(false)
      setShowDeleteConfirm(false)
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    })
  }

  const handleCopyLink = async () => {
    if (event) {
      try {
        await navigator.clipboard.writeText(event.guest_link)
        toast('Link copied!', 'success')
      } catch (err) {
        console.error('Failed to copy:', err)
      }
    }
  }

  const handleSaveDetails = async () => {
    if (!event) return
    try {
      setIsSavingDetails(true)
      await api.patch(`/events/${event.event_id}`, { location, description })
      setEvent(prev => prev ? { ...prev, location, description } : prev)
      toast('Details saved', 'success')
    } catch (err: any) {
      toast(err.response?.data?.detail || 'Failed to save details', 'error')
    } finally {
      setIsSavingDetails(false)
    }
  }

  const handleUploadCover = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !event) return
    try {
      setIsUploadingCover(true)
      const formData = new FormData()
      formData.append('file', file)
      const response = await api.post(`/events/${event.event_id}/cover`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setCoverImageUrl(response.data.cover_image_url)
      toast('Cover image uploaded', 'success')
    } catch (err: any) {
      toast(err.response?.data?.detail || 'Failed to upload cover image', 'error')
    } finally {
      setIsUploadingCover(false)
      e.target.value = ''
    }
  }

  if (isLoading) {
    return (
      <ProtectedRoute>
        <AdminLayout>
          <EventDetailSkeleton />
        </AdminLayout>
      </ProtectedRoute>
    )
  }

  if (error || !event) {
    return (
      <ProtectedRoute>
        <AdminLayout>
           <div className="max-w-4xl mx-auto p-4 bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl text-center">
            {error || 'Event not found'}
          </div>
        </AdminLayout>
      </ProtectedRoute>
    )
  }

  return (
    <ProtectedRoute>
      <Head>
        <title>{event.name} - PicUr</title>
      </Head>
      <AdminLayout>
        <div className="max-w-7xl mx-auto">
          <Breadcrumbs crumbs={[
            { label: 'Events', href: '/admin/events' },
            { label: event.name },
          ]} />
          {event.event_status === 'frozen' && (
            <div className="mb-6 p-4 rounded-xl bg-orange-500/10 border border-orange-500/20 text-orange-300 flex items-start gap-3">
              <div className="text-2xl">❄️</div>
              <div className="flex-1">
                <div className="font-semibold text-orange-200">This event is frozen</div>
                <p className="text-sm mt-1 text-orange-300/80">
                  Your subscription doesn&apos;t cover this many active events. The event link is locked for guests,
                  and uploads and reindexing are disabled. Upgrade your plan or delete a newer event to reactivate
                  guest access.
                </p>
                <a
                  href="/admin/billing"
                  className="inline-flex items-center gap-1 mt-2 text-sm font-semibold text-orange-200 hover:text-white"
                >
                  Manage subscription →
                </a>
              </div>
            </div>
          )}
          {event.is_cross_tenant_superadmin_view && (
            <div className="bg-purple-500/10 border border-purple-500/30 text-purple-200 rounded-xl px-4 py-3 mb-6 text-sm">
              <strong>Superadmin cross-tenant view.</strong> You are not the
              owner of this event. Edit / cover / photo controls are hidden
              for read-only safety. Mutations are still possible via the API
              with <code>?break_glass=true&amp;reason=...</code> and are
              audit-logged to the event.
            </div>
          )}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
            <h1 className="text-3xl font-bold">{event.name}</h1>

            <div className="flex gap-3">
              {event.viewer_can_edit !== false && (
                <button
                  onClick={() => router.push(`/admin/events/${event.event_id}/photos`)}
                  className="flex items-center gap-2 bg-white text-black px-4 py-2 rounded-lg font-semibold hover:bg-gray-200 transition-colors"
                >
                  <ImageIcon className="w-4 h-4" />
                  Manage Photos
                </button>
              )}
              {event.viewer_can_edit !== false && (
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  disabled={isDeleting}
                  className="flex items-center gap-2 bg-red-500/10 text-red-500 border border-red-500/20 px-4 py-2 rounded-lg font-semibold hover:bg-red-500/20 transition-colors disabled:opacity-50"
                >
                   {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                  {isDeleting ? 'Deleting...' : 'Delete Event'}
                </button>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
            <div className="lg:col-span-2 glass-card p-6 rounded-2xl">
              <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
                 Details
              </h2>
              <div className="space-y-4">
                <div className="flex items-center justify-between p-3 rounded-xl bg-white/5">
                  <span className="text-gray-400 flex items-center gap-2"><Calendar className="w-4 h-4" /> Date</span>
                  <span className="font-medium">{formatDate(event.date)}</span>
                </div>
                <div className="flex items-center justify-between p-3 rounded-xl bg-white/5">
                  <span className="text-gray-400 flex items-center gap-2"><LinkIcon className="w-4 h-4" /> Slug</span>
                  <span className="font-mono">{event.slug}</span>
                </div>
                 <div className="flex flex-col gap-2 p-3 rounded-xl bg-white/5">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 flex items-center gap-2"><LinkIcon className="w-4 h-4" /> Guest Link</span>
                    <div className="flex gap-1">
                      {editingLink ? (
                        <>
                          <button
                            onClick={handleSaveLink}
                            disabled={isSavingLink}
                            className="flex items-center gap-1 px-2 py-1 text-xs bg-green-500/20 text-green-400 hover:bg-green-500/30 rounded transition-colors disabled:opacity-50"
                          >
                            {isSavingLink ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                            Save
                          </button>
                          <button
                            onClick={() => { setEditingLink(false); setGuestLinkValue(event.guest_link) }}
                            className="flex items-center gap-1 px-2 py-1 text-xs bg-white/10 hover:bg-white/20 rounded transition-colors"
                          >
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                          {event.viewer_can_edit !== false && (
                            <button
                              onClick={() => setEditingLink(true)}
                              className="flex items-center gap-1 px-2 py-1 text-xs bg-white/10 hover:bg-white/20 rounded transition-colors"
                            >
                              <Pencil className="w-3 h-3" />
                              Edit
                            </button>
                          )}
                          <button
                            onClick={handleCopyLink}
                            className="flex items-center gap-1 px-2 py-1 text-xs bg-white/10 hover:bg-white/20 rounded transition-colors"
                          >
                            <Copy className="w-3 h-3" /> Copy
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  <input
                    type="text"
                    value={guestLinkValue}
                    readOnly={!editingLink}
                    onChange={(e) => setGuestLinkValue(e.target.value)}
                    className={`w-full rounded px-3 py-2 text-sm font-mono focus:outline-none transition-colors ${editingLink ? 'bg-white/10 border border-blue-400/50 text-white' : 'bg-white/5 border border-white/10 cursor-pointer'}`}
                    onClick={(e) => { if (!editingLink) e.currentTarget.select() }}
                  />
                </div>
                <div className="flex items-center justify-between p-3 rounded-xl bg-white/5">
                  <span className="text-gray-400 flex items-center gap-2"><Download className="w-4 h-4" /> Downloads</span>
                  <span className={`px-2 py-0.5 rounded text-sm ${event.allow_downloads ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                     {event.allow_downloads ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
                <div className="flex items-center justify-between p-3 rounded-xl bg-white/5">
                  <span className="text-gray-400 flex items-center gap-2"><Clock className="w-4 h-4" /> Retention</span>
                  <span>{event.retention_days} days</span>
                </div>

                {/* Customize Landing Page Section */}
                <div className="pt-4 mt-2 border-t border-white/10">
                  <h3 className="text-sm font-semibold text-gray-300 mb-3">Customize Landing Page</h3>

                  {/* Cover Image */}
                  <div className="mb-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm text-gray-400 flex items-center gap-2"><ImageIcon className="w-4 h-4" /> Cover Image</span>
                      {event.viewer_can_edit !== false && (
                        <label className="flex items-center gap-1 px-2 py-1 text-xs bg-white/10 hover:bg-white/20 rounded transition-colors cursor-pointer">
                          <Upload className="w-3 h-3" />
                          {coverImageUrl ? 'Change' : 'Upload'}
                          <input type="file" accept="image/*" ref={coverInputRef} onChange={handleUploadCover} className="hidden" />
                        </label>
                      )}
                    </div>
                    {coverImageUrl && (
                      <div className="relative w-full h-32 rounded-lg overflow-hidden">
                        <Image src={coverImageUrl} alt="Cover" fill className="object-cover" />
                      </div>
                    )}
                    {isUploadingCover && <p className="text-xs text-blue-400 mt-1">Uploading...</p>}
                  </div>

                  {/* Location */}
                  <div className="mb-3">
                    <label className="text-sm text-gray-400 flex items-center gap-2 mb-1"><MapPin className="w-4 h-4" /> Location</label>
                    <input
                      type="text"
                      value={location}
                      onChange={(e) => setLocation(e.target.value)}
                      placeholder="e.g. Grand Ballroom, Hotel Name"
                      className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-400/50 placeholder:text-gray-600"
                    />
                  </div>

                  {/* Description */}
                  <div className="mb-3">
                    <label className="text-sm text-gray-400 mb-1 block">Description</label>
                    <textarea
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="e.g. Simply scan your face and instantly access all your photos..."
                      rows={3}
                      className="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-400/50 placeholder:text-gray-600 resize-none"
                    />
                  </div>

                  <button
                    onClick={handleSaveDetails}
                    disabled={isSavingDetails}
                    className="flex items-center gap-1 px-3 py-1.5 text-xs bg-green-500/20 text-green-400 hover:bg-green-500/30 rounded transition-colors disabled:opacity-50"
                  >
                    {isSavingDetails ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                    Save Details
                  </button>
                </div>
              </div>
            </div>

            <div className="glass-card p-6 rounded-2xl flex flex-col items-center justify-center text-center">
              <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
                 <QrCode className="w-5 h-5" /> QR Code
              </h2>
              <div className="bg-white p-4 rounded-xl mb-4 flex items-center justify-center w-56 h-56">
                {qrCodeUrl ? (
                  <Image src={qrCodeUrl} alt="Event QR Code" width={192} height={192} className="object-contain" />
                ) : (
                  <Loader2 className="w-8 h-8 text-gray-400 animate-spin" />
                )}
              </div>
              <p className="text-sm text-gray-400">
                Share this QR code with guests to access the event
              </p>
            </div>
          </div>

          {/* Plan & Usage moved to /admin/plan so the per-event page stays
              focused on what's happening to this event right now. */}

          {/* Event Monitoring Dashboard */}
          <EventMonitoring eventId={event.event_id} />

          {/* Analytics Dashboard */}
          <div className="mt-8">
            <EventAnalytics eventId={event.event_id} />
          </div>
        </div>

        <ConfirmModal
          open={showDeleteConfirm}
          title="Delete Event"
          message={`Are you sure you want to delete "${event.name}"? All photos and data will be permanently removed. This action cannot be undone.`}
          confirmLabel="Delete Event"
          variant="danger"
          loading={isDeleting}
          onConfirm={handleDelete}
          onCancel={() => setShowDeleteConfirm(false)}
        />

      </AdminLayout>
    </ProtectedRoute>
  )
}
