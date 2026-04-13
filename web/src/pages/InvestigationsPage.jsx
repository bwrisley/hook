import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MessageSquare } from 'lucide-react'
import { api, AGENT_LABELS } from '../lib/api.js'
import AgentBadge from '../components/AgentBadge.jsx'
import InvestigationTimeline from '../components/InvestigationTimeline.jsx'

const STATUS_OPTIONS = ['active', 'contained', 'eradication', 'recovery', 'monitoring', 'closed']
const DISPOSITIONS = ['resolved', 'false-positive', 'escalated', 'inconclusive']

const statusBadge = {
  active: 'badge-amber',
  contained: 'badge-accent',
  eradication: 'badge-danger',
  recovery: 'badge-blue',
  monitoring: 'badge-safe',
  closed: 'badge-dim',
}

const riskBadge = (risk) => {
  const map = { HIGH: 'badge-danger', CRITICAL: 'badge-danger', MEDIUM: 'badge-amber', LOW: 'badge-accent', CLEAN: 'badge-safe' }
  return map[risk] || 'badge-dim'
}

export default function InvestigationsPage() {
  const navigate = useNavigate()
  const [investigations, setInvestigations] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [expandedFinding, setExpandedFinding] = useState(null)

  const load = async () => {
    try {
      const res = await api.get('/api/investigations')
      setInvestigations(res.data.items || [])
    } catch { /* no investigations dir */ }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const loadDetail = async (id) => {
    setSelected(id)
    setExpandedFinding(null)
    try {
      const res = await api.get(`/api/investigations/${id}`)
      setDetail(res.data)
    } catch {
      setDetail(null)
    }
  }

  const updateStatus = async (id, newStatus) => {
    try {
      await api.put(`/api/investigations/${id}/status`, { status: newStatus })
      loadDetail(id)
      load()
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to update status')
    }
  }

  const closeInvestigation = async (id) => {
    const disposition = window.prompt('Disposition (resolved, false-positive, escalated, inconclusive):')
    if (!disposition || !DISPOSITIONS.includes(disposition)) {
      alert('Invalid disposition. Options: ' + DISPOSITIONS.join(', '))
      return
    }
    try {
      await api.put(`/api/investigations/${id}/status`, { status: 'closed', disposition })
      loadDetail(id)
      load()
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to close')
    }
  }

  const addNote = async (id) => {
    const note = window.prompt('Add note:')
    if (!note) return
    try {
      await api.post(`/api/investigations/${id}/notes`, { note })
      loadDetail(id)
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to add note')
    }
  }

  if (loading) return <div className="font-mono text-sm text-dim">Loading investigations...</div>

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
                <span className={`badge ${statusBadge[inv.status] || 'badge-dim'}`}>{inv.status}</span>
              </div>
              <div className="mt-1 text-sm text-text line-clamp-2">{inv.title}</div>
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
          Investigations
        </h1>

        {detail ? (
          <div className="panel flex-1 overflow-auto p-6">
            {/* Header */}
            <div className="flex items-start justify-between">
              <div>
                <h2 className="font-mono text-lg font-bold text-accent">{detail.id}</h2>
                <div className="mt-1 text-text">{detail.title}</div>
                <div className="mt-1 font-mono text-xs text-dim">
                  Created: {detail.created_at ? new Date(detail.created_at).toLocaleString() : 'unknown'}
                  {detail.disposition && <span className="ml-3">Disposition: <strong>{detail.disposition}</strong></span>}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {detail.conversation_id && (
                  <button
                    className="btn text-[10px] py-1"
                    onClick={() => navigate(`/investigate/${detail.conversation_id}`)}
                    title="View the chat conversation for this investigation"
                  >
                    <MessageSquare className="h-3 w-3" /> View Chat
                  </button>
                )}
                <select
                  className="input w-auto text-[11px] py-1 px-2"
                  value={detail.status}
                  onChange={(e) => updateStatus(detail.id, e.target.value)}
                >
                  {STATUS_OPTIONS.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                {detail.status !== 'closed' && (
                  <button className="btn btn-danger text-[10px] py-1" onClick={() => closeInvestigation(detail.id)}>
                    Close
                  </button>
                )}
              </div>
            </div>

            {/* IOCs */}
            {detail.iocs?.length > 0 && (
              <div className="mt-6">
                <h3 className="font-mono text-xs uppercase tracking-[0.16em] text-accent">IOCs ({detail.iocs.length})</h3>
                <div className="mt-2 overflow-auto rounded-lg border border-border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-panel2">
                        <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-dim">Type</th>
                        <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-dim">Value</th>
                        <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-dim">Context</th>
                        <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-dim">Risk</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.iocs.map((ioc, idx) => (
                        <tr key={idx} className="border-t border-border">
                          <td className="px-3 py-2 font-mono text-[11px] uppercase text-dim">{ioc.type}</td>
                          <td className="px-3 py-2 font-mono text-[11px] text-accent">{ioc.value}</td>
                          <td className="px-3 py-2 text-xs text-text">{ioc.context}</td>
                          <td className="px-3 py-2"><span className={`badge ${riskBadge(ioc.risk)}`}>{ioc.risk || '?'}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Findings */}
            {detail.findings?.length > 0 && (
              <div className="mt-6">
                <h3 className="mb-3 font-mono text-xs uppercase tracking-[0.16em] text-accent">
                  Findings ({detail.findings.length})
                </h3>
                <div className="space-y-3">
                  {detail.findings.map((finding, idx) => (
                    <div key={idx} className="rounded-lg border border-border bg-panel2 p-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <AgentBadge agentId={finding.agent} />
                          <span className="font-mono text-[10px] text-dim">
                            {finding.timestamp ? new Date(finding.timestamp).toLocaleString() : ''}
                          </span>
                        </div>
                        {finding.file && (
                          <button
                            className="font-mono text-[10px] text-accent hover:underline"
                            onClick={() => setExpandedFinding(expandedFinding === idx ? null : idx)}
                          >
                            {expandedFinding === idx ? 'Collapse' : 'Expand'}
                          </button>
                        )}
                      </div>
                      <div className="mt-2 text-sm text-text">{finding.summary}</div>
                      {expandedFinding === idx && finding.detail && (
                        <div className="mt-3 rounded-lg border border-border/50 bg-panel p-3">
                          <pre className="whitespace-pre-wrap font-mono text-xs text-dim">{finding.detail}</pre>
                        </div>
                      )}
                    </div>
                  ))}
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

            {/* Notes */}
            <div className="mt-6">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-mono text-xs uppercase tracking-[0.16em] text-accent">
                  Notes ({detail.notes?.length || 0})
                </h3>
                <button className="font-mono text-[10px] text-accent hover:underline" onClick={() => addNote(detail.id)}>
                  + Add note
                </button>
              </div>
              {(detail.notes || []).length === 0 ? (
                <div className="font-mono text-xs text-dim">No notes yet.</div>
              ) : (
                <div className="space-y-2">
                  {detail.notes.map((note, idx) => (
                    <div key={idx} className="rounded-lg border border-border/50 bg-panel2 p-3">
                      <div className="font-mono text-[10px] text-dim">
                        {note.timestamp ? new Date(note.timestamp).toLocaleString() : ''} {note.author && `by ${note.author}`}
                      </div>
                      <div className="mt-1 text-sm text-text">{note.text}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Detail files */}
            {detail.findings_detail?.length > 0 && (
              <div className="mt-6">
                <h3 className="mb-3 font-mono text-xs uppercase tracking-[0.16em] text-accent">
                  Finding Reports ({detail.findings_detail.length})
                </h3>
                <div className="space-y-2">
                  {detail.findings_detail.map((fd, idx) => (
                    <details key={idx} className="rounded-lg border border-border bg-panel2">
                      <summary className="cursor-pointer px-4 py-2 font-mono text-xs text-accent">
                        {fd.filename}
                      </summary>
                      <div className="border-t border-border p-4">
                        <pre className="whitespace-pre-wrap font-mono text-xs text-text">{fd.content}</pre>
                      </div>
                    </details>
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
