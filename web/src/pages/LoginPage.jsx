import { useState } from 'react'
import { Shield } from 'lucide-react'
import { login } from '../lib/api.js'

export default function LoginPage({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!username || !password) return
    setBusy(true)
    setError('')
    try {
      const result = await login(username, password)
      onLogin(result.user)
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full items-center justify-center bg-shell">
      <div className="w-96 panel p-8">
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="rounded-xl border border-accent/40 bg-accent/10 p-3 text-accent">
            <Shield className="h-6 w-6" />
          </div>
          <div>
            <div className="font-mono text-lg font-bold tracking-[0.22em] text-accent">SHADOWBOX</div>
            <div className="font-mono text-[11px] uppercase tracking-[0.22em] text-dim">by punch cyber</div>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label className="block font-mono text-xs uppercase tracking-[0.14em] text-dim mb-1">Username</label>
              <input
                className="input"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
                autoComplete="username"
              />
            </div>
            <div>
              <label className="block font-mono text-xs uppercase tracking-[0.14em] text-dim mb-1">Password</label>
              <input
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
            {error && (
              <div className="rounded-lg border border-danger/30 bg-danger/10 p-3 font-mono text-xs text-danger">
                {error}
              </div>
            )}
            <button
              className="btn btn-primary w-full"
              type="submit"
              disabled={busy || !username || !password}
            >
              {busy ? 'Authenticating...' : 'Sign In'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
