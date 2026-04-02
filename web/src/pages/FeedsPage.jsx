import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'

export default function FeedsPage() {
  const [feeds, setFeeds] = useState([])
  const [watchlistCount, setWatchlistCount] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get('/api/feeds')
        setFeeds(res.data.feeds || [])
        setWatchlistCount(res.data.watchlist_count || 0)
      } catch { /* feeds dir may not exist */ }
      setLoading(false)
    }
    load()
  }, [])

  if (loading) {
    return <div className="font-mono text-sm text-dim">Loading feeds...</div>
  }

  const formatBytes = (bytes) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div>
      <h1 className="mb-6 font-mono text-sm font-bold uppercase tracking-[0.18em] text-accent">Threat Feeds</h1>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Feed files */}
        <div className="panel">
          <div className="border-b border-border px-5 py-3 font-mono text-xs uppercase tracking-[0.18em] text-accent">
            Feed Sources ({feeds.length})
          </div>
          <div className="p-4">
            {feeds.length === 0 ? (
              <div className="font-mono text-sm text-dim">
                No feed data. Run ./scripts/fetch-feeds.sh to pull threat intel.
              </div>
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

        {/* Watchlist */}
        <div className="panel">
          <div className="border-b border-border px-5 py-3 font-mono text-xs uppercase tracking-[0.18em] text-accent">
            Watchlist
          </div>
          <div className="flex flex-col items-center justify-center p-8">
            <div className="font-mono text-4xl font-bold text-accent">{watchlistCount}</div>
            <div className="mt-2 font-mono text-xs uppercase tracking-[0.16em] text-dim">
              Active IOCs
            </div>
            <div className="mt-4 font-mono text-xs text-dim">
              Managed via ./scripts/watchlist.sh
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
