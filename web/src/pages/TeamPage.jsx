import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api } from '../lib/api.js'

const actionLabels = {
  enrichment: 'Enrichment',
  triage: 'Triage',
  analysis: 'Threat Analysis',
  report: 'Report',
  watch_alert: 'Watch Alert',
}

const actionBadge = {
  enrichment: 'badge-accent',
  triage: 'badge-amber',
  analysis: 'badge-blue',
  report: 'badge-dim',
  watch_alert: 'badge-danger',
}

const riskBadge = (risk) => {
  if (!risk) return ''
  const map = { HIGH: 'badge-danger', MEDIUM: 'badge-amber', LOW: 'badge-safe', CLEAN: 'badge-safe', UNKNOWN: 'badge-dim' }
  return map[risk] || 'badge-dim'
}

function timeAgo(iso) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

export default function TeamPage() {
  const navigate = useNavigate()
  const [activity, setActivity] = useState([])
  const [loading, setLoading] = useState(true)
  const [iocLookup, setIocLookup] = useState('')
  const [iocHistory, setIocHistory] = useState(null)

  const load = async () => {
    try {
      const res = await api.get('/api/activity')
      setActivity(res.data.items || [])
    } catch { /* offline */ }
    setLoading(false)
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [])

  const lookupIoc = async (value) => {
    const ioc = value || iocLookup
    if (!ioc.trim()) return
    try {
      const res = await api.get(`/api/activity/ioc/${encodeURIComponent(ioc.trim())}`)
      setIocHistory(res.data)
    } catch {
      setIocHistory({ ioc: ioc.trim(), history: [] })
    }
  }

  if (loading) return <div className="font-mono text-sm text-dim">Loading team activity...</div>

  return (
    <div>
      <h1 className="mb-6 font-mono text-sm font-bold uppercase tracking-[0.18em] text-accent">Team Activity</h1>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* IOC Lookup */}
        <div className="panel p-5 lg:col-span-1">
          <div className="mb-4 font-mono text-xs uppercase tracking-[0.16em] text-accent">IOC Lookup</div>
          <div className="mb-3 font-mono text-[10px] text-dim">Check if anyone has already investigated an IOC</div>
          <form onSubmit={(e) => { e.preventDefault(); lookupIoc() }} className="flex gap-2">
            <input
              className="input flex-1"
              placeholder="IP, domain, or hash"
              value={iocLookup}
              onChange={(e) => setIocLookup(e.target.value)}
            />
            <button className="btn btn-primary" type="submit">
              <Search className="h-3.5 w-3.5" />
            </button>
          </form>

          {iocHistory && (
            <div className="mt-4">
              <div className="font-mono text-xs font-bold text-accent mb-2">{iocHistory.ioc}</div>
              {iocHistory.history.length === 0 ? (
                <div className="font-mono text-xs text-dim">No prior activity for this IOC</div>
              ) : (
                <div className="space-y-2 max-h-64 overflow-auto">
                  {iocHistory.history.map((h, idx) => (
                    <div key={idx} className="rounded-lg border border-border/50 bg-panel2 p-2">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[11px] text-text">{h.user_id}</span>
                        <span className="font-mono text-[10px] text-dim">{timeAgo(h.created_at)}</span>
                      </div>
                      <div className="mt-1 flex items-center gap-2">
                        <span className={`badge text-[9px] ${actionBadge[h.action] || 'badge-dim'}`}>{actionLabels[h.action] || h.action}</span>
                        {h.risk && <span className={`badge text-[9px] ${riskBadge(h.risk)}`}>{h.risk}</span>}
                      </div>
                      {h.detail && <div className="mt-1 font-mono text-[10px] text-dim">{h.detail}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Activity Feed */}
        <div className="panel lg:col-span-2">
          <div className="border-b border-border px-5 py-3 flex items-center justify-between">
            <span className="font-mono text-xs uppercase tracking-[0.18em] text-accent">Shared Feed</span>
            <span className="font-mono text-[10px] text-dim">{activity.length} events</span>
          </div>
          <div className="max-h-[600px] overflow-auto">
            {activity.length === 0 ? (
              <div className="p-5 font-mono text-xs text-dim">No team activity yet. Run an investigation to populate the feed.</div>
            ) : (
              <div className="divide-y divide-border/50">
                {activity.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-start gap-3 px-5 py-3 hover:bg-panel2 transition cursor-pointer"
                    onClick={() => {
                      if (item.conversation_id) navigate(`/investigate/${item.conversation_id}`)
                      if (item.ioc_value) lookupIoc(item.ioc_value)
                    }}
                  >
                    <div className="mt-0.5">
                      <span className={`badge text-[9px] ${actionBadge[item.action] || 'badge-dim'}`}>
                        {actionLabels[item.action] || item.action}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[11px] font-bold text-text">{item.user_id}</span>
                        {item.ioc_value && (
                          <span className="font-mono text-[11px] text-accent">{item.ioc_value}</span>
                        )}
                        {item.risk && (
                          <span className={`badge text-[9px] ${riskBadge(item.risk)}`}>{item.risk}</span>
                        )}
                      </div>
                      {item.detail && <div className="mt-0.5 text-xs text-dim">{item.detail}</div>}
                      {item.investigation_id && (
                        <span className="font-mono text-[10px] text-amber">{item.investigation_id}</span>
                      )}
                    </div>
                    <span className="font-mono text-[10px] text-dim whitespace-nowrap">{timeAgo(item.created_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
