import api from './api'

export interface AbuseReportRow {
  id: string
  // NULL after the underlying image was permanently deleted via
  // /delete-photo. FK is ON DELETE SET NULL so the report row survives
  // for queue history; callers must treat missing image_id as
  // "image no longer exists" (skip reveal, render placeholder).
  image_id: string | null
  event_id: string
  event_name?: string | null
  event_slug?: string | null
  filename?: string | null
  uploaded_at?: string | null
  category: string
  description?: string | null
  reporter_email?: string | null
  reporter_ip?: string | null
  status: string
  action_taken?: string | null
  notes?: string | null
  created_at: string
  reviewed_at?: string | null
  reviewed_by_email?: string | null
  duplicate_count?: number
  is_possible_self_report?: boolean
  reporter_ban_state?: 'softban' | 'permaban' | null
  image_status?: string | null
}

export interface AbuseReportListResponse {
  items: AbuseReportRow[]
  total: number
  limit: number
  offset: number
}

export interface AbuseRevealResponse {
  review_url: string
  expires_in: number
  status: string
  reviewed_at?: string | null
  reviewed_by_email?: string | null
}

export interface ReportFilePayload {
  image_id: string
  category: 'csam' | 'nudity' | 'harassment' | 'copyright' | 'violence' | 'other'
  description?: string
  reporter_email?: string
  turnstile_token?: string
  // Honeypot value — the modal reads it from a hidden uncontrolled <input>
  // via ref and passes it through here. Bots that auto-fill every field
  // populate the input; legit users never touch it. Only included in the
  // POST body when non-empty so the backend's "silent drop on populated"
  // check actually fires.
  honeypot?: string
}

export const abuseService = {
  async fileReport(payload: ReportFilePayload): Promise<{ message: string }> {
    const { honeypot, ...rest } = payload
    const body = honeypot ? { ...rest, website: honeypot } : rest
    const res = await api.post('/report', body)
    return res.data
  },

  async dismissBySource(opts: { reporter_ip?: string; reporter_email?: string }): Promise<number> {
    const res = await api.post('/admin/abuse-reports/dismiss-by-source', opts)
    return res.data.dismissed ?? 0
  },

  async clearBan(reporter_ip: string): Promise<void> {
    await api.post('/admin/abuse-reports/clear-ban', { reporter_ip })
  },

  async getPendingCount(): Promise<number> {
    const res = await api.get('/admin/abuse-reports/pending-count')
    return res.data.pending ?? 0
  },

  async list(params: {
    status?: string
    category?: string
    event_search?: string
    sort?: 'newest' | 'oldest'
    limit?: number
    offset?: number
  }): Promise<AbuseReportListResponse> {
    const res = await api.get('/admin/abuse-reports', { params })
    return res.data
  },

  async get(reportId: string): Promise<AbuseReportRow> {
    const res = await api.get(`/admin/abuse-reports/${reportId}`)
    return res.data
  },

  async reveal(reportId: string): Promise<AbuseRevealResponse> {
    const res = await api.post(`/admin/abuse-reports/${reportId}/reveal`)
    return res.data
  },

  async dismiss(reportId: string): Promise<void> {
    await api.post(`/admin/abuse-reports/${reportId}/dismiss`)
  },

  async quarantine(reportId: string): Promise<void> {
    await api.post(`/admin/abuse-reports/${reportId}/quarantine`)
  },

  async deletePhoto(reportId: string): Promise<void> {
    await api.post(`/admin/abuse-reports/${reportId}/delete-photo`)
  },

  async restoreImage(reportId: string): Promise<void> {
    await api.post(`/admin/abuse-reports/${reportId}/restore`)
  },
}
