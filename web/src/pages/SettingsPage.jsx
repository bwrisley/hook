import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'

export default function SettingsPage() {
  const [config, setConfig] = useState(null)
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [configRes, statusRes] = await Promise.all([
          api.get('/api/config'),
          api.get('/api/status'),
        ])
        setConfig(configRes.data.config || {})
        setStatus(statusRes.data)
      } catch { /* gateway offline */ }
      setLoading(false)
    }
    load()
  }, [])

  if (loading) {
    return <div className="font-mono text-sm text-dim">Loading configuration...</div>
  }

  return (
    <div>
      <h1 className="mb-6 font-mono text-sm font-bold uppercase tracking-[0.18em] text-accent">Settings</h1>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* System Status */}
        <div className="panel">
          <div className="border-b border-border px-5 py-3 font-mono text-xs uppercase tracking-[0.18em] text-accent">
            System Status
          </div>
          <div className="p-4 space-y-1">
            {status && (
              <>
                <div className="kv">
                  <span className="font-mono text-xs text-dim">Name</span>
                  <span className="font-mono text-xs text-text">{status.name}</span>
                </div>
                <div className="kv">
                  <span className="font-mono text-xs text-dim">Version</span>
                  <span className="font-mono text-xs text-text">{status.version}</span>
                </div>
                <div className="kv">
                  <span className="font-mono text-xs text-dim">Gateway</span>
                  <span className={`badge ${status.gateway?.status === 'ok' ? 'badge-accent' : 'badge-danger'}`}>
                    {status.gateway?.status || 'unknown'}
                  </span>
                </div>
                <div className="kv">
                  <span className="font-mono text-xs text-dim">Agents</span>
                  <span className="font-mono text-xs text-text">{status.agent_count}</span>
                </div>
                <div className="kv">
                  <span className="font-mono text-xs text-dim">Active Investigations</span>
                  <span className="font-mono text-xs text-text">{status.active_investigations}</span>
                </div>
                <div className="kv">
                  <span className="font-mono text-xs text-dim">Last Check</span>
                  <span className="font-mono text-xs text-dim">
                    {status.generated_at ? new Date(status.generated_at).toLocaleString() : ''}
                  </span>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Configuration (read-only) */}
        <div className="panel">
          <div className="border-b border-border px-5 py-3 font-mono text-xs uppercase tracking-[0.18em] text-accent">
            Configuration (Read-Only)
          </div>
          <div className="max-h-96 overflow-auto p-4">
            {config ? (
              <pre className="font-mono text-xs text-dim whitespace-pre-wrap">
                {JSON.stringify(config, null, 2)}
              </pre>
            ) : (
              <div className="font-mono text-sm text-dim">Configuration not available.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
