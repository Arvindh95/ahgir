import api from './api'

export interface Event {
  event_id: string
  slug: string
  name: string
  date: string
  guest_link: string
  qr_code_url?: string
  owner_user_id: string
  allow_downloads: boolean
  retention_days: number
  event_status?: 'active' | 'frozen' | 'expired'
  created_at: string
  photo_count?: number
  indexed_count?: number
  face_count?: number
  location?: string
  description?: string
  cover_image_url?: string
}

export interface EventStatus {
  total_photos: number
  pending: number
  indexed: number
  no_faces: number
  failed: number
  total_faces: number
  indexing_percentage: number
}

export interface EventTierInfo {
  tier_name: string
  photo_limit: number
  is_active: boolean
}

export interface UserTierInfo {
  tier_name: string
  max_events: number
  max_photos_per_event: number
  events_used: number
  is_active: boolean
}

export interface EventDetails extends Event {
  status: EventStatus
  tier?: EventTierInfo
  user_tier?: UserTierInfo
  // False when a superadmin is viewing someone else's event — UI hides
  // edit / cover / photo controls. Mutations from a superadmin still
  // require break_glass=true on the backend, so this flag is purely a
  // UX signal, not a security boundary.
  viewer_can_edit?: boolean
  is_cross_tenant_superadmin_view?: boolean
}

export interface AccuracyScoreBucket {
  bucket: string
  passed: number
  filtered: number
}

export interface AccuracyProblemScan {
  scan_id: string
  candidate_count: number
  near_miss_count: number
  max_raw_similarity: number
  max_scored_similarity: number
}

export interface AccuracyRecommendation {
  level: 'success' | 'info' | 'warning'
  title: string
  detail: string
}

export interface EventAccuracy {
  event_id: string
  generated_at: string
  scan_summary: {
    total_scans: number
    unique_guests: number
    matched_scans: number
    zero_match_scans: number
    no_face_scans: number
    filtered_scans: number
    upstream_error_scans: number
    uncategorized_scans: number
    avg_returned_matches: number
  }
  match_quality: {
    telemetry_scans: number
    candidate_count: number
    passed_candidates: number
    filtered_candidates: number
    rescued_candidates: number
    near_miss_candidates: number
    tiny_filtered_candidates: number
    blurry_filtered_candidates: number
  }
  indexing_health: EventStatus
  score_buckets: AccuracyScoreBucket[]
  problem_scans: AccuracyProblemScan[]
  recommendations: AccuracyRecommendation[]
}

export interface CreateEventRequest {
  name: string
  date: string
  passcode?: string
  allow_downloads: boolean
  retention_days: number
}

export const eventService = {
  async createEvent(data: CreateEventRequest): Promise<Event> {
    const response = await api.post('/events', data)
    return response.data
  },

  async getEvents(): Promise<Event[]> {
    const response = await api.get('/events')
    return response.data.events
  },

  async getEvent(eventId: string): Promise<EventDetails> {
    const response = await api.get(`/events/${eventId}`)
    return response.data
  },

  async deleteEvent(eventId: string): Promise<void> {
    await api.delete(`/events/${eventId}`)
  },

  async reindexEvent(eventId: string): Promise<{ message: string; queued_count: number }> {
    const response = await api.post(`/events/${eventId}/reindex`)
    return response.data
  },

  async getAccuracy(eventId: string): Promise<EventAccuracy> {
    const response = await api.get(`/events/${eventId}/accuracy`)
    return response.data
  },

  getQRCodeUrl(eventId: string): string {
    return `${api.defaults.baseURL}/events/${eventId}/qr`
  },
}
