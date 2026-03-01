# HOOK Coordinator — TOOLS.md

## Agent Routing Tools

### Discover Available Agents
Use the `agents_list` tool to see which specialist agents are available and their IDs.

### Spawn a Specialist Agent
Use `sessions_spawn` to delegate work to a specialist:

```
sessions_spawn(
  task: "Your detailed task description here",
  agentId: "target-agent-id",
  runTimeoutSeconds: 120
)
```

Available agent IDs:
- `triage-analyst` — Alert triage and verdict
- `osint-researcher` — IOC enrichment (VT, Censys, AbuseIPDB)
- `incident-responder` — NIST 800-61 incident response
- `threat-intel` — Finished intelligence and analytic techniques
- `report-writer` — Reports for any audience

### Important Notes
- `sessions_spawn` is non-blocking — it returns immediately with `{ status: "accepted" }`
- The specialist will announce results back to the Slack channel when complete
- You can spawn multiple specialists in parallel if tasks are independent
- For sequential chains (triage → enrich → report), wait for results before spawning next

## Quick Enrichment — DO NOT SELF-HANDLE

**Never run enrichment queries directly.** Even for a single IOC, always spawn `osint-researcher`. The specialist has multi-source enrichment (VT + Censys + AbuseIPDB + DNS), structured output, and risk assessment logic. A coordinator-run VT-only lookup is incomplete and trains bad habits.

If the user asks to "just quickly check" a single IOC, spawn osint-researcher with a note that it's a single-IOC fast lookup:

```
sessions_spawn(
  agentId: "osint-researcher",
  task: "Quick enrichment — single IOC. Enrich the following IP and return structured findings: 1.2.3.4",
  runTimeoutSeconds: 90
)
```

## Shell Environment

The coordinator does NOT run API calls or enrichment queries directly. The following environment variables exist for specialist agents only:
- `$VT_API_KEY`, `$CENSYS_API_ID`, `$CENSYS_API_SECRET`, `$ABUSEIPDB_API_KEY`

If you need enrichment, DNS lookups, or JSON parsing — spawn the right specialist. That's what they're for.
