import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Eye, FileText, Shield, TrendingUp, Zap } from 'lucide-react'
import { api, AGENT_LABELS } from '../lib/api.js'

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

function formatDuration(ms) {
  if (!ms) return '0s'
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

/** Tiny SVG sparkline */
function Sparkline({ data, color = '#ff6b00', height = 24, width = 80 }) {
  if (!data || data.length < 2) return null
  const max = Math.max(...data) || 1
  const min = Math.min(...data)
  const range = max - min || 1
  const step = width / (data.length - 1)
  const points = data.map((v, i) => `${i * step},${height - ((v - min) / range) * (height - 4) - 2}`).join(' ')
  return (
    <svg width={width} height={height} className="opacity-40">
      <polyline fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" points={points} />
    </svg>
  )
}

/** Metric card with optional sparkline */
function MetricCard({ label, value, sub, icon: Icon, accent, sparkline }) {
  return (
    <div className="panel p-5 relative overflow-hidden">
      {sparkline && sparkline.length > 1 && (
        <div className="absolute bottom-0 right-2 opacity-30">
          <Sparkline data={sparkline} height={40} width={100} color={accent ? '#ff6b00' : '#7e97a6'} />
        </div>
      )}
      <div className="flex items-center justify-between relative">
        <div>
          <div className={`font-mono text-3xl font-bold ${accent ? 'text-accent' : 'text-text'}`}>{value}</div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-dim">{label}</div>
          {sub && <div className="mt-1 font-mono text-[10px] text-dim">{sub}</div>}
        </div>
        {Icon && <Icon className="h-6 w-6 text-dim" />}
      </div>
    </div>
  )
}

function RiskBar({ dist }) {
  const total = (dist.HIGH || 0) + (dist.MEDIUM || 0) + (dist.LOW || 0) + (dist.UNKNOWN || 0)
  if (total === 0) return <div className="font-mono text-xs text-dim">No enrichment data yet</div>
  const pct = (v) => Math.round((v / total) * 100)
  return (
    <div>
      <div className="flex h-4 overflow-hidden rounded-full">
        {dist.HIGH > 0 && <div className="bg-danger" style={{ width: `${pct(dist.HIGH)}%` }} />}
        {dist.MEDIUM > 0 && <div className="bg-amber" style={{ width: `${pct(dist.MEDIUM)}%` }} />}
        {dist.LOW > 0 && <div className="bg-safe" style={{ width: `${pct(dist.LOW)}%` }} />}
        {dist.UNKNOWN > 0 && <div className="bg-border" style={{ width: `${pct(dist.UNKNOWN)}%` }} />}
      </div>
      <div className="mt-2 flex gap-4 font-mono text-[10px]">
        <span className="text-danger">HIGH {dist.HIGH || 0}</span>
        <span className="text-amber">MED {dist.MEDIUM || 0}</span>
        <span className="text-safe">LOW {dist.LOW || 0}</span>
        <span className="text-dim">UNK {dist.UNKNOWN || 0}</span>
      </div>
    </div>
  )
}

function UsageChart({ daily }) {
  if (!daily || daily.length === 0) return <div className="font-mono text-xs text-dim">No usage data yet</div>
  const maxTokens = Math.max(...daily.map((d) => d.tokens)) || 1
  return (
    <div className="flex items-end gap-1 h-24">
      {daily.map((d) => (
        <div key={d.date} className="flex-1 flex flex-col items-center gap-1">
          <div
            className="w-full bg-accent/60 rounded-t transition-all"
            style={{ height: `${Math.max(4, (d.tokens / maxTokens) * 80)}px` }}
            title={`${d.date}: ${formatTokens(d.tokens)} tokens, ${formatCost(d.cost)}`}
          />
          <span className="font-mono text-[8px] text-dim">{d.date.slice(5)}</span>
        </div>
      ))}
    </div>
  )
}

function AgentBar({ stats }) {
  const agents = Object.entries(stats).sort((a, b) => (b[1].total_tokens || 0) - (a[1].total_tokens || 0))
  const maxTokens = agents.length > 0 ? Math.max(...agents.map(([, s]) => s.total_tokens || 0)) || 1 : 1
  if (agents.length === 0) return <div className="font-mono text-xs text-dim">No agent activity yet</div>
  return (
    <div className="space-y-2">
      {agents.slice(0, 7).map(([agentId, s]) => (
        <div key={agentId} className="flex items-center gap-2">
          <span className="w-20 truncate font-mono text-[11px] text-accent">{AGENT_LABELS[agentId] || agentId}</span>
          <div className="flex-1 h-3 bg-panel2 rounded-full overflow-hidden">
            <div
              className="h-full bg-accent/50 rounded-full transition-all"
              style={{ width: `${Math.max(2, ((s.total_tokens || 0) / maxTokens) * 100)}%` }}
            />
          </div>
          <span className="font-mono text-[10px] text-dim w-12 text-right">{formatTokens(s.total_tokens)}</span>
        </div>
      ))}
    </div>
  )
}

/** Agent response time chart */
function ResponseTimeChart({ times, activeAgents }) {
  const agents = Object.entries(times).sort((a, b) => (b[1].avg_ms || 0) - (a[1].avg_ms || 0))
  if (agents.length === 0) return <div className="font-mono text-xs text-dim">No response data yet</div>
  const maxMs = Math.max(...agents.map(([, t]) => t.avg_ms || 0)) || 1
  return (
    <div className="space-y-2">
      {agents.slice(0, 7).map(([agentId, t]) => {
        const isActive = (activeAgents || []).includes(agentId)
        return (
          <div key={agentId} className="flex items-center gap-2">
            <span className="w-20 truncate font-mono text-[11px] text-accent flex items-center gap-1">
              {isActive && <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />}
              {AGENT_LABELS[agentId] || agentId}
            </span>
            <div className="flex-1 h-3 bg-panel2 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  t.avg_ms > 15000 ? 'bg-danger/50' : t.avg_ms > 8000 ? 'bg-amber/50' : 'bg-safe/50'
                }`}
                style={{ width: `${Math.max(2, ((t.avg_ms || 0) / maxMs) * 100)}%` }}
              />
            </div>
            <span className="font-mono text-[10px] text-dim w-14 text-right">{formatDuration(t.avg_ms)}</span>
          </div>
        )
      })}
    </div>
  )
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get('/api/dashboard')
        setData(res.data)
      } catch { /* offline */ }
      setLoading(false)
    }
    load()
    const interval = setInterval(load, 15000)
    return () => clearInterval(interval)
  }, [])

  if (loading) return <div className="font-mono text-sm text-dim">Loading dashboard...</div>
  if (!data) return <div className="font-mono text-sm text-dim">Dashboard unavailable</div>

  const hasActive = (data.active_agents || []).length > 0

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-mono text-sm font-bold uppercase tracking-[0.18em] text-accent">Dashboard</h1>
        {hasActive && (
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
            <span className="font-mono text-[10px] text-accent">
              {data.active_agents.map((a) => AGENT_LABELS[a] || a).join(', ')} working
            </span>
          </div>
        )}
      </div>

      {/* Key metrics with sparklines */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4 mb-6">
        <MetricCard
          label="Investigations"
          value={data.investigations?.total || 0}
          sub={`${data.investigations?.active || 0} active`}
          icon={FileText}
          sparkline={data.sparkline_inv}
        />
        <MetricCard
          label="Watched IOCs"
          value={data.watched_iocs || 0}
          sub={`${data.unread_notifications || 0} alerts`}
          icon={Eye}
        />
        <MetricCard
          label="API Calls"
          value={data.totals?.total_calls || 0}
          icon={TrendingUp}
          sparkline={data.sparkline_calls}
        />
        <MetricCard
          label="Cost"
          value={formatCost(data.totals?.total_cost)}
          icon={Shield}
          accent
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* IOC Risk Distribution */}
        <div className="panel p-5">
          <div className="mb-4 font-mono text-xs uppercase tracking-[0.16em] text-accent">IOC Risk Distribution</div>
          <RiskBar dist={data.risk_distribution || {}} />
        </div>

        {/* Usage (7 days) */}
        <div className="panel p-5">
          <div className="mb-4 font-mono text-xs uppercase tracking-[0.16em] text-accent">Usage (7 days)</div>
          <UsageChart daily={data.daily_usage || []} />
        </div>

        {/* Agent Token Usage */}
        <div className="panel p-5">
          <div className="mb-4 font-mono text-xs uppercase tracking-[0.16em] text-accent">Agent Token Usage</div>
          <AgentBar stats={data.agent_stats || {}} />
        </div>

        {/* Agent Response Time */}
        <div className="panel p-5">
          <div className="mb-4 flex items-center gap-2">
            <Zap className="h-3.5 w-3.5 text-accent" />
            <span className="font-mono text-xs uppercase tracking-[0.16em] text-accent">Agent Response Time (avg)</span>
          </div>
          <ResponseTimeChart times={data.agent_response_times || {}} activeAgents={data.active_agents} />
        </div>

        {/* Recent Investigations */}
        <div className="panel p-5">
          <div className="mb-4 flex items-center justify-between">
            <span className="font-mono text-xs uppercase tracking-[0.16em] text-accent">Recent Investigations</span>
            <button className="font-mono text-[10px] text-accent hover:underline" onClick={() => navigate('/investigations')}>
              View all
            </button>
          </div>
          {(data.recent_investigations || []).length === 0 ? (
            <div className="font-mono text-xs text-dim">No investigations yet</div>
          ) : (
            <div className="space-y-2">
              {data.recent_investigations.map((inv) => (
                <div key={inv.id} className="flex items-center justify-between rounded-lg border border-border/50 bg-panel2 px-3 py-2">
                  <div>
                    <span className="font-mono text-[11px] font-bold text-accent">{inv.id}</span>
                    <div className="text-xs text-text line-clamp-1">{inv.title}</div>
                  </div>
                  <span className={`badge text-[9px] ${
                    inv.status === 'active' ? 'badge-amber' : inv.status === 'closed' ? 'badge-dim' : 'badge-accent'
                  }`}>{inv.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* CISA KEV */}
        <div className="panel p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-danger" />
              <span className="font-mono text-xs uppercase tracking-[0.16em] text-accent">CISA KEV</span>
            </div>
            <div className="flex gap-3 font-mono text-[10px] text-dim">
              <span>{data.cisa_kev?.total_kevs || 0} total</span>
              <span>{data.cisa_kev?.recent_count || 0} new (30d)</span>
            </div>
          </div>
          {(data.cisa_kev?.recent_30d || []).length === 0 ? (
            <div className="font-mono text-xs text-dim">No recent KEVs</div>
          ) : (
            <div className="overflow-auto max-h-48">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-panel">
                  <tr className="border-b border-border">
                    <th className="px-2 py-1 text-left font-mono text-[10px] uppercase text-dim">CVE</th>
                    <th className="px-2 py-1 text-left font-mono text-[10px] uppercase text-dim">Product</th>
                    <th className="px-2 py-1 text-left font-mono text-[10px] uppercase text-dim">Due</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {data.cisa_kev.recent_30d.slice(0, 8).map((v) => (
                    <tr key={v.cve} className="hover:bg-panel2">
                      <td className="px-2 py-1 font-mono text-[11px] text-danger">{v.cve}</td>
                      <td className="px-2 py-1 text-[11px] text-text">{v.vendor} {v.product}</td>
                      <td className="px-2 py-1 font-mono text-[10px] text-amber">{v.due_date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
