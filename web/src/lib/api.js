import axios from 'axios'

export const api = axios.create({
  timeout: 120000,
})

/**
 * Stream a chat message via SSE.
 * Shadowbox events: agent_start, agent_result, coordinator, investigation.
 */
export async function streamChat({ message, conversationId, sessionKey, onEvent }) {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
  coordinator: 'Routes requests, chains workflows',
  'triage-analyst': 'Alert triage: TP/FP/Suspicious/Escalate',
  'osint-researcher': 'IOC enrichment via VT, Censys, AbuseIPDB',
  'incident-responder': 'NIST 800-61 IR guidance',
  'threat-intel': 'Structured analytic techniques (ACH)',
  'report-writer': 'Audience-adapted reports',
  'log-querier': 'Natural language log queries',
}
