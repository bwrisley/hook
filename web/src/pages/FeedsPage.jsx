import { useEffect, useState } from 'react'
import { Eye, EyeOff, Plus } from 'lucide-react'
import { api } from '../lib/api.js'

export default function FeedsPage() {
  const [feeds, setFeeds] = useState([])
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

  const formatBytes = (bytes) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const riskBadge = (risk) => {
    const map = { HIGH: 'badge-danger', CRITICAL: 'badge-danger', MEDIUM: 'badge-amber', LOW: 'badge-accent', CLEAN: 'badge-safe', UNKNOWN: 'badge-dim' }
    return map[risk] || 'badge-dim'
  }

  if (loading) return <div className="font-mono text-sm text-dim">Loading feeds...</div>

  return (
    <div>
      <h1 className="mb-6 font-mono text-sm font-bold uppercase tracking-[0.18em] text-accent">Feeds & Watchlist</h1>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
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
                        <td className="px-3 py-2 font-mono text-[10px] text-dim">{w.last_checked ? new Date(w.last_checked).toLocaleString() : 'never'}</td>
                        <td className="px-3 py-2 font-mono text-[10px] text-dim">{w.last_changed ? new Date(w.last_changed).toLocaleString() : 'never'}</td>
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

        {/* Feed files */}
        <div className="panel">
          <div className="border-b border-border px-5 py-3 font-mono text-xs uppercase tracking-[0.18em] text-accent">
            Feed Sources ({feeds.length})
          </div>
          <div className="p-4">
            {feeds.length === 0 ? (
              <div className="font-mono text-sm text-dim">No feed data. Run ./scripts/fetch-feeds.sh</div>
            ) : (
              <div className="space-y-2">
                {feeds.map((feed) => (
                  <div key={feed.name} className="kv">
                    <div>
                      <div className="font-mono text-xs text-text">{feed.name}</div>
                      <div className="font-mono text-[10px] text-dim">
                        {feed.last_modified ? new Date(feed.last_modified).toLocaleString() : 'unknown'}
                      </div>
                    </div>
                    <span className="font-mono text-xs text-dim">{formatBytes(feed.size_bytes)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Legacy watchlist */}
        <div className="panel">
          <div className="border-b border-border px-5 py-3 font-mono text-xs uppercase tracking-[0.18em] text-accent">
            Legacy Watchlist (file-based)
          </div>
          <div className="flex flex-col items-center justify-center p-8">
            <div className="font-mono text-4xl font-bold text-accent">{watchlistCount}</div>
            <div className="mt-2 font-mono text-xs uppercase tracking-[0.16em] text-dim">IOCs in watchlist.txt</div>
          </div>
        </div>
      </div>
    </div>
  )
}
