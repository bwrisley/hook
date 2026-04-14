import { useEffect, useState } from 'react'
import { Eye, EyeOff, ExternalLink, Plus } from 'lucide-react'
import { api } from '../lib/api.js'

const categoryLabels = {
  c2: 'Command & Control',
  malware_distribution: 'Malware Distribution',
  malware_iocs: 'Malware IOCs',
  combined: 'Combined Feed',
  unknown: 'Threat Intel',
}

const categoryBadge = {
  c2: 'badge-danger',
  malware_distribution: 'badge-amber',
  malware_iocs: 'badge-accent',
  combined: 'badge-dim',
  unknown: 'badge-dim',
}

export default function FeedsPage() {
  const [feeds, setFeeds] = useState([])
  const [totalIocs, setTotalIocs] = useState(0)
  const [iocBreakdown, setIocBreakdown] = useState({})
  const [watchlistCount, setWatchlistCount] = useState(0)
  const [watched, setWatched] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [newIoc, setNewIoc] = useState({ ioc_value: '', ioc_type: 'ip' })

  const load = async () => {
    try {
      const [feedsRes, watchRes] = await Promise.all([
        api.get('/api/feeds'),
        api.get('/api/watchlist'),
      ])
      setFeeds(feedsRes.data.feeds || [])
      setTotalIocs(feedsRes.data.total_iocs || 0)
      setIocBreakdown(feedsRes.data.ioc_breakdown || {})
      setWatchlistCount(feedsRes.data.watchlist_count || 0)
      setWatched(watchRes.data.items || [])
    } catch { /* offline */ }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const addWatch = async (e) => {
    e.preventDefault()
    if (!newIoc.ioc_value) return
    try {
      await api.post('/api/watchlist', newIoc)
      setNewIoc({ ioc_value: '', ioc_type: 'ip' })
      setShowAdd(false)
      load()
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to add')
    }
  }

  const removeWatch = async (ioc_value) => {
    if (!window.confirm(`Stop watching ${ioc_value}?`)) return
    await api.delete(`/api/watchlist/${encodeURIComponent(ioc_value)}`)
    load()
  }

  const riskBadge = (risk) => {
    const map = { HIGH: 'badge-danger', CRITICAL: 'badge-danger', MEDIUM: 'badge-amber', LOW: 'badge-accent', CLEAN: 'badge-safe', UNKNOWN: 'badge-dim' }
    return map[risk] || 'badge-dim'
  }

  const timeAgo = (iso) => {
    if (!iso) return 'unknown'
    const diff = Date.now() - new Date(iso).getTime()
    const hours = Math.floor(diff / 3600000)
    if (hours < 1) return 'just now'
    if (hours < 24) return `${hours}h ago`
    return `${Math.floor(hours / 24)}d ago`
  }

  if (loading) return <div className="font-mono text-sm text-dim">Loading feeds...</div>

  // Separate feed sources from combined
  const sourceFeed = feeds.filter((f) => !f.name.startsWith('combined'))
  const combinedFeed = feeds.find((f) => f.name.startsWith('combined'))

  return (
    <div>
      <h1 className="mb-6 font-mono text-sm font-bold uppercase tracking-[0.18em] text-accent">Feeds & Watchlist</h1>

      {/* Feed summary bar */}
      <div className="mb-6 panel p-4">
        <div className="flex gap-8">
          <div>
            <div className="font-mono text-2xl font-bold text-text">{totalIocs}</div>
            <div className="font-mono text-[10px] uppercase text-dim">Total Feed IOCs</div>
          </div>
          <div>
            <div className="font-mono text-2xl font-bold text-text">{iocBreakdown.ip || 0}</div>
            <div className="font-mono text-[10px] uppercase text-dim">IPs</div>
          </div>
          <div>
            <div className="font-mono text-2xl font-bold text-text">{iocBreakdown.domain || 0}</div>
            <div className="font-mono text-[10px] uppercase text-dim">Domains</div>
          </div>
          <div>
            <div className="font-mono text-2xl font-bold text-text">{iocBreakdown.hash || 0}</div>
            <div className="font-mono text-[10px] uppercase text-dim">Hashes</div>
          </div>
          <div>
            <div className="font-mono text-2xl font-bold text-accent">{watched.length}</div>
            <div className="font-mono text-[10px] uppercase text-dim">Watched</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Feed Sources */}
        <div className="panel lg:col-span-2">
          <div className="border-b border-border px-5 py-3 font-mono text-xs uppercase tracking-[0.18em] text-accent">
            Threat Intelligence Sources
          </div>
          <div className="p-4">
            {sourceFeed.length === 0 ? (
              <div className="font-mono text-sm text-dim">No feed data. Run ./scripts/fetch-feeds.sh</div>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                {sourceFeed.map((feed) => (
                  <div key={feed.name} className="rounded-lg border border-border bg-panel2 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono text-xs font-bold text-text">{feed.source}</span>
                      <span className={`badge text-[9px] ${categoryBadge[feed.category] || 'badge-dim'}`}>
                        {categoryLabels[feed.category] || feed.category}
                      </span>
                    </div>
                    <div className="text-xs text-dim mb-3">{feed.description}</div>
                    <div className="space-y-1">
                      <div className="kv">
                        <span className="font-mono text-[10px] text-dim">Provider</span>
                        <span className="font-mono text-[10px] text-text">{feed.provider}</span>
                      </div>
                      <div className="kv">
                        <span className="font-mono text-[10px] text-dim">IOCs</span>
                        <span className="font-mono text-[10px] text-text">{feed.ioc_count}</span>
                      </div>
                      <div className="kv">
                        <span className="font-mono text-[10px] text-dim">Breakdown</span>
                        <span className="font-mono text-[10px] text-text">
                          {feed.breakdown?.ip > 0 && `${feed.breakdown.ip} IPs`}
                          {feed.breakdown?.domain > 0 && ` ${feed.breakdown.domain} domains`}
                          {feed.breakdown?.hash > 0 && ` ${feed.breakdown.hash} hashes`}
                        </span>
                      </div>
                      <div className="kv">
                        <span className="font-mono text-[10px] text-dim">Updated</span>
                        <span className="font-mono text-[10px] text-text">{timeAgo(feed.last_modified)}</span>
                      </div>
                    </div>
                    {feed.url && (
                      <a href={feed.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 font-mono text-[10px] text-accent hover:underline">
                        <ExternalLink className="h-3 w-3" /> Source
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* IOC Watchlist */}
        <div className="panel lg:col-span-2">
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <span className="font-mono text-xs uppercase tracking-[0.18em] text-accent">
              IOC Watchlist ({watched.length})
            </span>
            <button className="btn btn-primary text-[10px] py-1" onClick={() => setShowAdd(!showAdd)}>
              <Plus className="h-3 w-3" /> Watch IOC
            </button>
          </div>

          {showAdd && (
            <div className="border-b border-border p-4">
              <form onSubmit={addWatch} className="flex gap-2 items-end">
                <div className="flex-1">
                  <label className="block font-mono text-[10px] uppercase text-dim mb-1">IOC Value</label>
                  <input className="input" placeholder="IP, domain, or hash" value={newIoc.ioc_value} onChange={(e) => setNewIoc({ ...newIoc, ioc_value: e.target.value })} />
                </div>
                <div className="w-32">
                  <label className="block font-mono text-[10px] uppercase text-dim mb-1">Type</label>
                  <select className="input" value={newIoc.ioc_type} onChange={(e) => setNewIoc({ ...newIoc, ioc_type: e.target.value })}>
                    <option value="ip">IP</option>
                    <option value="domain">Domain</option>
                    <option value="hash">Hash</option>
                  </select>
                </div>
                <button className="btn btn-primary" type="submit">Add</button>
                <button className="btn" type="button" onClick={() => setShowAdd(false)}>Cancel</button>
              </form>
            </div>
          )}

          <div className="p-4">
            {watched.length === 0 ? (
              <div className="font-mono text-sm text-dim">No IOCs being watched. Add one to monitor for risk changes.</div>
            ) : (
              <div className="overflow-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-dim">IOC</th>
                      <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-dim">Type</th>
                      <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-dim">Risk</th>
                      <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-dim">Checks</th>
                      <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-dim">Last Checked</th>
                      <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-dim">Last Changed</th>
                      <th className="px-3 py-2"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50">
                    {watched.map((w) => (
                      <tr key={w.ioc_value} className="hover:bg-panel2">
                        <td className="px-3 py-2 font-mono text-xs text-accent">{w.ioc_value}</td>
                        <td className="px-3 py-2 font-mono text-[11px] uppercase text-dim">{w.ioc_type}</td>
                        <td className="px-3 py-2"><span className={`badge ${riskBadge(w.current_risk)}`}>{w.current_risk}</span></td>
                        <td className="px-3 py-2 font-mono text-xs text-text">{w.check_count}</td>
                        <td className="px-3 py-2 font-mono text-[10px] text-dim">{w.last_checked ? timeAgo(w.last_checked) : 'never'}</td>
                        <td className="px-3 py-2 font-mono text-[10px] text-dim">{w.last_changed ? timeAgo(w.last_changed) : 'never'}</td>
                        <td className="px-3 py-2">
                          <button className="text-dim hover:text-danger" onClick={() => removeWatch(w.ioc_value)} title="Stop watching">
                            <EyeOff className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
