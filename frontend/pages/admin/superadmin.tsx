import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import ConfirmModal from '@/components/ConfirmModal'
import api from '@/lib/api'
import { authService } from '@/lib/auth'
import { useToast } from '@/hooks/useToast'
import SuperadminSkeleton from '@/components/skeletons/SuperadminSkeleton'
import GlobalAnalytics from '@/components/GlobalAnalytics'
import { Shield, Users, Image as ImageIcon, Database, Ban, ShieldCheck, ShieldOff, Trash2, DollarSign, CreditCard, Settings, Loader2, Search, Zap } from 'lucide-react'

interface UserItem {
  user_id: string
  email: string
  is_verified: boolean
  is_superadmin: boolean
  is_disabled: boolean
  event_count: number
  tier_name: string
  max_events: number
  max_photos_per_event: number
  created_at: string
}

interface PlatformStats {
  total_users: number
  total_events: number
  total_photos: number
  total_faces: number
  total_storage_bytes: number
  total_revenue_cents: number
}

interface PaymentItem {
  payment_id: string
  user_email: string
  tier_name: string
  amount_cents: number
  currency: string
  status: string
  created_at: string
}

interface EventItem {
  event_id: string
  name: string
  date: string | null
  owner_email: string
  photo_count: number
  user_tier: string
  photo_limit: number
  has_override: boolean
  created_at: string
}

interface UserTierEditState {
  userId: string
  email: string
  tierName: string
  maxEvents: string
  maxPhotos: string
}

interface EventOverrideState {
  eventId: string
  eventName: string
  photoLimit: string
}

interface ConfirmAction {
  type: 'superadmin' | 'disabled' | 'delete'
  userId: string
  email: string
  currentValue: boolean
}

