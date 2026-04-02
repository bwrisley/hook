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

export default function AgentsPage() {
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get('/api/agents')
        setAgents(res.data.agents || [])
      } catch {
        setAgents([
          { id: 'coordinator', model: 'openai/gpt-4.1' },
          { id: 'triage-analyst', model: 'openai/gpt-4.1' },
          { id: 'osint-researcher', model: 'openai/gpt-4.1' },
          { id: 'incident-responder', model: 'openai/gpt-5' },
          { id: 'threat-intel', model: 'openai/gpt-5' },
          { id: 'report-writer', model: 'openai/gpt-4.1' },
          { id: 'log-querier', model: 'openai/gpt-4.1' },
        ])
      } finally {
        setLoading(false)
      }
    }
    load()
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

          return (
            <div key={agent.id} className={`panel p-5 ${borderClass}`}>
              <div className="flex items-center justify-between">
                <div className={`font-mono text-sm font-bold uppercase tracking-[0.16em] ${textClass}`}>
                  {callsign}
                </div>
                <div className="badge badge-accent">active</div>
              </div>
              <div className="mt-1 font-mono text-[11px] text-dim">{agent.id}</div>
              <div className="mt-3 text-sm text-text">{role}</div>
              <div className="mt-4 space-y-1">
                <div className="kv">
                  <span className="font-mono text-xs text-dim">Model</span>
                  <span className="font-mono text-xs text-text">{agent.model || 'default'}</span>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
