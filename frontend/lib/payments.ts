import api from './api'

export interface TierConfig {
  name: string
  max_events: number
  max_photos_per_event: number
  retention_days: number
  monthly_cents: number
  yearly_cents: number
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
  retention_days: number
  active_events: number
  is_active: boolean
  subscription_status: string | null
  billing_interval: 'month' | 'year' | null
  current_period_end: string | null
  cancel_at_period_end: boolean
  activated_at: string | null
}

export interface CheckoutResponse {
  checkout_url: string
  session_id: string
}

export interface PortalResponse {
  portal_url: string
}

export type BillingInterval = 'month' | 'year'

export const paymentService = {
  async getConfig(): Promise<PaymentConfig> {
    const response = await api.get('/payments/config')
    return response.data
  },

  async getMyTier(): Promise<UserTierInfo> {
    const response = await api.get('/payments/my-tier')
    return response.data
  },

  async createCheckout(tierName: 'starter' | 'pro', interval: BillingInterval): Promise<CheckoutResponse> {
    const response = await api.post('/payments/checkout', {
      tier_name: tierName,
      interval,
    })
    return response.data
  },

  async openPortal(): Promise<PortalResponse> {
    const response = await api.post('/payments/portal')
    return response.data
  },
}
