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

export default function AgentsPage() {
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const res = await api.get('/api/agents')
      setAgents(res.data.agents || [])
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
      <h1 className="mb-6 font-mono text-sm font-bold uppercase tracking-[0.18em] text-accent">Agents</h1>
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
                  <span className="font-mono text-xs text-dim">Messages</span>
                  <span className="font-mono text-xs text-text">{agent.message_count || 0}</span>
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
