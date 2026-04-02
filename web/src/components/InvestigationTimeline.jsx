import AgentBadge from './AgentBadge.jsx'

export default function InvestigationTimeline({ events }) {
  if (!events || events.length === 0) {
    return <div className="font-mono text-sm text-dim">No events recorded.</div>
  }

  return (
    <div className="space-y-3">
      {events.map((event, idx) => (
        <div key={idx} className="flex gap-3">
          <div className="flex flex-col items-center">
            <div className="h-2 w-2 rounded-full bg-accent" />
            {idx < events.length - 1 && <div className="w-px flex-1 bg-border" />}
          </div>
          <div className="pb-3">
            <div className="flex items-center gap-2">
              {event.agent && <AgentBadge agentId={event.agent} />}
              <span className="font-mono text-[11px] text-dim">
                {event.timestamp ? new Date(event.timestamp).toLocaleString() : ''}
              </span>
            </div>
            <div className="mt-1 text-sm text-text">{event.event || event.summary || ''}</div>
          </div>
        </div>
      ))}
    </div>
  )
}
