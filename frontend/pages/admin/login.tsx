import { useState, FormEvent, useEffect } from 'react'
import { useRouter } from 'next/router'
import { authService } from '@/lib/auth'

export default function Login() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    // Redirect if already authenticated
    if (authService.isAuthenticated()) {
      router.push('/admin/events')
    }
  }, [router])

  const validateForm = (): boolean => {
    if (!email || !password) {
      setError('Email and password are required')
      return false
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError('Invalid email format')
      return false
    }

    return true
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')

    if (!validateForm()) {
      return
    }

    setIsLoading(true)

    try {
      await authService.login(email, password)
      router.push('/admin/events')
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Login failed')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: '400px', margin: '100px auto', padding: '20px' }}>
      <h1>Admin Login</h1>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '15px' }}>
          <label htmlFor="email" style={{ display: 'block', marginBottom: '5px' }}>
            Email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ width: '100%', padding: '8px', fontSize: '14px' }}
            disabled={isLoading}
          />
        </div>

        <div style={{ marginBottom: '15px' }}>
          <label htmlFor="password" style={{ display: 'block', marginBottom: '5px' }}>
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: '100%', padding: '8px', fontSize: '14px' }}
            disabled={isLoading}
          />
        </div>

        {error && (
          <div style={{ color: 'red', marginBottom: '15px', fontSize: '14px' }}>
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={isLoading}
          style={{
            width: '100%',
            padding: '10px',
            backgroundColor: '#0070f3',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: isLoading ? 'not-allowed' : 'pointer',
            fontSize: '16px',
          }}
        >
          {isLoading ? 'Logging in...' : 'Login'}
        </button>
      </form>

      <p style={{ marginTop: '20px', textAlign: 'center' }}>
        Don't have an account?{' '}
        <a href="/admin/register" style={{ color: '#0070f3' }}>
          Register
        </a>
      </p>
    </div>
  )
}
