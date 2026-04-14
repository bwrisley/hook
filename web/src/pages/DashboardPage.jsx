import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Eye, FileText, Shield, TrendingUp } from 'lucide-react'
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

function MetricCard({ label, value, sub, icon: Icon, accent }) {
  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between">
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
            className="w-full bg-accent/60 rounded-t"
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
              className="h-full bg-accent/50 rounded-full"
              style={{ width: `${Math.max(2, ((s.total_tokens || 0) / maxTokens) * 100)}%` }}
            />
          </div>
          <span className="font-mono text-[10px] text-dim w-12 text-right">{formatTokens(s.total_tokens)}</span>
        </div>
      ))}
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
    const interval = setInterval(load, 30000)
    return () => clearInterval(interval)
  }, [])

  if (loading) return <div className="font-mono text-sm text-dim">Loading dashboard...</div>
  if (!data) return <div className="font-mono text-sm text-dim">Dashboard unavailable</div>

  return (
    <div>
      <h1 className="mb-6 font-mono text-sm font-bold uppercase tracking-[0.18em] text-accent">Dashboard</h1>

      {/* Key metrics */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4 mb-6">
        <MetricCard label="Investigations" value={data.investigations?.total || 0} sub={`${data.investigations?.active || 0} active`} icon={FileText} />
        <MetricCard label="Watched IOCs" value={data.watched_iocs || 0} sub={`${data.unread_notifications || 0} alerts`} icon={Eye} />
        <MetricCard label="API Calls" value={data.totals?.total_calls || 0} icon={TrendingUp} />
        <MetricCard label="Cost" value={formatCost(data.totals?.total_cost)} icon={Shield} accent />
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

        {/* Agent Activity */}
        <div className="panel p-5">
          <div className="mb-4 font-mono text-xs uppercase tracking-[0.16em] text-accent">Agent Token Usage</div>
          <AgentBar stats={data.agent_stats || {}} />
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
        <div className="panel p-5 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-danger" />
              <span className="font-mono text-xs uppercase tracking-[0.16em] text-accent">
                CISA Known Exploited Vulnerabilities
              </span>
            </div>
            <div className="flex gap-4 font-mono text-[10px] text-dim">
              <span>{data.cisa_kev?.total_kevs || 0} total KEVs</span>
              <span>{data.cisa_kev?.recent_count || 0} added last 30 days</span>
            </div>
          </div>
          {(data.cisa_kev?.recent_30d || []).length === 0 ? (
            <div className="font-mono text-xs text-dim">No recent KEVs or unable to fetch CISA feed</div>
          ) : (
            <div className="overflow-auto max-h-60">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-panel">
                  <tr className="border-b border-border">
                    <th className="px-3 py-1 text-left font-mono text-[10px] uppercase text-dim">CVE</th>
                    <th className="px-3 py-1 text-left font-mono text-[10px] uppercase text-dim">Vendor</th>
                    <th className="px-3 py-1 text-left font-mono text-[10px] uppercase text-dim">Product</th>
                    <th className="px-3 py-1 text-left font-mono text-[10px] uppercase text-dim">Vulnerability</th>
                    <th className="px-3 py-1 text-left font-mono text-[10px] uppercase text-dim">Added</th>
                    <th className="px-3 py-1 text-left font-mono text-[10px] uppercase text-dim">Due</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {data.cisa_kev.recent_30d.map((v) => (
                    <tr key={v.cve} className="hover:bg-panel2">
                      <td className="px-3 py-1.5 font-mono text-[11px] text-danger">{v.cve}</td>
                      <td className="px-3 py-1.5 font-mono text-[11px] text-text">{v.vendor}</td>
                      <td className="px-3 py-1.5 font-mono text-[11px] text-text">{v.product}</td>
                      <td className="px-3 py-1.5 text-xs text-dim line-clamp-1">{v.name}</td>
                      <td className="px-3 py-1.5 font-mono text-[10px] text-dim">{v.date_added}</td>
                      <td className="px-3 py-1.5 font-mono text-[10px] text-amber">{v.due_date}</td>
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
