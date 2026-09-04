import { useState } from 'react'
import { authApi, setToken } from '../lib/api'

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await authApi.login(username, password)
      setToken(res.data.access_token)
      onLogin(res.data.username)
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <form onSubmit={submit} className="w-full max-w-sm bg-white rounded-xl border border-gray-200 shadow-sm p-8">
        <h1 className="text-xl font-bold text-gray-900 mb-1">HTL PreQue</h1>
        <p className="text-sm text-gray-500 mb-6">Sign in to continue</p>

        {error && (
          <div className="mb-4 text-sm text-red-700 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <label className="block text-xs font-medium text-gray-600 mb-1">Username</label>
        <input
          className="input w-full mb-4"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
          required
        />

        <label className="block text-xs font-medium text-gray-600 mb-1">Password</label>
        <input
          type="password"
          className="input w-full mb-6"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        <button type="submit" disabled={loading} className="btn-primary w-full justify-center">
          {loading ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
