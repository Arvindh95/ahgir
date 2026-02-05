import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import EventMonitoring from '@/components/EventMonitoring'
import { eventService, EventDetails } from '@/lib/events'
import api from '@/lib/api'
import { Loader2, ArrowLeft, Image as ImageIcon, Trash2, Calendar, Link as LinkIcon, Download, Clock, QrCode, Copy, Check, Pencil, Save, MapPin, Upload } from 'lucide-react'
import { useRef } from 'react'

export default function EventDetailsPage() {
  const router = useRouter()
  const { id } = router.query
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [isDeleting, setIsDeleting] = useState(false)
  const [copied, setCopied] = useState(false)
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
      setError(err.response?.data?.error?.message || 'Failed to load event')
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
      setError('Invalid guest link format. Should be like https://domain/e/your-slug')
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
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update guest link')
    } finally {
      setIsSavingLink(false)
    }
  }

  const handleDelete = async () => {
    if (!event || !confirm('Are you sure you want to delete this event? This action cannot be undone.')) {
      return
    }

    try {
      setIsDeleting(true)
      await eventService.deleteEvent(event.event_id)
      router.push('/admin/events')
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to delete event')
      setIsDeleting(false)
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
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
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
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save')
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
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to upload cover image')
    } finally {
      setIsUploadingCover(false)
    }
  }

  if (isLoading) {
    return (
      <ProtectedRoute>
        <AdminLayout>
          <div className="flex items-center justify-center h-64">
            <Loader2 className="w-8 h-8 text-white animate-spin" />
          </div>
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
      <AdminLayout>
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
            <div className="flex items-center gap-4">
              <button 
                onClick={() => router.push('/admin/events')}
                className="p-2 rounded-lg hover:bg-white/10 transition-colors"
               >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <h1 className="text-3xl font-bold">{event.name}</h1>
            </div>
            
            <div className="flex gap-3">
              <button
                onClick={() => router.push(`/admin/events/${event.event_id}/photos`)}
                className="flex items-center gap-2 bg-white text-black px-4 py-2 rounded-lg font-semibold hover:bg-gray-200 transition-colors"
              >
                <ImageIcon className="w-4 h-4" />
                Manage Photos
              </button>
              <button
                onClick={handleDelete}
                disabled={isDeleting}
                className="flex items-center gap-2 bg-red-500/10 text-red-500 border border-red-500/20 px-4 py-2 rounded-lg font-semibold hover:bg-red-500/20 transition-colors disabled:opacity-50"
              >
                 {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                {isDeleting ? 'Deleting...' : 'Delete Event'}
              </button>
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
                          <button
                            onClick={() => setEditingLink(true)}
                            className="flex items-center gap-1 px-2 py-1 text-xs bg-white/10 hover:bg-white/20 rounded transition-colors"
                          >
                            <Pencil className="w-3 h-3" />
                            Edit
                          </button>
                          <button
                            onClick={handleCopyLink}
                            className="flex items-center gap-1 px-2 py-1 text-xs bg-white/10 hover:bg-white/20 rounded transition-colors"
                          >
                            {copied ? <><Check className="w-3 h-3" /> Copied</> : <><Copy className="w-3 h-3" /> Copy</>}
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
                      <label className="flex items-center gap-1 px-2 py-1 text-xs bg-white/10 hover:bg-white/20 rounded transition-colors cursor-pointer">
                        <Upload className="w-3 h-3" />
                        {coverImageUrl ? 'Change' : 'Upload'}
                        <input type="file" accept="image/*" ref={coverInputRef} onChange={handleUploadCover} className="hidden" />
                      </label>
                    </div>
                    {coverImageUrl && (
                      <img src={coverImageUrl} alt="Cover" className="w-full h-32 object-cover rounded-lg" />
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
                  <img src={qrCodeUrl} alt="Event QR Code" className="w-48 h-48 object-contain" />
                ) : (
                  <Loader2 className="w-8 h-8 text-gray-400 animate-spin" />
                )}
              </div>
              <p className="text-sm text-gray-400">
                Share this QR code with guests to access the event
              </p>
            </div>
          </div>

          {/* Event Monitoring Dashboard */}
          <EventMonitoring eventId={event.event_id} />
        </div>
      </AdminLayout>
    </ProtectedRoute>
  )
}
