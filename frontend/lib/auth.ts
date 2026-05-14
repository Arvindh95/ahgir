import api from './api'

export interface User {
  user_id: string
  email: string
  is_superadmin?: boolean
  created_at?: string
}

export interface RegisterResponse {
  user_id: string
  email: string
  created_at: string
}

// Auth tokens live in HttpOnly cookies that JS can't read. This service
// can no longer answer "are you logged in?" synchronously — it must ask
// the backend. Callers cache the user in React state.
export const authService = {
  async register(email: string, password: string): Promise<RegisterResponse> {
    const response = await api.post('/auth/register', { email, password })
    return response.data
  },

  async login(email: string, password: string): Promise<User> {
    // Backend sets picur_session cookie on success and returns the user.
    // No token in the response body — there is nothing for us to store.
    const response = await api.post('/auth/login', { email, password })
    return response.data
  },

  async getMe(): Promise<User> {
    const response = await api.get('/auth/me')
    return response.data
  },

  async logout(): Promise<void> {
    // Clears the cookie server-side. Idempotent; safe to call even if
    // the session was already gone.
    try {
      await api.post('/auth/logout')
    } catch {
      // Network glitch on logout shouldn't trap the user on the page;
      // they're trying to leave anyway.
    }
  },

  async isAuthenticated(): Promise<boolean> {
    // Async because the source of truth is now the server, not JS.
    try {
      await api.get('/auth/me')
      return true
    } catch {
      return false
    }
  },

  async verifyEmail(token: string): Promise<{ message: string }> {
    const response = await api.post('/auth/verify', { token })
    return response.data
  },

  async resendVerification(email: string): Promise<{ message: string }> {
    const response = await api.post('/auth/resend-verify', { email })
    return response.data
  },

  async forgotPassword(email: string): Promise<{ message: string }> {
    const response = await api.post('/auth/forgot-password', { email })
    return response.data
  },

  async resetPassword(token: string, new_password: string): Promise<{ message: string }> {
    const response = await api.post('/auth/reset-password', { token, new_password })
    return response.data
  },
}
