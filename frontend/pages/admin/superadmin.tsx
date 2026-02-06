import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminLayout from '@/components/AdminLayout'
import ConfirmModal from '@/components/ConfirmModal'
import api from '@/lib/api'
import { authService } from '@/lib/auth'
import { useToast } from '@/hooks/useToast'
import SuperadminSkeleton from '@/components/skeletons/SuperadminSkeleton'
import GlobalAnalytics from '@/components/GlobalAnalytics'
import { Shield, Users, Image as ImageIcon, Database, Ban, ShieldCheck, ShieldOff } from 'lucide-react'

interface UserItem {
  user_id: string
  email: string
  is_verified: boolean
  is_superadmin: boolean
  is_disabled: boolean
  event_count: number
  created_at: string
}

interface PlatformStats {
  total_users: number
  total_events: number
  total_photos: number
  total_faces: number
  total_storage_bytes: number
}

interface ConfirmAction {
  type: 'superadmin' | 'disabled'
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

  useEffect(() => {
    checkAccess()
  }, [])

  const checkAccess = async () => {
    try {
      const me = await authService.getMe()
      if (!me.is_superadmin) {
        router.push('/admin/events')
        return
      }
      await Promise.all([loadUsers(), loadStats()])
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

  const handleConfirm = async () => {
    if (!confirmAction) return
    const { type, userId, currentValue } = confirmAction
    setUpdating(userId)
    try {
      if (type === 'superadmin') {
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

  return (
    <ProtectedRoute>
      <AdminLayout>
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-8 flex items-center gap-3">
            <Shield className="w-8 h-8 text-purple-400" />
            Superadmin Panel
          </h1>

          {/* Platform Stats */}
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
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
            </div>
          )}

          {/* Platform Analytics */}
          <GlobalAnalytics />

          {/* User Management Table */}
          <div className="glass-card p-6 rounded-2xl">
            <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
              <Users className="w-5 h-5" /> User Management
            </h2>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-gray-400">
                    <th className="pb-3 pl-2 font-medium">Email</th>
                    <th className="pb-3 font-medium">Events</th>
                    <th className="pb-3 font-medium">Status</th>
                    <th className="pb-3 font-medium">Created</th>
                    <th className="pb-3 font-medium text-right pr-2">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {users.map((user) => (
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
                      <td className="py-3">{user.event_count}</td>
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
                            onClick={() => setConfirmAction({ type: 'superadmin', userId: user.user_id, email: user.email, currentValue: user.is_superadmin })}
                            disabled={updating === user.user_id}
                            className={`p-1.5 rounded-lg transition-colors ${
                              user.is_superadmin
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
                            className={`p-1.5 rounded-lg transition-colors ${
                              user.is_disabled
                                ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
                                : 'bg-white/5 text-gray-500 hover:bg-white/10 hover:text-red-400'
                            }`}
                            title={user.is_disabled ? 'Enable account' : 'Disable account'}
                          >
                            <Ban className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
