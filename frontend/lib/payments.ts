import api from './api'

export interface TierConfig {
  name: string
  photo_limit: number
  price_cents: number
  currency: string
}

export interface PaymentConfig {
  publishable_key: string
  tiers: Record<string, TierConfig>
}

export interface EventTierInfo {
  event_id: string
  tier_name: string
  photo_limit: number
  is_active: boolean
  activated_at: string | null
}

export interface CheckoutResponse {
  checkout_url: string
  session_id: string
}

export const paymentService = {
  async getConfig(): Promise<PaymentConfig> {
    const response = await api.get('/payments/config')
    return response.data
  },

  async createCheckout(eventId: string, tierName: string): Promise<CheckoutResponse> {
    const response = await api.post('/payments/checkout', {
      event_id: eventId,
      tier_name: tierName,
    })
    return response.data
  },

  async getEventTier(eventId: string): Promise<EventTierInfo> {
    const response = await api.get(`/payments/event/${eventId}/tier`)
    return response.data
  },
}
