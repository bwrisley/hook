# Shadowbox

**by PUNCH Cyber**

Shadowbox is a multi-agent SOC operations platform. Seven specialist AI
agents — each with a distinct personality and operational role —
collaborate to triage alerts, enrich IOCs, respond to incidents, produce
intelligence assessments, and write reports. The whole system runs as a
single FastAPI process; the in-process agent runner calls OpenAI
directly. The web interface is the primary surface today, with Slack
planned as a secondary interface.

The backend system is called HOOK (Hunting, Orchestration & Operational
Knowledge).

## Architecture

```
                   Browser (http://localhost:7799)
                          |
                   FastAPI + SSE  (web/api/server.py)
                          |
                   Agent Runner   (web/api/agent_runner.py)
                          |
           +---------- Marshall ----------+
           |        (coordinator)         |
           |                              |
     +-----+-----+              +--------+--------+
     |           |              |        |        |
   Tara       Hunter         Ward     Driver    Page
  (triage)   (enrichment)    (IR)    (intel)   (reports)
                                                  |
                                                Wells
                                              (log query)
```

The agent runner streams over Server-Sent Events, handles tool calls
(`exec`) inline against the local filesystem, and persists conversation
state to SQLite (`data/hook-web.db`).

## The Team

| Callsign | Agent ID | Model | Role |
|----------|----------|-------|------|
| **Marshall** | coordinator | gpt-4.1 | Action officer. Routes requests, chains workflows, briefs back. Calm, dry, decisive. |
| **Tara** | triage-analyst | gpt-4.1 | Alert triage. TP/FP/Suspicious/Escalate verdicts with ATT&CK mapping. Clinical, precise. |
| **Hunter** | osint-researcher | gpt-4.1 | IOC enrichment across 8 sources. Follows infrastructure threads past where most stop. |
| **Ward** | incident-responder | gpt-4.1 | NIST 800-61 IR guidance. Contain first, understand later. Framework-driven. |
| **Driver** | threat-intel | gpt-5 | Structured analysis (ACH, Key Assumptions). Opinionated, comfortable making assumptions. |
| **Page** | report-writer | gpt-5 | Intelligence writer. Audience-calibrated reports with timelines, impact, detection gaps. |
| **Wells** | log-querier | gpt-4.1 | Translates natural language to OpenSearch DSL. Returns what the data shows. |

## Enrichment Sources

Hunter queries 8 sources for IP enrichment, 6 for domains, and 3 for hashes:

| Source | IP | Domain | Hash | Key Required |
|--------|:--:|:------:|:----:|:------------:|
| VirusTotal | x | x | x | VT_API_KEY |
| AbuseIPDB | x | | | ABUSEIPDB_API_KEY |
| Censys | x | | | CENSYS_API_ID/SECRET |
| AlienVault OTX | x | x | x | OTX_API_KEY |
| Shodan | x | | | SHODAN_API_KEY |
| URLhaus | x | x | | None |
| ThreatFox | x | x | x | None |
| DNS/WHOIS | x | x | | None |

Single-source queries are supported:
```bash
enrich-ip.sh --source shodan 1.2.3.4
enrich-ip.sh --source otx,urlhaus 1.2.3.4
enrich-domain.sh --source threatfox evil.com
```

## Quick Start

```bash
git clone git@github.com:bwrisley/hook.git
cd hook
./install/setup.sh
open http://localhost:7799
# Default login: admin / shadowbox  (change immediately)
```

`setup.sh` is idempotent — it builds the Python venv, builds the
frontend, prompts for any missing API keys, starts Ollama, pulls
embedding models, and optionally installs a macOS LaunchAgent so the
web UI auto-starts at login. See `install/INSTALL.md` for the long
form, manual setup, and troubleshooting.

## Shadowbox Web UI

The web interface provides:

- **Investigate** — Chat with the agent team. Submit alerts, IOCs, or questions. Marshall routes to the right specialist. Direct agent routing dropdown available.
- **Agents** — Live status of all 7 agents with message counts, token usage, and cost tracking.
- **History** — Investigation lifecycle management. View findings, timelines, IOCs. Change status, add notes, link to conversations.
- **Feeds** — Threat feed status and IOC watchlist. Watch IOCs for risk changes with automatic re-enrichment every 4 hours.
- **Settings** — Health dashboard with service status for the agent provider, Ollama, RAG, API keys, feeds, and database.
- **Audit** — Full audit log of agent calls with user, model, tokens, duration, and cost (admin only).
- **Users** — User management with role-based access: admin and analyst (admin only).

Features:
- Real-time chain progress bar with elapsed timers per agent
- Smart fast-routing (simple enrichments skip Marshall)
- Multi-turn conversation continuity
- Per-user conversation isolation with read-only and collaborate sharing
- Notification bell with watchlist alerts and auto-created investigations
- Orange/black SOC theme

