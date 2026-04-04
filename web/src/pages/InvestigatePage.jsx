import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Plus, Send, Trash2, X } from 'lucide-react'
import { api, streamChat, AGENT_LABELS } from '../lib/api.js'
import AgentBadge from '../components/AgentBadge.jsx'

export default function InvestigatePage() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const [conversations, setConversations] = useState([])
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [activeAgent, setActiveAgent] = useState(null)
  const [chainProgress, setChainProgress] = useState([])
  const activeId = conversationId || null
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const isStreamingRef = useRef(false)
  const sessionKeyRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => { scrollToBottom() }, [messages, chainProgress])

  const loadConversations = async (autoSelect = false) => {
    try {
      const res = await api.get('/api/conversations')
      const items = res.data.items || []
      setConversations(items)
      if (autoSelect && !activeId && items.length > 0) {
        navigate(`/investigate/${items[0].conversation_id}`, { replace: true })
      }
    } catch { /* gateway may be offline */ }
  }

  const loadMessages = async (convId) => {
    if (!convId) {
      setMessages([])
      return
    }
    try {
      const res = await api.get(`/api/conversations/${convId}/messages`)
      const loaded = (res.data.messages || []).map((msg, idx) => ({
        ...msg,
        id: msg.msg_id ? `db-${msg.msg_id}` : `${msg.timestamp}-${idx}`,
      }))
      setMessages(loaded)
    } catch {
      setMessages([])
    }
  }

  useEffect(() => { loadConversations(true) }, [])

  useEffect(() => {
    if (!isStreamingRef.current) {
      loadMessages(activeId)
    }
  }, [activeId])

  const newChat = () => {
    setMessages([])
    setInput('')
    setActiveAgent(null)
    setChainProgress([])
    sessionKeyRef.current = null
    if (activeId) {
      navigate('/investigate')
    }
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  const deleteConversation = async (convId, e) => {
    e.stopPropagation()
    const conv = conversations.find((c) => c.conversation_id === convId)
    const label = conv?.title || convId
    if (!window.confirm(`Delete investigation "${label}"? This cannot be undone.`)) return
    try {
      await api.delete(`/api/conversations/${convId}`)
      if (activeId === convId) {
        navigate('/investigate')
        setMessages([])
      }
      loadConversations()
    } catch { /* ignore */ }
  }

  const deleteMessage = async (msg) => {
    const msgId = msg.msg_id
    if (!msgId) return
    try {
      await api.delete(`/api/messages/${msgId}`)
      setMessages((prev) => prev.filter((m) => m.msg_id !== msgId))
    } catch { /* ignore */ }
  }

  const send = async () => {
    if (!input.trim() || busy) return
    const outgoing = input.trim()
    const ts = new Date().toISOString()

    const userMsg = { id: `${ts}-user`, role: 'user', content: outgoing, timestamp: ts }
    setMessages((prev) => [...prev, userMsg])
    setBusy(true)
    setActiveAgent('coordinator')
    setChainProgress([{ agent: 'coordinator', status: 'working', startedAt: Date.now() }])
    setInput('')
    isStreamingRef.current = true

    try {
      await streamChat({
        message: outgoing,
        conversationId: activeId,
        sessionKey: sessionKeyRef.current,
        onEvent: (event, payload) => {
          if (event === 'meta') {
            if (payload.conversation_id && !activeId) {
              navigate(`/investigate/${payload.conversation_id}`, { replace: true })
            }
            if (payload.session_key) {
              sessionKeyRef.current = payload.session_key
            }
          }

          if (event === 'agent_start') {
            setActiveAgent(payload.agent)
            setChainProgress((prev) => {
              // Mark previous agent as done
              const updated = prev.map((p) =>
                p.status === 'working' ? { ...p, status: 'done', finishedAt: Date.now() } : p
              )
              // Don't add duplicate entries for the same agent
              if (updated.some((p) => p.agent === payload.agent && p.status === 'done')) {
                return updated
              }
              return [...updated, { agent: payload.agent, status: 'working', startedAt: Date.now() }]
            })
          }

          if (event === 'agent_result') {
            setActiveAgent(null)
            setChainProgress((prev) =>
              prev.map((p) =>
                p.agent === payload.agent && p.status === 'working'
                  ? { ...p, status: 'done', finishedAt: Date.now() }
                  : p
              )
            )
            setMessages((prev) => [...prev, {
              id: `${Date.now()}-result-${payload.agent}`,
              role: 'assistant',
              agent: payload.agent,
              content: payload.content,
              timestamp: new Date().toISOString(),
              type: 'agent_result',
            }])
          }

          if (event === 'coordinator') {
            setChainProgress((prev) =>
              prev.map((p) =>
                p.agent === 'coordinator' && p.status === 'working'
                  ? { ...p, status: 'done', finishedAt: Date.now() }
                  : p
              )
            )
            setMessages((prev) => [...prev, {
              id: `${Date.now()}-coord`,
              role: 'assistant',
              agent: 'coordinator',
              content: payload.content,
              timestamp: new Date().toISOString(),
              type: 'coordinator',
            }])
          }

          if (event === 'error') {
            setMessages((prev) => [...prev, {
              id: `${Date.now()}-error`,
              role: 'system',
              content: `Error: ${payload.message}`,
              timestamp: new Date().toISOString(),
              type: 'error',
            }])
          }
        },
      })
    } catch (err) {
      setMessages((prev) => [...prev, {
        id: `${Date.now()}-err`,
        role: 'system',
        content: `Connection error: ${err.message}`,
        timestamp: new Date().toISOString(),
        type: 'error',
      }])
    } finally {
      isStreamingRef.current = false
      setBusy(false)
      setActiveAgent(null)
      setChainProgress([])
      loadConversations()
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const getBorderClass = (msg) => {
    if (msg.type === 'error') return 'border-danger/30 bg-danger/5'
    if (msg.type === 'agent_start') return 'border-amber/20 bg-amber/5'
    if (msg.role === 'user') return 'border-border bg-panel2'
    return 'border-accent/20 bg-accent/5'
  }

  const formatDuration = (ms) => {
    if (!ms) return ''
    const s = Math.round(ms / 1000)
    return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
  }

  return (
    <div className="flex h-full min-h-0 gap-6">
      {/* Conversation sidebar */}
      <div className="panel flex w-72 flex-col overflow-hidden">
        <div className="border-b border-border p-4">
          <button className="btn btn-primary w-full" onClick={newChat}>
            <Plus className="h-4 w-4" /> New Investigation
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-3 space-y-2">
          {conversations.map((conv) => (
            <div
              key={conv.conversation_id}
              className={`group relative rounded-xl border p-3 transition ${
                activeId === conv.conversation_id
                  ? 'border-accent bg-accent/10'
                  : 'border-border bg-panel2 hover:bg-panel2'
              }`}
            >
              <button
                className="w-full text-left"
                onClick={() => navigate(`/investigate/${conv.conversation_id}`)}
              >
                <div className="truncate font-mono text-xs text-accent pr-6">
                  {conv.title || conv.conversation_id}
                </div>
                <div className="mt-1 font-mono text-[10px] text-dim">
                  {conv.last_message_at ? new Date(conv.last_message_at).toLocaleString() : ''}
                </div>
              </button>
              <button
                className="absolute right-2 top-3 hidden text-dim hover:text-danger group-hover:block"
                onClick={(e) => deleteConversation(conv.conversation_id, e)}
                title="Delete conversation"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <div className="flex items-center justify-between">
          <h1 className="font-mono text-sm font-bold uppercase tracking-[0.18em] text-accent">Investigate</h1>
          {activeAgent && busy && (
            <div className="flex items-center gap-2">
              <AgentBadge agentId={activeAgent} />
              <span className="inline-flex items-center gap-1 font-mono text-xs text-accent">
                working
                <span className="activity-ellipsis" aria-hidden="true">
                  <span /><span /><span />
                </span>
              </span>
            </div>
          )}
        </div>

        <div className="panel flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="min-h-0 flex-1 space-y-3 overflow-auto p-5">
            {messages.length === 0 && !busy && (
              <div className="flex h-full items-center justify-center">
                <div className="text-center">
                  <div className="font-mono text-sm uppercase tracking-[0.18em] text-dim">
                    Submit an alert, IOC, or question
                  </div>
                  <div className="mt-2 font-mono text-xs text-dim">
                    Shadowbox will route to the appropriate specialist
                  </div>
                </div>
              </div>
            )}
            {messages.map((msg) => (
              <div key={msg.id} className={`group relative rounded-xl border p-4 ${getBorderClass(msg)}`}>
                <div className="mb-2 flex items-center gap-2">
                  {msg.agent ? (
                    <AgentBadge agentId={msg.agent} />
                  ) : (
                    <span className="font-mono text-xs uppercase tracking-[0.18em] text-dim">
                      {msg.role === 'user' ? 'Operator' : 'System'}
                    </span>
                  )}
                  <span className="font-mono text-[10px] text-dim">
                    {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : ''}
                  </span>
                  {msg.msg_id && (
                    <button
                      className="ml-auto hidden text-dim hover:text-danger group-hover:block"
                      onClick={() => deleteMessage(msg)}
                      title="Delete message"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
                <div className="markdown text-sm">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              </div>
            ))}

            {/* Chain progress indicator */}
            {busy && chainProgress.length > 0 && (
              <div className="rounded-xl border border-accent/20 bg-accent/5 p-4">
                <div className="mb-3 font-mono text-xs uppercase tracking-[0.16em] text-accent">
                  Chain Progress
                </div>
                <div className="flex flex-wrap gap-2">
                  {chainProgress.map((step, idx) => {
                    const label = AGENT_LABELS[step.agent] || step.agent
                    const duration = step.finishedAt ? formatDuration(step.finishedAt - step.startedAt) : ''
                    return (
                      <div key={`${step.agent}-${idx}`} className="flex items-center gap-1.5">
                        {idx > 0 && <span className="text-dim">&#8250;</span>}
                        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[11px] ${
                          step.status === 'working'
                            ? 'border-accent/40 bg-accent/15 text-accent'
                            : 'border-safe/30 bg-safe/10 text-safe'
                        }`}>
                          {step.status === 'working' && (
                            <span className="activity-ellipsis" aria-hidden="true">
                              <span /><span /><span />
                            </span>
                          )}
                          {step.status === 'done' && <span>&#10003;</span>}
                          {label}
                          {duration && <span className="text-dim ml-1">{duration}</span>}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          <div className="border-t border-border p-4">
            <div className="flex gap-2">
              <textarea
                ref={inputRef}
                className="textarea min-h-16 flex-1"
                placeholder="Describe an alert, paste IOCs, or ask a security question... Enter to send, Shift+Enter for newline"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={2}
              />
              <button
                className="btn btn-primary self-end"
                onClick={send}
                disabled={busy || !input.trim()}
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
