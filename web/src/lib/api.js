import axios from 'axios'

export const api = axios.create({
  timeout: 120000,
  withCredentials: true,
})

export async function login(username, password) {
  const res = await api.post('/api/auth/login', { username, password })
  return res.data
}

export async function logout() {
  await api.post('/api/auth/logout')
}

export async function getMe() {
  const res = await api.get('/api/auth/me')
  return res.data
}

/**
 * Stream a chat message via SSE.
 * Shadowbox events: agent_start, agent_result, coordinator, investigation.
 */
export async function streamChat({ message, conversationId, sessionKey, onEvent }) {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      session_key: sessionKey,
    }),
  })

  if (!response.ok || !response.body) {
    throw new Error(`Chat stream failed (${response.status})`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let splitIndex
    while ((splitIndex = buffer.indexOf('\n\n')) !== -1) {
      const chunk = buffer.slice(0, splitIndex)
      buffer = buffer.slice(splitIndex + 2)
      const lines = chunk.split('\n')
      let event = 'message'
      let data = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) event = line.slice(7)
        if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (data) {
        onEvent?.(event, JSON.parse(data))
      }
    }
  }
}

/** Agent ID to display color mapping */
export const AGENT_COLORS = {
  coordinator: 'accent',
  'triage-analyst': 'amber',
  'osint-researcher': 'safe',
  'incident-responder': 'danger',
  'threat-intel': 'blue',
  'report-writer': 'dim',
  'log-querier': 'amber',
}

/** Agent ID to callsign */
export const AGENT_LABELS = {
  coordinator: 'Marshall',
  'triage-analyst': 'Tara',
  'osint-researcher': 'Hunter',
  'incident-responder': 'Ward',
  'threat-intel': 'Driver',
  'report-writer': 'Page',
  'log-querier': 'Wells',
}

/** Agent ID to role description */
export const AGENT_ROLES = {
  coordinator: 'Senior SOC coordinator. Calm, dry, decisive. Earns authority by knowing exactly who to hand work to and giving them everything they need.',
  'triage-analyst': 'Tier 2 SOC analyst. Seen everything twice. Clinical, precise, no-nonsense. Calls what she sees and shows her work.',
  'osint-researcher': 'Infrastructure intelligence analyst. Follows the thread past where most analysts stop. Methodical, thorough, quietly precise.',
  'incident-responder': 'Federal IR lead. Contain first, understand later. Calm, precise, framework-driven. Has been in worse situations than this one.',
  'threat-intel': 'Intelligence analyst. IC-trained, cyber-focused. Precise, measured, patient. Confidence levels mean something here.',
  'report-writer': 'Intelligence writer. Translates what the team found into what the audience needs. Precise, calibrated, quietly authoritative.',
  'log-querier': 'Data engineer turned log intelligence specialist. Literal, precise, technically thorough. Returns what the data shows and nothing it doesn\'t.',
}
