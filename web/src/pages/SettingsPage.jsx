import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'

function StatusBadge({ ok, label }) {
  return (
    <span className={`badge ${ok ? 'badge-accent' : 'badge-danger'}`}>
      {label || (ok ? 'ok' : 'down')}
    </span>
  )
}

function formatTokens(n) {
  if (!n) return '0'
  if (n < 1000) return String(n)
  if (n < 1000000) return `${(n / 1000).toFixed(1)}k`
  return `${(n / 1000000).toFixed(2)}M`
}

function formatCost(usd) {
  if (!usd) return '$0.00'
  if (usd < 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(2)}`
}

export default function SettingsPage() {
  const [health, setHealth] = useState(null)
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const [healthRes, configRes] = await Promise.all([
        api.get('/api/health'),
        api.get('/api/config'),
      ])
      setHealth(healthRes.data)
      setConfig(configRes.data.config || {})
    } catch { /* offline */ }
    setLoading(false)
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, 15000)
    return () => clearInterval(interval)
  }, [])

  if (loading) return <div className="font-mono text-sm text-dim">Loading health data...</div>

  const checks = health?.checks || {}

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-mono text-sm font-bold uppercase tracking-[0.18em] text-accent">System Health</h1>
        <StatusBadge ok={health?.status === 'healthy'} label={health?.status || 'unknown'} />
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {/* Gateway */}
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-xs uppercase tracking-[0.16em] text-accent">OpenClaw Gateway</span>
            <StatusBadge ok={checks.gateway?.status === 'ok'} />
          </div>
          <div className="kv">
            <span className="font-mono text-xs text-dim">Port</span>
            <span className="font-mono text-xs text-text">{checks.gateway?.port}</span>
          </div>
        </div>

        {/* Ollama */}
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-xs uppercase tracking-[0.16em] text-accent">Ollama (Local LLM)</span>
            <StatusBadge ok={checks.ollama?.status === 'ok'} />
          </div>
          <div className="kv">
            <span className="font-mono text-xs text-dim">Models</span>
            <span className="font-mono text-xs text-text">{(checks.ollama?.models || []).join(', ') || 'none'}</span>
          </div>
        </div>

        {/* RAG */}
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-xs uppercase tracking-[0.16em] text-accent">RAG Vector Store</span>
            <StatusBadge ok={checks.rag?.vectors > 0} label={checks.rag?.vectors > 0 ? 'active' : 'empty'} />
          </div>
          <div className="space-y-1">
            <div className="kv">
              <span className="font-mono text-xs text-dim">Vectors</span>
              <span className="font-mono text-xs text-text">{checks.rag?.vectors || 0}</span>
            </div>
            <div className="kv">
              <span className="font-mono text-xs text-dim">Backend</span>
              <span className="font-mono text-xs text-text">{checks.rag?.backend || 'none'}</span>
            </div>
          </div>
        </div>

        {/* API Keys */}
        <div className="panel p-5">
          <div className="mb-3 font-mono text-xs uppercase tracking-[0.16em] text-accent">API Keys</div>
          <div className="space-y-1">
            {Object.entries(checks.api_keys || {}).map(([key, set]) => (
              <div key={key} className="kv">
                <span className="font-mono text-xs text-dim">{key}</span>
                <StatusBadge ok={set} label={set ? 'set' : 'missing'} />
              </div>
            ))}
          </div>
        </div>

        {/* Feeds */}
        <div className="panel p-5">
          <div className="mb-3 font-mono text-xs uppercase tracking-[0.16em] text-accent">Threat Feeds</div>
          <div className="kv">
            <span className="font-mono text-xs text-dim">Latest Feed</span>
            <span className="font-mono text-xs text-text">{checks.feeds?.latest || 'none'}</span>
          </div>
        </div>

        {/* Database */}
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-xs uppercase tracking-[0.16em] text-accent">Database</span>
            <StatusBadge ok={checks.database?.status === 'ok'} />
          </div>
          <div className="space-y-1">
            <div className="kv">
              <span className="font-mono text-xs text-dim">Conversations</span>
              <span className="font-mono text-xs text-text">{checks.database?.conversations || 0}</span>
            </div>
            <div className="kv">
              <span className="font-mono text-xs text-dim">Messages</span>
              <span className="font-mono text-xs text-text">{checks.database?.messages || 0}</span>
            </div>
            <div className="kv">
              <span className="font-mono text-xs text-dim">Users</span>
              <span className="font-mono text-xs text-text">{checks.database?.users || 0}</span>
            </div>
          </div>
        </div>

        {/* Usage */}
        <div className="panel p-5 md:col-span-2 xl:col-span-3">
          <div className="mb-3 font-mono text-xs uppercase tracking-[0.16em] text-accent">Usage Totals</div>
          <div className="flex gap-8">
            <div>
              <div className="font-mono text-2xl font-bold text-text">{formatTokens(checks.usage?.total_tokens)}</div>
              <div className="font-mono text-[10px] uppercase text-dim">Tokens</div>
            </div>
            <div>
              <div className="font-mono text-2xl font-bold text-text">{checks.usage?.total_calls || 0}</div>
              <div className="font-mono text-[10px] uppercase text-dim">API Calls</div>
            </div>
            <div>
              <div className="font-mono text-2xl font-bold text-accent">{formatCost(checks.usage?.total_cost)}</div>
              <div className="font-mono text-[10px] uppercase text-dim">Estimated Cost</div>
            </div>
          </div>
        </div>
      </div>

      {/* Config (collapsed) */}
      <details className="mt-6 panel">
        <summary className="cursor-pointer border-b border-border px-5 py-3 font-mono text-xs uppercase tracking-[0.18em] text-accent">
          Configuration (Read-Only)
        </summary>
        <div className="max-h-96 overflow-auto p-4">
          <pre className="font-mono text-xs text-dim whitespace-pre-wrap">
            {config ? JSON.stringify(config, null, 2) : 'Not available'}
          </pre>
        </div>
      </details>
    </div>
  )
}
