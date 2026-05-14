import api from './api'

export interface AuditLog {
  log_id: string
  event_id: string
  actor_type: string
  action: string
  metadata: any
  timestamp: string
}

export interface AuditLogsResponse {
  logs: AuditLog[]
  total: number
  page: number
  limit: number
}

export const auditService = {
  async getAuditLogs(
    eventId: string,
    page: number = 1,
    limit: number = 50,
    action?: string,
    actorType?: 'admin' | 'guest' | 'system'
  ): Promise<AuditLogsResponse> {
    const params: any = { page, limit }
    if (action) {
      params.action = action
    }
    if (actorType) {
      params.actor_type = actorType
    }
    const response = await api.get(`/events/${eventId}/logs`, { params })
    return response.data
  },
}
