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
- `sessions_spawn` is non-blocking — it returns immediately with `{ status: "accepted", runId, childSessionKey }`
- **Save the `childSessionKey`** — you need it to read results via `sessions_history`
- The specialist will announce results back to the Slack channel when complete
- You can spawn multiple specialists in parallel if tasks are independent
- For sequential chains (triage → enrich → report), wait for announce before spawning next

### Read Subagent Results
After a subagent announces back, you can get the full transcript if the announce text is truncated or you need specific details:

```
sessions_history(
  sessionKey: "<childSessionKey from sessions_spawn>",
  limit: 10
)
```

This returns the subagent's full conversation including tool calls and outputs. Use it when:
- The announce text is truncated or missing detail
- You need to extract specific data points (e.g., exact VT scores) for the next chain step
- You want to verify what the subagent actually did

### List Active Subagents
```
sessions_list()
```
Check which subagents are still running or have completed.

## Investigation State Files

For multi-step investigations, write a state file to track chain progress. This survives context compaction and gives you a persistent record.

### Write State
```
exec: cat > investigation-state.md << 'EOF'
# Investigation: Suspicious PowerShell on WKSTN-FIN-042
## Status: in-progress
## Started: 2026-03-01T14:30:00Z

### Chain Progress
- [x] Triage: TP, High confidence
- [ ] OSINT: Pending
- [ ] Report: Pending

### Accumulated Findings
Triage verdict: True Positive (85% confidence)
ATT&CK: T1059.001 (PowerShell), T1071.001 (Web Protocols)

### Extracted IOCs
| IOC | Type | Risk | Source |
|-----|------|------|--------|
| 45.77.65.211 | IP | TBD | Triage extraction |

### Next Step
Spawn osint-researcher for IOC enrichment
EOF
```

### Read State
```
exec: cat investigation-state.md
```

Read the state file at the start of each chain step to recover context. Update it after each subagent announces back.

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

## Lobster Pipelines (Deterministic Enrichment)

Lobster runs deterministic shell pipelines — no LLM cost per step, no token overhead. Use these for structured enrichment when you don't need LLM judgment.

**When to use Lobster vs Agent chains:**
- **Lobster** → "Enrich this IP" / "Run this IOC through all sources" / "Process this alert's IOCs" — pure data enrichment, structured output
- **Agent chain** → "Triage this alert" / "Is this a true positive?" / "Write me a report for the CISO" — requires judgment, analysis, or audience adaptation

### Available Pipelines

**Single IOC enrichment:**
```
lobster(
  action: "run",
  pipeline: "pipelines/ioc-enrich-ip.yaml",
  args: {"ip": "45.77.65.211"},
  timeoutMs: 30000
)
```

```
lobster(
  action: "run",
  pipeline: "pipelines/ioc-enrich-domain.yaml",
  args: {"domain": "evil-update.com"},
  timeoutMs: 30000
)
```

**Full alert enrichment (extract → enrich all → report):**
```
lobster(
  action: "run",
  pipeline: "pipelines/alert-to-report.yaml",
  args: {"alert_text": "[paste full alert text]"},
  timeoutMs: 120000
)
```

**Batch IOC check (from file):**
```
lobster(
  action: "run",
  pipeline: "pipelines/batch-ioc-check.yaml",
  args: {"ioc_file": "feeds/daily-iocs.txt"},
  timeoutMs: 300000
)
```

### Combining Lobster + Agents

For a full investigation, you can use Lobster for fast enrichment then hand results to an agent for analysis:

1. Run `alert-to-report` pipeline → get structured enrichment JSON
2. Read the pipeline output
3. Spawn `triage-analyst` or `threat-intel` with the enrichment data in the task description
4. Spawn `report-writer` with both enrichment + analysis findings

This is faster and cheaper than a pure agent chain because the enrichment steps don't consume LLM tokens.

## Shell Environment

The coordinator does NOT run API calls or enrichment queries directly. The following environment variables exist for specialist agents only:
- `$VT_API_KEY`, `$CENSYS_API_ID`, `$CENSYS_API_SECRET`, `$ABUSEIPDB_API_KEY`

The coordinator CAN use `exec` for file operations (reading/writing investigation state files) and basic utilities. Do NOT use `exec` for API calls or enrichment — spawn the right specialist or use a Lobster pipeline.