export default function SuperadminPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [users, setUsers] = useState<UserItem[]>([])
  const [stats, setStats] = useState<PlatformStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState<string | null>(null)
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null)
  const [currentUserId, setCurrentUserId] = useState<string>('')
  const [payments, setPayments] = useState<PaymentItem[]>([])
  const [events, setEvents] = useState<EventItem[]>([])
  const [eventSearch, setEventSearch] = useState('')
  const [userSearch, setUserSearch] = useState('')
  const [tierEdit, setTierEdit] = useState<UserTierEditState | null>(null)
  const [savingTier, setSavingTier] = useState(false)
  const [overrideEdit, setOverrideEdit] = useState<EventOverrideState | null>(null)
  const [savingOverride, setSavingOverride] = useState(false)

  useEffect(() => {
    checkAccess()
  }, [])

  const checkAccess = async () => {
    try {
      const me = await authService.getMe()
      setCurrentUserId(me.user_id)
      if (!me.is_superadmin) {
        router.push('/admin/events')
        return
      }
      await Promise.all([loadUsers(), loadStats(), loadPayments(), loadEvents()])
    } catch {
      router.push('/admin/login')
    } finally {
      setLoading(false)
    }
  }

  const loadUsers = async () => {
    const response = await api.get('/admin/users')
    setUsers(response.data.users)
  }

  const loadStats = async () => {
    const response = await api.get('/admin/stats')
    setStats(response.data)
  }

  const loadPayments = async () => {
    try {
      const response = await api.get('/admin/payments')
      setPayments(response.data.payments || [])
    } catch { }
  }

  const loadEvents = async () => {
    try {
      const response = await api.get('/admin/events')
      setEvents(response.data.events || [])
    } catch { }
  }

  const handleTierSave = async () => {
    if (!tierEdit) return
    setSavingTier(true)
    try {
      const body: any = { tier_name: tierEdit.tierName }
      if (tierEdit.tierName === 'custom') {
        if (tierEdit.maxEvents) body.max_events = parseInt(tierEdit.maxEvents)
        if (tierEdit.maxPhotos) body.max_photos_per_event = parseInt(tierEdit.maxPhotos)
      }
      await api.patch(`/admin/users/${tierEdit.userId}/tier`, body)
      toast(`Tier updated to ${tierEdit.tierName} for "${tierEdit.email}"`, 'success')
      setTierEdit(null)
      loadUsers()
    } catch (err: any) {
      toast(err.response?.data?.detail || 'Failed to update tier', 'error')
    } finally {
      setSavingTier(false)
    }
  }

  const handleOverrideSave = async () => {
    if (!overrideEdit) return
    setSavingOverride(true)
    try {
      await api.patch(`/admin/events/${overrideEdit.eventId}/photo-override`, {
        photo_limit: parseInt(overrideEdit.photoLimit)
      })
      toast(`Photo limit set to ${overrideEdit.photoLimit} for "${overrideEdit.eventName}"`, 'success')
      setOverrideEdit(null)
      loadEvents()
    } catch (err: any) {
      toast(err.response?.data?.detail || 'Failed to set override', 'error')
    } finally {
      setSavingOverride(false)
    }
  }

  const handleRemoveOverride = async (eventId: string, eventName: string) => {
    try {
      await api.delete(`/admin/events/${eventId}/photo-override`)
      toast(`Override removed for "${eventName}"`, 'success')
      loadEvents()
    } catch (err: any) {
      toast(err.response?.data?.detail || 'Failed to remove override', 'error')
    }
  }

  const handleConfirm = async () => {
    if (!confirmAction) return
    const { type, userId, currentValue } = confirmAction
    setUpdating(userId)
    try {
      if (type === 'delete') {
        await api.delete(`/admin/users/${userId}`)
        setUsers(prev => prev.filter(u => u.user_id !== userId))
        toast('User deleted permanently', 'success')
        loadStats()
      } else if (type === 'superadmin') {
        await api.patch(`/admin/users/${userId}`, { is_superadmin: !currentValue })
        setUsers(prev => prev.map(u =>
          u.user_id === userId ? { ...u, is_superadmin: !currentValue } : u
        ))
        toast(currentValue ? 'Superadmin revoked' : 'Superadmin granted', 'success')
      } else {
        await api.patch(`/admin/users/${userId}`, { is_disabled: !currentValue })
        setUsers(prev => prev.map(u =>
          u.user_id === userId ? { ...u, is_disabled: !currentValue } : u
        ))
        toast(currentValue ? 'Account enabled' : 'Account disabled', 'success')
      }
    } catch (err: any) {
      toast(err.response?.data?.detail || 'Failed to update user', 'error')
    } finally {
      setUpdating(null)
      setConfirmAction(null)
    }
  }

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
  }

  const formatDate = (ts: string) => {
    return new Date(ts).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric'
    })
  }

  const getConfirmModalProps = () => {
    if (!confirmAction) return { title: '', message: '', variant: 'danger' as const }
    const { type, email, currentValue } = confirmAction
    if (type === 'delete') {
      return {
        title: 'Delete User',
        message: `Permanently delete ${email} and all their events, photos, and data? This cannot be undone.`,
        variant: 'danger' as const,
      }
    }
    if (type === 'superadmin') {
      return {
        title: currentValue ? 'Revoke Superadmin' : 'Grant Superadmin',
        message: currentValue
          ? `Revoke superadmin privileges from ${email}? They will lose access to the admin panel.`
          : `Grant superadmin privileges to ${email}? They will be able to manage all users and events.`,
        variant: 'warning' as const,
      }
    }
    return {
      title: currentValue ? 'Enable Account' : 'Disable Account',
      message: currentValue
        ? `Enable the account for ${email}? They will be able to log in again.`
        : `Disable the account for ${email}? They won't be able to log in.`,
      variant: 'danger' as const,
    }
  }

  if (loading) {
    return (
      <ProtectedRoute>
        <AdminLayout>
          <SuperadminSkeleton />
        </AdminLayout>
      </ProtectedRoute>
    )
  }

  const modalProps = getConfirmModalProps()

  const tierDefaults: Record<string, { events: string; photos: string }> = {
    free: { events: '1', photos: '25' },
    starter: { events: '5', photos: '250' },
    pro: { events: '20', photos: '500' },
  }

  return (
    <ProtectedRoute>
      <Head><title>Super Admin - PicUr</title></Head>
      <AdminLayout>
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-8 flex items-center gap-3">
            <Shield className="w-8 h-8 text-purple-400" />
            Superadmin Panel
          </h1>

          {/* Platform Stats */}
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mb-8">
              <div className="glass-card p-4 rounded-xl text-center">
                <div className="text-2xl font-bold text-purple-400 mb-1">{stats.total_users}</div>
                <div className="text-xs text-gray-400 uppercase tracking-wider flex items-center justify-center gap-1">
                  <Users className="w-3 h-3" /> Users
                </div>
              </div>
              <div className="glass-card p-4 rounded-xl text-center">
                <div className="text-2xl font-bold text-blue-400 mb-1">{stats.total_events}</div>
                <div className="text-xs text-gray-400 uppercase tracking-wider">Events</div>
              </div>
              <div className="glass-card p-4 rounded-xl text-center">
                <div className="text-2xl font-bold text-green-400 mb-1">{stats.total_photos}</div>
                <div className="text-xs text-gray-400 uppercase tracking-wider flex items-center justify-center gap-1">
                  <ImageIcon className="w-3 h-3" /> Photos
                </div>
              </div>
              <div className="glass-card p-4 rounded-xl text-center">
                <div className="text-2xl font-bold text-cyan-400 mb-1">{stats.total_faces}</div>
                <div className="text-xs text-gray-400 uppercase tracking-wider">Faces</div>
              </div>
              <div className="glass-card p-4 rounded-xl text-center">
                <div className="text-2xl font-bold text-orange-400 mb-1">{formatBytes(stats.total_storage_bytes)}</div>
                <div className="text-xs text-gray-400 uppercase tracking-wider flex items-center justify-center gap-1">
                  <Database className="w-3 h-3" /> Storage
                </div>
              </div>
              <div className="glass-card p-4 rounded-xl text-center">
                <div className="text-2xl font-bold text-emerald-400 mb-1">RM {(stats.total_revenue_cents / 100).toFixed(0)}</div>
                <div className="text-xs text-gray-400 uppercase tracking-wider flex items-center justify-center gap-1">
                  <DollarSign className="w-3 h-3" /> Revenue
                </div>
              </div>
            </div>
          )}

          {/* Platform Analytics */}
          <GlobalAnalytics />

          {/* User Management Table */}
          <div className="glass-card p-6 rounded-2xl">
            <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
              <Users className="w-5 h-5" /> User Management
            </h2>

            <div className="relative mb-4">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                type="text"
                placeholder="Search users by email..."
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
                className="glass-input w-full pl-10 pr-4 py-2.5 rounded-xl text-sm"
              />
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-gray-400">
                    <th className="pb-3 pl-2 font-medium">Email</th>
                    <th className="pb-3 font-medium">Tier</th>
                    <th className="pb-3 font-medium">Events</th>
                    <th className="pb-3 font-medium">Photos/Event</th>
                    <th className="pb-3 font-medium">Status</th>
                    <th className="pb-3 font-medium">Created</th>
                    <th className="pb-3 font-medium text-right pr-2">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {users
                    .filter(u => !userSearch || u.email.toLowerCase().includes(userSearch.toLowerCase()))
                    .map((user) => (
                    <tr
                      key={user.user_id}
                      className={`hover:bg-white/5 transition-colors ${user.is_disabled ? 'opacity-50' : ''}`}
                    >
                      <td className="py-3 pl-2">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{user.email}</span>
                          {user.is_superadmin && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 uppercase">
                              Admin
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase ${
                          user.tier_name === 'free' ? 'bg-gray-500/20 text-gray-400' :
                          user.tier_name === 'starter' ? 'bg-blue-500/20 text-blue-400' :
                          user.tier_name === 'pro' ? 'bg-purple-500/20 text-purple-400' :
                          'bg-yellow-500/20 text-yellow-400'
                        }`}>
                          {user.tier_name}
                        </span>
                      </td>
                      <td className="py-3">{user.event_count}/{user.max_events}</td>
                      <td className="py-3">{user.max_photos_per_event}</td>
                      <td className="py-3">
                        <div className="flex items-center gap-2">
                          {user.is_disabled ? (
                            <span className="px-2 py-0.5 rounded text-xs font-medium bg-red-500/20 text-red-400">Disabled</span>
                          ) : user.is_verified ? (
                            <span className="px-2 py-0.5 rounded text-xs font-medium bg-green-500/20 text-green-400">Verified</span>
                          ) : (
                            <span className="px-2 py-0.5 rounded text-xs font-medium bg-yellow-500/20 text-yellow-400">Unverified</span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 text-gray-400">{formatDate(user.created_at)}</td>
                      <td className="py-3 pr-2">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => setTierEdit({
                              userId: user.user_id,
                              email: user.email,
                              tierName: user.tier_name,
                              maxEvents: String(user.max_events),
                              maxPhotos: String(user.max_photos_per_event),
                            })}
                            className="p-1.5 rounded-lg transition-colors bg-white/5 text-gray-500 hover:bg-white/10 hover:text-yellow-400"
                            title="Edit tier"
                          >
                            <Zap className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => setConfirmAction({ type: 'superadmin', userId: user.user_id, email: user.email, currentValue: user.is_superadmin })}
                            disabled={updating === user.user_id}
                            className={`p-1.5 rounded-lg transition-colors ${user.is_superadmin
                                ? 'bg-purple-500/20 text-purple-400 hover:bg-purple-500/30'
                                : 'bg-white/5 text-gray-500 hover:bg-white/10 hover:text-purple-400'
                              }`}
                            title={user.is_superadmin ? 'Remove superadmin' : 'Make superadmin'}
                          >
                            {user.is_superadmin ? <ShieldCheck className="w-4 h-4" /> : <ShieldOff className="w-4 h-4" />}
                          </button>
                          <button
                            onClick={() => setConfirmAction({ type: 'disabled', userId: user.user_id, email: user.email, currentValue: user.is_disabled })}
                            disabled={updating === user.user_id}
                            className={`p-1.5 rounded-lg transition-colors ${user.is_disabled
                                ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
                                : 'bg-white/5 text-gray-500 hover:bg-white/10 hover:text-red-400'
                              }`}
                            title={user.is_disabled ? 'Enable account' : 'Disable account'}
                          >
                            <Ban className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => setConfirmAction({ type: 'delete', userId: user.user_id, email: user.email, currentValue: false })}
                            disabled={updating === user.user_id || user.user_id === currentUserId}
                            className="p-1.5 rounded-lg transition-colors bg-white/5 text-gray-500 hover:bg-red-500/20 hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed"
                            title={user.user_id === currentUserId ? 'Cannot delete yourself' : 'Delete user permanently'}
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* User Tier Edit Modal */}
          {tierEdit && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={() => setTierEdit(null)}>
              <div className="glass-card rounded-2xl p-8 max-w-md w-full mx-4" onClick={(e) => e.stopPropagation()}>
                <h3 className="text-lg font-bold mb-1">Edit User Tier</h3>
                <p className="text-sm text-gray-400 mb-6">{tierEdit.email}</p>

                <div className="space-y-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Tier</label>
                    <select
                      value={tierEdit.tierName}
                      onChange={(e) => {
                        const tier = e.target.value
                        const defaults = tierDefaults[tier]
                        setTierEdit({
                          ...tierEdit,
                          tierName: tier,
                          maxEvents: tier === 'custom' ? tierEdit.maxEvents : (defaults?.events || tierEdit.maxEvents),
                          maxPhotos: tier === 'custom' ? tierEdit.maxPhotos : (defaults?.photos || tierEdit.maxPhotos),
                        })
                      }}
                      className="glass-input w-full px-3 py-2.5 rounded-xl text-sm [&>option]:bg-gray-900 [&>option]:text-white"
                    >
                      <option value="free">Free (1 event, 25 photos)</option>
                      <option value="starter">Starter (5 events, 250 photos)</option>
                      <option value="pro">Pro (20 events, 500 photos)</option>
                      <option value="custom">Custom</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Max Events</label>
                    <input
                      type="number"
                      value={tierEdit.maxEvents}
                      onChange={(e) => setTierEdit({ ...tierEdit, maxEvents: e.target.value })}
                      className="glass-input w-full px-3 py-2.5 rounded-xl text-sm"
                      disabled={tierEdit.tierName !== 'custom'}
                    />
                  </div>

                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Max Photos per Event</label>
                    <input
                      type="number"
                      value={tierEdit.maxPhotos}
                      onChange={(e) => setTierEdit({ ...tierEdit, maxPhotos: e.target.value })}
                      className="glass-input w-full px-3 py-2.5 rounded-xl text-sm"
                      disabled={tierEdit.tierName !== 'custom'}
                    />
                  </div>
                </div>

                <div className="flex gap-3 mt-6">
                  <button
                    onClick={() => setTierEdit(null)}
                    className="flex-1 py-2.5 rounded-xl text-sm font-medium bg-white/5 hover:bg-white/10 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleTierSave}
                    disabled={savingTier}
                    className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {savingTier ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving...</> : 'Save'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Per-Event Photo Override */}
          <div className="glass-card p-6 rounded-2xl mt-8">
            <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
              <Settings className="w-5 h-5" /> Per-Event Photo Override
            </h2>

            <div className="relative mb-4">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                type="text"
                placeholder="Search events by name or owner email..."
                value={eventSearch}
                onChange={(e) => setEventSearch(e.target.value)}
                className="glass-input w-full pl-10 pr-4 py-2.5 rounded-xl text-sm"
              />
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-gray-400">
                    <th className="pb-3 pl-2 font-medium">Event</th>
                    <th className="pb-3 font-medium">Owner</th>
                    <th className="pb-3 font-medium">Photos</th>
                    <th className="pb-3 font-medium">User Tier</th>
                    <th className="pb-3 font-medium">Photo Limit</th>
                    <th className="pb-3 font-medium text-right pr-2">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {events
                    .filter((e) => {
                      if (!eventSearch) return true
                      const q = eventSearch.toLowerCase()
                      return e.name.toLowerCase().includes(q) || e.owner_email?.toLowerCase().includes(q)
                    })
                    .slice(0, 20)
                    .map((event) => (
                      <tr key={event.event_id} className="hover:bg-white/5 transition-colors">
                        <td className="py-3 pl-2 font-medium">{event.name}</td>
                        <td className="py-3 text-gray-400 text-xs">{event.owner_email}</td>
                        <td className="py-3">{event.photo_count}</td>
                        <td className="py-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase ${
                            event.user_tier === 'free' ? 'bg-gray-500/20 text-gray-400' :
                            event.user_tier === 'premium' ? 'bg-blue-500/20 text-blue-400' :
                            event.user_tier === 'premium_plus' ? 'bg-purple-500/20 text-purple-400' :
                            'bg-yellow-500/20 text-yellow-400'
                          }`}>
                            {event.user_tier === 'premium_plus' ? 'P+' : event.user_tier}
                          </span>
                        </td>
                        <td className="py-3">
                          {event.photo_limit.toLocaleString()}
                          {event.has_override && (
                            <span className="ml-1 text-[10px] text-yellow-400 font-bold">(override)</span>
                          )}
                        </td>
                        <td className="py-3 pr-2 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => setOverrideEdit({
                                eventId: event.event_id,
                                eventName: event.name,
                                photoLimit: String(event.photo_limit),
                              })}
                              className="px-3 py-1 rounded-lg text-xs font-medium bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white transition-colors"
                            >
                              Set Override
                            </button>
                            {event.has_override && (
                              <button
                                onClick={() => handleRemoveOverride(event.event_id, event.name)}
                                className="px-3 py-1 rounded-lg text-xs font-medium bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
                              >
                                Remove
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Event Override Modal */}
          {overrideEdit && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={() => setOverrideEdit(null)}>
              <div className="glass-card rounded-2xl p-8 max-w-md w-full mx-4" onClick={(e) => e.stopPropagation()}>
                <h3 className="text-lg font-bold mb-1">Set Photo Override</h3>
                <p className="text-sm text-gray-400 mb-6">{overrideEdit.eventName}</p>

                <div>
                  <label className="block text-sm text-gray-400 mb-1">Photo Limit</label>
                  <input
                    type="number"
                    value={overrideEdit.photoLimit}
                    onChange={(e) => setOverrideEdit({ ...overrideEdit, photoLimit: e.target.value })}
                    className="glass-input w-full px-3 py-2.5 rounded-xl text-sm"
                    placeholder="e.g. 800"
                  />
                </div>

                <div className="flex gap-3 mt-6">
                  <button
                    onClick={() => setOverrideEdit(null)}
                    className="flex-1 py-2.5 rounded-xl text-sm font-medium bg-white/5 hover:bg-white/10 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleOverrideSave}
                    disabled={savingOverride}
                    className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {savingOverride ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving...</> : 'Save'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Recent Payments */}
          <div className="glass-card p-6 rounded-2xl mt-8">
            <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
              <CreditCard className="w-5 h-5" /> Recent Payments
            </h2>
            {payments.length === 0 ? (
              <p className="text-gray-500 text-sm text-center py-8">No payments yet</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-gray-400">
                      <th className="pb-3 pl-2 font-medium">User</th>
                      <th className="pb-3 font-medium">Tier</th>
                      <th className="pb-3 font-medium">Amount</th>
                      <th className="pb-3 font-medium">Status</th>
                      <th className="pb-3 font-medium">Date</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {payments.slice(0, 20).map((payment) => (
                      <tr key={payment.payment_id} className="hover:bg-white/5 transition-colors">
                        <td className="py-3 pl-2 font-medium">{payment.user_email}</td>
                        <td className="py-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase ${
                            payment.tier_name === 'premium' ? 'bg-blue-500/20 text-blue-400' :
                            payment.tier_name === 'premium_plus' ? 'bg-purple-500/20 text-purple-400' :
                            'bg-gray-500/20 text-gray-400'
                          }`}>
                            {payment.tier_name === 'premium_plus' ? 'Premium+' : payment.tier_name}
                          </span>
                        </td>
                        <td className="py-3 font-medium">RM {(payment.amount_cents / 100).toFixed(0)}</td>
                        <td className="py-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                            payment.status === 'completed' ? 'bg-green-500/20 text-green-400' :
                            payment.status === 'pending' ? 'bg-yellow-500/20 text-yellow-400' :
                            'bg-red-500/20 text-red-400'
                          }`}>
                            {payment.status}
                          </span>
                        </td>
                        <td className="py-3 text-gray-400">{formatDate(payment.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <ConfirmModal
          open={!!confirmAction}
          title={modalProps.title}
          message={modalProps.message}
          confirmLabel={modalProps.title}
          variant={modalProps.variant}
          loading={!!updating}
          onConfirm={handleConfirm}
          onCancel={() => setConfirmAction(null)}
        />
      </AdminLayout>
    </ProtectedRoute>
  )
}
