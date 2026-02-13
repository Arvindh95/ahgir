import api from './api'

export interface TierConfig {
  name: string
  max_events: number
  max_photos_per_event: number
  price_cents: number
  currency: string
}

export interface PaymentConfig {
  publishable_key: string
  tiers: Record<string, TierConfig>
}

export interface UserTierInfo {
  tier_name: string
  max_events: number
  max_photos_per_event: number
  events_used: number
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

  async getMyTier(): Promise<UserTierInfo> {
    const response = await api.get('/payments/my-tier')
    return response.data
  },

  async createCheckout(tierName: string): Promise<CheckoutResponse> {
    const response = await api.post('/payments/checkout', {
      tier_name: tierName,
    })
    return response.data
  },
}
