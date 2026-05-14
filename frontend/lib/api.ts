import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  // Send + receive HttpOnly auth cookies (picur_session, picur_event).
  // The backend's CORS config allow_credentials=True permits this.
  withCredentials: true,
})

// CSRF defense: the backend's CsrfMiddleware rejects any state-changing
// request that carries an auth cookie unless it also has this header. A
// classic CSRF attacker (third-party page) cannot set custom headers on
// a vanilla form submit — so requiring one closes the gap. We attach it
// on every method to keep the interceptor trivial; the backend ignores
// it on GET/HEAD/OPTIONS.
api.interceptors.request.use((config) => {
  config.headers['X-Requested-With'] = 'XMLHttpRequest'
  return config
})

export default api
