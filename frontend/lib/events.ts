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

  getQRCodeUrl(eventId: string): string {
    return `${api.defaults.baseURL}/events/${eventId}/qr`
  },
}
