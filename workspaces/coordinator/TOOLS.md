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

## Investigation Management (exec tool)

Use the `exec` tool to run investigation management commands. These are REAL commands you must ACTUALLY EXECUTE using the exec tool — not just describe or reference.

### Create an Investigation
Use the exec tool to run:
```
/Users/bww/projects/hook/scripts/investigation.sh create "Title describing the incident"
```
Returns JSON with the investigation ID. Save this ID for all subsequent commands.

### Register IOCs
Use the exec tool to run:
```
/Users/bww/projects/hook/scripts/investigation.sh add-ioc <INV-ID> <type> <value> "<context>"
```
Types: ip, domain, hash, url, email. Context is a brief description like "C2 callback" or "stager download".

### Record Findings (MANDATORY after every subagent announce)
Use the exec tool to run:
```
/Users/bww/projects/hook/scripts/investigation.sh add-finding <INV-ID> <agent-name> "<one-line summary>"
```
You MUST run this after every subagent announces back. This is how findings get persisted.

### Get Investigation Context (MANDATORY before every chain spawn)
Use the exec tool to run:
```
/Users/bww/projects/hook/scripts/investigation.sh context <INV-ID>
```
Returns formatted markdown with all IOCs, findings, and timeline. Include this output in the `task` field when spawning the next agent in a chain.

### Other Commands
Use the exec tool to run any of these:
```
/Users/bww/projects/hook/scripts/investigation.sh status <INV-ID>          # Detailed status
/Users/bww/projects/hook/scripts/investigation.sh set-status <INV-ID> <s>  # Update status
/Users/bww/projects/hook/scripts/investigation.sh active                    # Current active investigation
/Users/bww/projects/hook/scripts/investigation.sh list                      # List all investigations
/Users/bww/projects/hook/scripts/investigation.sh close <INV-ID> <disp>     # Close investigation
```
Statuses: active, contained, eradication, recovery, monitoring, closed
Dispositions: resolved, false-positive, escalated, inconclusive

### Example: Full Chain with Investigation

Step 0 — Use exec to create investigation and register IOCs:
```
exec: /Users/bww/projects/hook/scripts/investigation.sh create "Multi-stage attack on WKSTN-FIN-042"
exec: /Users/bww/projects/hook/scripts/investigation.sh add-ioc INV-20260302-001 ip 45.77.65.211 "C2 callback"
exec: /Users/bww/projects/hook/scripts/investigation.sh add-ioc INV-20260302-001 domain update-check.finance-portal.com "stager"
```
Then spawn triage-analyst.

Step 1 — When triage announces back, use exec to record finding and get context, then spawn next:
```
exec: /Users/bww/projects/hook/scripts/investigation.sh add-finding INV-20260302-001 triage-analyst "TP high confidence. T1071, T1078, T1021."
exec: /Users/bww/projects/hook/scripts/investigation.sh context INV-20260302-001
```
Include the context output in the osint-researcher spawn task.

Step 2 — When OSINT announces back, same pattern:
```
exec: /Users/bww/projects/hook/scripts/investigation.sh add-finding INV-20260302-001 osint-researcher "3 IOCs enriched, IP low-risk Vultr."
exec: /Users/bww/projects/hook/scripts/investigation.sh context INV-20260302-001
```
Include context in the incident-responder spawn task.

Repeat for every step. Every announce → exec add-finding → exec context → spawn next.

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

The coordinator CAN and SHOULD use `exec` for:
- Running investigation management scripts (`/Users/bww/projects/hook/scripts/investigation.sh`)
- Reading investigation context for chain handoff
- Basic file operations

The coordinator does NOT use `exec` for:
- API calls or enrichment queries (spawn osint-researcher instead)
- Report generation (spawn report-writer instead)
- Any analysis work (spawn the right specialist)

Environment variables available:
- `$HOOK_DIR` — Path to the HOOK repository root
- `$VT_API_KEY`, `$CENSYS_API_ID`, `$CENSYS_API_SECRET`, `$ABUSEIPDB_API_KEY` — For specialist agents only

---

## Behavioral Memory (RAG)

After a multi-agent chain completes, store the investigation summary for future recall:

```bash
exec: python3 /Users/bww/projects/hook/scripts/rag-inject.py store-finding --inv INV-20260302-001 --agent coordinator --summary "Multi-stage attack: phishing to C2, contained within 2 hours"
```

To check for related past investigations before starting a new chain:

```bash
exec: python3 /Users/bww/projects/hook/scripts/rag-inject.py query "Cobalt Strike beacon" --category investigation_finding --k 3
```

### Log Querier Agent

When an investigation needs raw log evidence and `HOOK_OPENSEARCH_HOST` is configured, delegate to the log-querier agent:

```
sessions_spawn(
  task: "Query logs for outbound connections to 45.77.65.211 in the last 24 hours",
  agentId: "log-querier",
  runTimeoutSeconds: 120
)
```

The log-querier translates natural language questions into OpenSearch DSL queries.