## RAG Behavioral Memory

Agents have access to behavioral memory powered by Ollama (nomic-embed-text) embeddings:

- **IOC verdicts** — Past enrichment results recalled before re-enriching
- **Threat feed IOCs** — Auto-ingested from Feodo, URLhaus, ThreatFox feeds
- **TTPs** — Historical technique observations for attribution analysis
- **Findings** — Cross-investigation recall of past findings

Feed-to-RAG pipeline runs automatically: `fetch-feeds.sh` pulls IOCs,
`feed-to-rag.py` stores them with semantic embeddings, and the agent
runner injects feed matches into specialist context.

## Automation

macOS LaunchAgents (auto-start on login):

| Service | Schedule | Purpose |
|---------|----------|---------|
| Shadowbox Web | Always (KeepAlive) | Web UI + agent runner on port 7799 |
| Daily Check | 6:00 AM | Fetch feeds, enrich new IOCs, check watchlist |
| Watch Check | Every 4 hours | Re-enrich watched IOCs, detect risk changes |

```bash
./scripts/restart.sh status   # Show all service status
./scripts/restart.sh web      # Restart web service
./scripts/restart.sh stop     # Stop web service
```

## Requirements

- macOS with Apple Silicon (tested on M4 Max)
- Python 3.13+, Node.js 22+
- [Ollama](https://ollama.ai) with nomic-embed-text (qwen2.5:14b optional)
- OpenAI API key (gpt-4.1 + gpt-5)
- Enrichment API keys: VirusTotal, Censys, AbuseIPDB, AlienVault OTX, Shodan (all free tier)

## Repository Structure

```
hook/
+-- README.md
+-- requirements.txt
+-- .env                        # API keys (gitignored)
+-- core/
|   +-- db/                    # Database connectors (OpenSearch)
|   +-- rag/                   # RAG engine, behavioral memory, baseliner
|   +-- llm/                   # Ollama provider
+-- web/
|   +-- api/
|   |   +-- server.py          # FastAPI app
|   |   +-- agent_runner.py    # In-process OpenAI agent runner
|   |   +-- auth.py            # User auth + sessions
|   |   +-- watchlist.py       # IOC watchlist + notifications
|   |   +-- sse.py             # SSE event formatting
|   +-- src/                   # React + Vite + Tailwind frontend
+-- workspaces/                # Agent workspaces
|   +-- coordinator/           # Marshall
|   +-- triage-analyst/        # Tara
|   +-- osint-researcher/      # Hunter
|   +-- incident-responder/    # Ward
|   +-- threat-intel/          # Driver
|   +-- report-writer/         # Page
|   +-- log-querier/           # Wells
+-- scripts/
|   +-- lib/common.py          # Shared validation, rate limiting, caching
|   +-- enrich-ip.sh           # 8-source IP enrichment
|   +-- enrich-domain.sh       # 6-source domain enrichment
|   +-- enrich-hash.sh         # 3-source hash enrichment
|   +-- rag-inject.py          # RAG CLI (store/recall)
|   +-- feed-to-rag.py         # Feed IOC ingestion
|   +-- watch-check.py         # Watchlist re-enrichment
|   +-- fetch-feeds.sh         # Threat feed downloader
|   +-- restart.sh             # Service management
|   +-- test-agent.sh          # Agent testing helper
|   +-- backup-agents.sh       # SOUL.md/TOOLS.md backup
+-- data/                       # Runtime data (gitignored)
+-- config/                     # LaunchAgent plists
+-- deploy/                     # Azure provisioning
+-- tests/                      # Mocks, unit tests, scenarios
+-- install/                    # Installation guide + setup script
+-- docs/                       # BUILD-GUIDE, DEPLOY-AZURE, research
```

## Phase History

| Phase | Milestone |
|-------|-----------|
| 1 | CLINCH — Prototype, proved the concept |
| 2 | HOOK — Production rebuild, 6 agents, Slack integration, enrichment APIs |
| 3 | Coordinator routing overhaul, native tools, session memory, Lobster pipelines |
| 4 | Production hardening: input validation, rate limiting, structured logging, cron |
| 5 | Config stabilization, validation tooling, Frozen Ledger test suite |
| 6 | Shadowbox web UI, RAG memory, 7th agent, Ollama, multi-user auth, 8-source enrichment, watchlist monitoring, notification system, audit log, investigation lifecycle |
| 7 | OpenClaw eliminated. Single FastAPI process with in-process agent runner calling OpenAI directly. Build/deploy collapsed to one container; Azure target switches from 3 container apps to 2 (web + optional Ollama). |

## License

Proprietary -- PUNCH Cyber. All rights reserved.
