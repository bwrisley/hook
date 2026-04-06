import { useEffect, useState } from 'react'
import { api, AGENT_LABELS } from '../lib/api.js'

function formatCost(usd) {
  if (!usd) return '$0.00'
  if (usd < 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(2)}`
}

function formatTokens(n) {
  if (!n) return '0'
  if (n < 1000) return String(n)
  return `${(n / 1000).toFixed(1)}k`
}

function formatDuration(ms) {
  if (!ms) return '0s'
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

export default function AuditPage() {
  const [entries, setEntries] = useState([])
  const [totals, setTotals] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get('/api/audit')
        setEntries(res.data.entries || [])
        setTotals(res.data.totals || {})
      } catch (err) {
        if (err.response?.status === 403) {
          setError('Admin access required')
        }
      }
      setLoading(false)
    }
    load()
  }, [])

  if (loading) return <div className="font-mono text-sm text-dim">Loading audit log...</div>
  if (error) return <div className="font-mono text-sm text-danger">{error}</div>

  return (
    <div>
      <h1 className="mb-6 font-mono text-sm font-bold uppercase tracking-[0.18em] text-accent">Audit Log</h1>

      {/* Totals bar */}
      <div className="mb-6 panel p-4">
        <div className="flex gap-8">
          <div>
            <div className="font-mono text-2xl font-bold text-text">{totals.total_calls || 0}</div>
            <div className="font-mono text-[10px] uppercase text-dim">Total Calls</div>
          </div>
          <div>
            <div className="font-mono text-2xl font-bold text-text">{formatTokens(totals.total_tokens)}</div>
            <div className="font-mono text-[10px] uppercase text-dim">Total Tokens</div>
          </div>
          <div>
            <div className="font-mono text-2xl font-bold text-accent">{formatCost(totals.total_cost)}</div>
            <div className="font-mono text-[10px] uppercase text-dim">Total Cost</div>
          </div>
        </div>
      </div>

      {/* Log table */}
      <div className="panel overflow-hidden">
        <div className="border-b border-border px-5 py-3 font-mono text-xs uppercase tracking-[0.18em] text-accent">
          Recent Activity ({entries.length} entries)
        </div>
        <div className="overflow-auto max-h-[600px]">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-panel">
              <tr className="border-b border-border">
                <th className="px-4 py-2 text-left font-mono text-[10px] uppercase text-dim">Time</th>
                <th className="px-4 py-2 text-left font-mono text-[10px] uppercase text-dim">User</th>
                <th className="px-4 py-2 text-left font-mono text-[10px] uppercase text-dim">Agent</th>
                <th className="px-4 py-2 text-left font-mono text-[10px] uppercase text-dim">Model</th>
                <th className="px-4 py-2 text-right font-mono text-[10px] uppercase text-dim">Tokens</th>
                <th className="px-4 py-2 text-right font-mono text-[10px] uppercase text-dim">Duration</th>
                <th className="px-4 py-2 text-right font-mono text-[10px] uppercase text-dim">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {entries.map((e, idx) => (
                <tr key={idx} className="hover:bg-panel2">
                  <td className="px-4 py-2 font-mono text-[11px] text-dim">
                    {e.timestamp ? new Date(e.timestamp).toLocaleString() : ''}
                  </td>
                  <td className="px-4 py-2 font-mono text-[11px] text-text">
                    {e.user || '-'}
                  </td>
                  <td className="px-4 py-2 font-mono text-[11px] text-accent">
                    {AGENT_LABELS[e.agent] || e.agent}
                  </td>
                  <td className="px-4 py-2 font-mono text-[11px] text-dim">
                    {e.model}
                  </td>
                  <td className="px-4 py-2 font-mono text-[11px] text-text text-right">
                    {formatTokens(e.tokens_total)}
                  </td>
                  <td className="px-4 py-2 font-mono text-[11px] text-text text-right">
                    {formatDuration(e.duration_ms)}
                  </td>
                  <td className="px-4 py-2 font-mono text-[11px] text-accent text-right">
                    {formatCost(e.cost_usd)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
