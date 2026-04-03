import { useEffect, useState } from 'react'
import { api, AGENT_COLORS, AGENT_LABELS, AGENT_ROLES } from '../lib/api.js'

const colorBorderMap = {
  accent: 'border-accent/30',
  amber: 'border-amber/30',
  safe: 'border-safe/30',
  green: 'border-safe/30',
  danger: 'border-danger/30',
  blue: 'border-blue/30',
  dim: 'border-border',
}

const colorTextMap = {
  accent: 'text-accent',
  amber: 'text-amber',
  safe: 'text-safe',
  green: 'text-safe',
  danger: 'text-danger',
  blue: 'text-blue',
  dim: 'text-dim',
}

function timeAgo(isoString) {
  if (!isoString) return 'never'
  const diff = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function formatTokens(n) {
  if (!n) return '0'
  if (n < 1000) return String(n)
  if (n < 1000000) return `${(n / 1000).toFixed(1)}k`
  return `${(n / 1000000).toFixed(2)}M`
}

function formatDuration(ms) {
  if (!ms) return '0s'
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return `${m}m ${s % 60}s`
}

function formatCost(usd) {
  if (!usd) return '$0.00'
  if (usd < 0.01) return `$${usd.toFixed(4)}`
  if (usd < 1) return `$${usd.toFixed(3)}`
  return `$${usd.toFixed(2)}`
}

export default function AgentsPage() {
  const [agents, setAgents] = useState([])
  const [totals, setTotals] = useState({})
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const res = await api.get('/api/agents')
      setAgents(res.data.agents || [])
      setTotals(res.data.totals || {})
    } catch {
      setAgents([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, 5000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return <div className="font-mono text-sm text-dim">Loading agents...</div>
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-mono text-sm font-bold uppercase tracking-[0.18em] text-accent">Agents</h1>
      </div>

      {/* Usage summary bar */}
      <div className="mb-6 panel p-4">
        <div className="flex items-center justify-between">
          <div className="font-mono text-xs uppercase tracking-[0.16em] text-accent">Usage Summary</div>
        </div>
        <div className="mt-3 flex gap-8">
          <div>
            <div className="font-mono text-2xl font-bold text-text">{formatTokens(totals.total_tokens)}</div>
            <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-dim">Total Tokens</div>
          </div>
          <div>
            <div className="font-mono text-2xl font-bold text-text">{totals.total_calls || 0}</div>
            <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-dim">API Calls</div>
          </div>
          <div>
            <div className="font-mono text-2xl font-bold text-text">{formatDuration(totals.total_duration_ms)}</div>
            <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-dim">Total Compute</div>
          </div>
          <div>
            <div className="font-mono text-2xl font-bold text-accent">{formatCost(totals.total_cost)}</div>
            <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-dim">Estimated Cost</div>
          </div>
        </div>
      </div>

      {/* Agent cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {agents.map((agent) => {
          const color = AGENT_COLORS[agent.id] || 'dim'
          const borderClass = colorBorderMap[color] || 'border-border'
          const textClass = colorTextMap[color] || 'text-dim'
          const callsign = AGENT_LABELS[agent.id] || agent.id
          const role = AGENT_ROLES[agent.id] || agent.role || ''
          const isWorking = agent.status === 'working'

          return (
            <div key={agent.id} className={`panel p-5 ${borderClass}`}>
              <div className="flex items-center justify-between">
                <div className={`font-mono text-sm font-bold uppercase tracking-[0.16em] ${textClass}`}>
                  {callsign}
                </div>
                {isWorking ? (
                  <span className="badge badge-amber">
                    <span className="activity-ellipsis mr-1" aria-hidden="true">
                      <span /><span /><span />
                    </span>
                    working
                  </span>
                ) : (
                  <span className="badge badge-accent">idle</span>
                )}
              </div>
              <div className="mt-1 font-mono text-[11px] text-dim">{agent.id}</div>
              <div className="mt-3 text-sm text-text">{role}</div>
              <div className="mt-4 space-y-1">
                <div className="kv">
                  <span className="font-mono text-xs text-dim">Model</span>
                  <span className="font-mono text-xs text-text">{agent.model || 'default'}</span>
                </div>
                <div className="kv">
                  <span className="font-mono text-xs text-dim">API Calls</span>
                  <span className="font-mono text-xs text-text">{agent.total_calls || 0}</span>
                </div>
                <div className="kv">
                  <span className="font-mono text-xs text-dim">Tokens Used</span>
                  <span className="font-mono text-xs text-text">{formatTokens(agent.total_tokens)}</span>
                </div>
                <div className="kv">
                  <span className="font-mono text-xs text-dim">Compute Time</span>
                  <span className="font-mono text-xs text-text">{formatDuration(agent.total_duration_ms)}</span>
                </div>
                <div className="kv">
                  <span className="font-mono text-xs text-dim">Cost</span>
                  <span className="font-mono text-xs text-accent">{formatCost(agent.total_cost)}</span>
                </div>
                <div className="kv">
                  <span className="font-mono text-xs text-dim">Last Active</span>
                  <span className="font-mono text-xs text-text">
                    {timeAgo(agent.last_active || agent.last_finished)}
                  </span>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
