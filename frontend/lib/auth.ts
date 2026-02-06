import api from './api'

export interface User {
  user_id: string
  email: string
  is_superadmin?: boolean
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface RegisterResponse {
  user_id: string
  email: string
  created_at: string
}

export const authService = {
  async register(email: string, password: string): Promise<RegisterResponse> {
    const response = await api.post('/auth/register', { email, password })
    return response.data
  },

  async login(email: string, password: string): Promise<LoginResponse> {
    const response = await api.post('/auth/login', { email, password })
    const { access_token } = response.data
    localStorage.setItem('token', access_token)
    return response.data
  },

  async getMe(): Promise<User> {
    const response = await api.get('/auth/me')
    return response.data
  },

  logout() {
    localStorage.removeItem('token')
  },

  isAuthenticated(): boolean {
    return !!localStorage.getItem('token')
  },

  async verifyEmail(token: string): Promise<{ message: string }> {
    const response = await api.post('/auth/verify', { token })
    return response.data
  },

  async resendVerification(email: string): Promise<{ message: string }> {
    const response = await api.post('/auth/resend-verify', { email })
    return response.data
  },
}
