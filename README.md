# HOOK — Hunting, Orchestration & Operational Knowledge

**by PUNCH Cyber**

HOOK is a multi-agent SOC assistant built on [OpenClaw](https://github.com/openclaw/openclaw). It provides AI-powered security operations through six specialist agents coordinated via Slack.

## Architecture

```
         Slack (#hook)
              |
              v
     +--- Coordinator ---+
     |   (routes tasks)   |
     |                    |
     v        v           v
  Hunting  Orchestration  Operational
  Pillar     Pillar      Knowledge Pillar
     |         |              |
     +- Triage +- Coordinator +- Threat Intel
     |  Analyst|  (self)      |
     |         |              |
     +- OSINT  +- Incident   +- Report
       Researcher Responder     Writer
```

## Agents

| Agent | Pillar | Model | Purpose |
|-------|--------|-------|---------|
| **coordinator** | -- | gpt-4.1 | Routes requests, chains workflows, handles simple queries |
| **triage-analyst** | Hunting | gpt-4.1 | Alert triage: TP/FP/Suspicious/Escalate verdicts |
| **osint-researcher** | Hunting | gpt-4.1 | IOC enrichment via VirusTotal, Censys, AbuseIPDB |
| **incident-responder** | Orchestration | gpt-5 | NIST 800-61 IR guidance with platform-specific steps |
| **threat-intel** | Operational Knowledge | gpt-5 | Structured analytic techniques (ACH, Key Assumptions) |
| **report-writer** | Operational Knowledge | gpt-4.1 | Audience-adapted reports (analyst to board level) |
| **log-querier** | Data | gpt-4.1 | Natural language log queries via OpenSearch (Phase 6) |

## Quick Start

1. Clone this repo
2. Run `./install/setup.sh` (automated) or follow `install/INSTALL.md` (manual)
3. Configure Slack app (see Step 5 in `install/INSTALL.md`)
4. Start OpenClaw: `openclaw gateway install && openclaw gateway start`
5. Validate: `./scripts/health-check.sh && ./scripts/validate-config.sh`
6. Test in Slack: `@HOOK Hello`
7. Smoke test: `./tests/run-frozen-ledger.sh`

Full installation guide: [install/INSTALL.md](install/INSTALL.md)

## Requirements

- [OpenClaw](https://github.com/openclaw/openclaw) installed
- macOS with Homebrew (security tools: `brew install jq bind nmap whois`)
- OpenAI API key (GPT-4.1 + GPT-5)
- VirusTotal API key (free tier)
- Censys API credentials (free tier)
- AbuseIPDB API key (free tier)
- Slack workspace with app creation access

## Repository Structure

```
hook/
+-- README.md
+-- INSTALL.md                  # Redirect to install/INSTALL.md
+-- requirements.txt            # Python dependencies (Phase 6)
+-- .gitignore
+-- core/                       # Phase 6: Backend modules
|   +-- db/
|   |   +-- connector.py       # BaseDBConnector ABC + OpenSearchConnector
|   |   +-- querier.py         # NL -> OpenSearch DSL translator
|   +-- rag/
|       +-- engine.py          # RAG engine (OpenSearch k-NN + FAISS fallback)
|       +-- memory.py          # Behavioral memory (IOC verdicts, baselines, TTPs)
|       +-- baseliner.py       # 6-hourly baseline builder
+-- web/                        # Phase 6: Web UI
|   +-- api/
|   |   +-- server.py          # FastAPI app (port 7799)
|   |   +-- gateway_bridge.py  # OpenClaw gateway REST API bridge
|   |   +-- sse.py             # SSE event formatting
|   +-- src/                   # React + Vite frontend
|   |   +-- pages/             # InvestigatePage, AgentsPage, etc.
|   |   +-- components/        # Layout, AgentBadge, InvestigationTimeline
|   |   +-- lib/api.js         # SSE streaming + REST client
|   +-- package.json
|   +-- vite.config.js
|   +-- tailwind.config.js
+-- docs/
|   +-- RESEARCH-INTER-AGENT-ROUTING.md
|   +-- PIPELINES.md            # Lobster pipeline documentation
|   +-- PHASE5-CHECKLIST.md     # Config stabilization results
|   +-- skills/                 # Reference docs (human-readable)
+-- workspaces/                 # Agent workspaces (SOUL.md + TOOLS.md)
|   +-- coordinator/
|   +-- triage-analyst/
|   +-- osint-researcher/
|   +-- incident-responder/
|   +-- threat-intel/
|   +-- report-writer/
|   +-- log-querier/            # Phase 6: NL log query agent
+-- pipelines/                  # Lobster workflow definitions
|   +-- ioc-enrich-ip.yaml
|   +-- ioc-enrich-domain.yaml
|   +-- alert-to-report.yaml
|   +-- batch-ioc-check.yaml
+-- scripts/                    # Pipeline helper scripts (hardened)
|   +-- lib/
|   |   +-- common.py          # Shared validation, rate limiting, logging
|   |   +-- slack-notify.sh    # Post messages to Slack from scripts
|   +-- enrich-ip.sh
|   +-- enrich-domain.sh
|   +-- enrich-hash.sh
|   +-- extract-iocs.sh
|   +-- enrich-batch.sh
|   +-- format-report.sh
|   +-- health-check.sh        # Environment validation
|   +-- validate-config.sh     # Config structure/drift validation
|   +-- rag-inject.py          # Phase 6: RAG CLI for agents
|   +-- run-baseliner.py       # Phase 6: Baseliner entry point
|   +-- query-logs.py          # Phase 6: Log query entry point
|   +-- start-web.sh           # Phase 6: Web UI launcher
|   +-- fetch-feeds.sh         # Pull IOCs from threat feeds
|   +-- watchlist.sh           # Persistent IOC watchlist manager
|   +-- daily-check.sh         # Automated daily threat check (cron)
|   +-- morning-briefing.sh    # Morning Slack summary
|   +-- schedule-install.sh    # Install/uninstall macOS LaunchAgents
+-- data/                       # Dynamic data (gitignored)
|   +-- feeds/                 # Downloaded threat feed IOCs
|   +-- reports/               # Daily enrichment reports
|   +-- faiss/                 # Phase 6: FAISS vector index (gitignored)
|   +-- watchlist.txt          # Persistent IOC watchlist
+-- config/
|   +-- openclaw.json.template # Config template with placeholders
|   +-- USER.md.template
|   +-- Dockerfile.hook        # Custom image (future Docker sandboxing)
|   +-- build.sh               # Build script for custom image
|   +-- ai.openclaw.hook-daily.plist      # LaunchAgent: daily threat check
|   +-- ai.openclaw.hook-briefing.plist   # LaunchAgent: morning briefing
|   +-- com.punchcyber.hook.web.plist     # Phase 6: Web server LaunchAgent
|   +-- com.punchcyber.hook.baseliner.plist # Phase 6: Baseliner LaunchAgent
+-- tests/
|   +-- mocks/                  # Phase 6: Test infrastructure
|   |   +-- mock_db.py         # In-memory DB with cosine kNN
|   |   +-- mock_llm.py        # Deterministic LLM
|   |   +-- data_generator.py  # Synthetic test data
|   +-- test_mocks.py          # Phase 6: Mock tests
|   +-- test_rag.py            # Phase 6: RAG engine tests
|   +-- test_web_api.py        # Phase 6: Web API tests
|   +-- scenarios/
|   |   +-- operation-frozen-ledger.md  # Smoke test scenario
|   +-- run-frozen-ledger.sh            # Test runner (print/post/log)
|   +-- results/                        # Test results (gitignored)
|   +-- ioc-lists/                      # Test IOC data
+-- install/
    +-- INSTALL.md              # Comprehensive installation guide
    +-- setup.sh                # Automated setup script
```

## Inter-Agent Routing

HOOK uses OpenClaw's `sessions_spawn` for inter-agent communication. The coordinator agent receives all Slack messages and delegates to specialists:

```
User: "Enrich 45.77.65.211"
  -> Coordinator: sessions_spawn(agentId: "osint-researcher", task: "Enrich IP 45.77.65.211...")
  -> OSINT Researcher: runs VT + Censys + AbuseIPDB
  -> Result announced back to Slack
```

For multi-step investigations, the coordinator chains agents sequentially, passing accumulated findings between each step:

```
User: "Investigate this alert fully"
  -> Coordinator spawns triage-analyst
  -> Triage result announces back
  -> Coordinator spawns osint-researcher with triage findings
  -> OSINT result announces back
  -> Coordinator spawns report-writer with all findings
  -> Final report announces back to Slack
```

See [docs/RESEARCH-INTER-AGENT-ROUTING.md](docs/RESEARCH-INTER-AGENT-ROUTING.md) for the full research on routing mechanisms.

## Test Scenarios

**Operation Frozen Ledger** — Full attack chain: phishing, execution, C2, credential dump, lateral movement, ransomware. Tests all six agents individually and as a chained workflow.

```bash
# Print test prompts for manual Slack testing
./tests/run-frozen-ledger.sh

# Post prompts directly to Slack (interactive, waits between tests)
./tests/run-frozen-ledger.sh --post

# Generate results capture template
./tests/run-frozen-ledger.sh --log
```

See [tests/scenarios/operation-frozen-ledger.md](tests/scenarios/operation-frozen-ledger.md) for full scenario details and expected behaviors.

## Validation

```bash
# Environment: dependencies, tools, API connectivity, workspaces
./scripts/health-check.sh

# Config: structure, placeholders, agents, bindings, schema pitfalls
./scripts/validate-config.sh
```

## Automation

HOOK includes cron-driven automation via macOS LaunchAgents:

- **Daily threat check** (6 AM): fetches threat feeds, checks watchlist IOCs, posts results to Slack
- **Morning briefing** (8 AM): summarizes overnight feed activity and watchlist hits

Install with: `./scripts/schedule-install.sh --install`

## Web UI (Phase 6)

HOOK includes a web interface alongside the Slack interface. Both operate simultaneously.

```bash
# Development mode (API + Vite dev server)
./scripts/start-web.sh

# Production (build frontend, then serve)
./scripts/start-web.sh --build
./scripts/start-web.sh --api
```

- **API**: FastAPI on port 7799 (bridges to OpenClaw gateway)
- **Frontend**: React + Vite on port 5173 (dev) or bundled to `web/dist/`
- **Views**: Investigate (chat), Agents (status), Investigations (history), Feeds, Settings

## RAG Behavioral Memory (Phase 6)

Agents have access to behavioral memory via RAG:
- **IOC verdicts**: Past enrichment results recalled before re-enriching
- **Baselines**: Network behavioral baselines for triage context
- **TTPs**: Historical technique observations for ACH analysis
- **Findings**: Cross-investigation recall of past findings

Agents interact via `exec: python3 $HOOK_DIR/scripts/rag-inject.py`. Baseliner runs every 6 hours via LaunchAgent.

## Phase History

| Phase | Name | Milestone |
|-------|------|-----------|
| 1 | CLINCH | Prototype, proved the concept |
| 2 | HOOK | Production rebuild, 6 agents, Slack integration, enrichment APIs |
| 3 | HOOK | Coordinator routing overhaul, native tools, session memory, Lobster pipelines |
| 4 | HOOK | Production hardening: input validation, rate limiting, structured logging, cron automation, install docs |
| 5 | HOOK | Config stabilization, channel standardization, config validation tooling, Frozen Ledger test runner, all 6 tests passing |
| 6 | HOOK | Web UI (FastAPI + React), RAG behavioral memory, log-querier agent, direct OpenSearch connectivity, test mocks |

## License

Proprietary -- PUNCH Cyber. All rights reserved.
