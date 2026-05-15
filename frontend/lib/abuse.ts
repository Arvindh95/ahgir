import api from './api'

export interface AbuseReportRow {
  id: string
  image_id: string
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
}

export const abuseService = {
  async fileReport(payload: ReportFilePayload): Promise<{ message: string }> {
    // Honeypot field. Hidden in the modal via CSS so legit users never fill
    // it. Bots filling every field will populate it and the backend silently
    // drops the row.
    const body = { ...payload, website: '' }
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
    sort?: 'newest' | 'oldest'
    limit?: number
    offset?: number
  }): Promise<AbuseReportListResponse> {
    const res = await api.get('/admin/abuse-reports', { params })
    return res.data
  },

  async get(reportId: string): Promise<AbuseReportRow> {
    // Single-report metadata reuse: hit the list with id-filter would be
    // cleaner, but for Phase 1 we list pending+offset and find locally.
    // Dedicated single-get endpoint is a follow-up.
    const res = await api.get('/admin/abuse-reports', {
      params: { status: undefined, limit: 100 },
    })
    const found = (res.data.items as AbuseReportRow[]).find((r) => r.id === reportId)
    if (!found) throw new Error('report not found')
    return found
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
}
