import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import InvestigationTimeline from '../components/InvestigationTimeline.jsx'

const statusBadge = {
  active: 'badge-amber',
  contained: 'badge-accent',
  eradication: 'badge-danger',
  recovery: 'badge-blue',
  monitoring: 'badge-green',
  closed: 'badge-dim',
}

export default function InvestigationsPage() {
  const [investigations, setInvestigations] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get('/api/investigations')
        setInvestigations(res.data.items || [])
      } catch { /* no investigations dir yet */ }
      setLoading(false)
    }
    load()
  }, [])

  const loadDetail = async (id) => {
    setSelected(id)
    try {
      const res = await api.get(`/api/investigations/${id}`)
      setDetail(res.data)
    } catch {
      setDetail(null)
    }
  }

  if (loading) {
    return <div className="font-mono text-sm text-dim">Loading investigations...</div>
  }

  return (
    <div className="flex h-full min-h-0 gap-6">
      {/* List */}
      <div className="panel flex w-96 flex-col overflow-hidden">
        <div className="border-b border-border px-5 py-3 font-mono text-xs uppercase tracking-[0.18em] text-accent">
          Investigations ({investigations.length})
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          {investigations.length === 0 && (
            <div className="p-5 font-mono text-sm text-dim">No investigations recorded yet.</div>
          )}
          {investigations.map((inv) => (
            <button
              key={inv.id}
              className={`w-full border-b border-border p-4 text-left transition hover:bg-panel2 ${
                selected === inv.id ? 'bg-accent/5' : ''
              }`}
              onClick={() => loadDetail(inv.id)}
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold text-accent">{inv.id}</span>
                <span className={`badge ${statusBadge[inv.status] || 'badge-dim'}`}>
                  {inv.status}
                </span>
              </div>
              <div className="mt-1 text-sm text-text">{inv.title}</div>
              <div className="mt-2 flex gap-4 font-mono text-[11px] text-dim">
                <span>{inv.ioc_count} IOCs</span>
                <span>{inv.finding_count} findings</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Detail */}
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <h1 className="font-mono text-sm font-bold uppercase tracking-[0.18em] text-accent">
          Investigation History
        </h1>

        {detail ? (
          <div className="panel flex-1 overflow-auto p-6">
            <div className="flex items-center justify-between">
              <h2 className="font-mono text-lg font-bold text-accent">{detail.id}</h2>
              <span className={`badge ${statusBadge[detail.status] || 'badge-dim'}`}>
                {detail.status}
              </span>
            </div>
            <div className="mt-1 text-text">{detail.title}</div>
            <div className="mt-1 font-mono text-xs text-dim">
              Created: {detail.created_at ? new Date(detail.created_at).toLocaleString() : 'unknown'}
            </div>

            {/* IOCs */}
            {detail.iocs?.length > 0 && (
              <div className="mt-6">
                <h3 className="font-mono text-xs uppercase tracking-[0.16em] text-accent">IOCs</h3>
                <div className="mt-2 overflow-auto rounded-lg border border-border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-panel2">
                        <th className="px-3 py-2 text-left font-mono text-xs text-dim">Type</th>
                        <th className="px-3 py-2 text-left font-mono text-xs text-dim">Value</th>
                        <th className="px-3 py-2 text-left font-mono text-xs text-dim">Context</th>
                        <th className="px-3 py-2 text-left font-mono text-xs text-dim">Risk</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.iocs.map((ioc, idx) => (
                        <tr key={idx} className="border-t border-border">
                          <td className="px-3 py-2 font-mono text-xs uppercase text-dim">{ioc.type}</td>
                          <td className="px-3 py-2 font-mono text-xs text-accent">{ioc.value}</td>
                          <td className="px-3 py-2 text-xs text-text">{ioc.context}</td>
                          <td className="px-3 py-2">
                            <span className={`badge ${
                              ioc.risk === 'HIGH' ? 'badge-danger' :
                              ioc.risk === 'MEDIUM' ? 'badge-amber' : 'badge-green'
                            }`}>{ioc.risk || 'unknown'}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Timeline */}
            {detail.timeline?.length > 0 && (
              <div className="mt-6">
                <h3 className="mb-3 font-mono text-xs uppercase tracking-[0.16em] text-accent">Timeline</h3>
                <InvestigationTimeline events={detail.timeline} />
              </div>
            )}

            {/* Findings */}
            {detail.findings?.length > 0 && (
              <div className="mt-6">
                <h3 className="mb-3 font-mono text-xs uppercase tracking-[0.16em] text-accent">Findings</h3>
                <div className="space-y-3">
                  {detail.findings.map((finding, idx) => (
                    <div key={idx} className="rounded-lg border border-border bg-panel2 p-4">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-accent">{finding.agent}</span>
                        <span className="font-mono text-[10px] text-dim">
                          {finding.timestamp ? new Date(finding.timestamp).toLocaleString() : ''}
                        </span>
                      </div>
                      <div className="mt-2 text-sm text-text">{finding.summary}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="panel flex flex-1 items-center justify-center">
            <div className="font-mono text-sm text-dim">Select an investigation to view details</div>
          </div>
        )}
      </div>
    </div>
  )
}
