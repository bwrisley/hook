# Shadowbox

**by PUNCH Cyber**

Shadowbox is a multi-agent SOC operations platform built on [OpenClaw](https://github.com/openclaw/openclaw). Seven specialist AI agents — each with a distinct personality and operational role — collaborate to triage alerts, enrich IOCs, respond to incidents, produce intelligence assessments, and write reports. The platform is operable through a web interface (Shadowbox) and will support Slack as a secondary interface.

The backend system is called HOOK (Hunting, Orchestration & Operational Knowledge).

## Architecture

```
                   Shadowbox Web UI (:7799)
                          |
                   FastAPI + SSE Bridge
                          |
                   OpenClaw Gateway (:18789)
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
# 1. Install dependencies
npm install -g openclaw
brew install jq bind nmap whois
pip3 install -r requirements.txt  # or use .venv

# 2. Install Ollama (local embeddings)
brew install ollama
brew services start ollama
ollama pull nomic-embed-text
ollama pull qwen2.5:14b

# 3. Configure
cp config/openclaw.json.template ~/.openclaw/openclaw.json
# Edit with your API keys, workspace paths, and gateway auth token

# 4. Set up .env
cp .env.example .env  # Add all API keys

# 5. Start services
openclaw gateway install && openclaw gateway start
./scripts/restart.sh all

# 6. Open Shadowbox
open http://localhost:7799
# Default login: admin / shadowbox
```

## Shadowbox Web UI

The web interface provides:

- **Investigate** — Chat with the agent team. Submit alerts, IOCs, or questions. Marshall routes to the right specialist. Direct agent routing dropdown available.
- **Agents** — Live status of all 7 agents with message counts, token usage, and cost tracking.
- **History** — Investigation lifecycle management. View findings, timelines, IOCs. Change status, add notes, link to conversations.
- **Feeds** — Threat feed status and IOC watchlist. Watch IOCs for risk changes with automatic re-enrichment every 4 hours.
- **Settings** — Health dashboard with service status for Gateway, Ollama, RAG, API keys, feeds, and database.
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

Feed-to-RAG pipeline runs automatically: `fetch-feeds.sh` pulls IOCs, `feed-to-rag.py` stores them with semantic embeddings, and the bridge auto-injects feed matches into specialist context.

## Automation

macOS LaunchAgents (auto-start on boot):

| Service | Schedule | Purpose |
|---------|----------|---------|
| Shadowbox Web | Always (KeepAlive) | Web UI on port 7799 |
| OpenClaw Gateway | Always (KeepAlive) | Agent runtime on port 18789 |
| Daily Check | 6:00 AM | Fetch feeds, enrich new IOCs, check watchlist |
| Watch Check | Every 4 hours | Re-enrich watched IOCs, detect risk changes |

```bash
./scripts/restart.sh status  # Show all service status
./scripts/restart.sh all     # Restart everything
./scripts/restart.sh web     # Restart web only
```

## Requirements

- macOS with Apple Silicon (tested on M4 Max)
- [OpenClaw](https://github.com/openclaw/openclaw) via npm
- [Ollama](https://ollama.ai) with nomic-embed-text + qwen2.5:14b
- Node.js 22+, Python 3.14+
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
|   |   +-- gateway_bridge.py  # OpenClaw CLI bridge with chain detection
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
+-- data/                      # Runtime data (gitignored)
+-- config/                    # Config templates + LaunchAgent plists
+-- tests/                     # Mocks, unit tests, scenarios
+-- install/                   # Installation guide + setup script
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

## License

Proprietary -- PUNCH Cyber. All rights reserved.
