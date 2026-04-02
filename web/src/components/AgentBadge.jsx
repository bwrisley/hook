import { AGENT_COLORS, AGENT_LABELS } from '../lib/api.js'

const colorClasses = {
  accent: 'badge-accent',
  amber: 'badge-amber',
  safe: 'badge-safe',
  green: 'badge-green',
  danger: 'badge-danger',
  blue: 'badge-blue',
  dim: 'badge-dim',
}

export default function AgentBadge({ agentId }) {
  const color = AGENT_COLORS[agentId] || 'dim'
  const label = AGENT_LABELS[agentId] || agentId

  return (
    <span className={`badge ${colorClasses[color] || 'badge-dim'}`}>
      {label}
    </span>
  )
}
