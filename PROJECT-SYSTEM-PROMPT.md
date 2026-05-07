HOOK / Shadowbox — Hunting, Orchestration & Operational Knowledge
by PUNCH Cyber

Continue building HOOK / Shadowbox, a multi-agent SOC assistant. Repo: https://github.com/bwrisley/hook | Local: ~/projects/hook

## Current State (Phase 7 Complete — OpenClaw eliminated)

Single FastAPI process on port 7799 with an in-process agent runner that
calls OpenAI directly. 7 agents operational. Web UI is the primary
interface; Slack is reserved but not yet wired up. Mac Studio (M4 Max)
is the dev environment via the `com.punchcyber.hook.web` LaunchAgent.

**Agents:** coordinator/Marshall (gpt-4.1), triage-analyst/Tara (gpt-4.1),
osint-researcher/Hunter (gpt-4.1), incident-responder/Ward (gpt-4.1),
threat-intel/Driver (gpt-5), report-writer/Page (gpt-5),
log-querier/Wells (gpt-4.1).

**What works:**
- Marshall routes to specialists by callsign; chain detection recognizes
  "Routing to Driver", "ask Hunter", etc.
- Multi-step chains: triage -> OSINT -> IR/report with context passing
- Fast-route patterns skip Marshall for simple `enrich <ioc>` and
  `ask <callsign>` requests
- 8-source IP enrichment (VT, AbuseIPDB, Censys, OTX, Shodan, URLhaus,
  ThreatFox, DNS), 6-source domain, 3-source hash; per-source `--source`
  flag for debugging
- Hardened scripts: input validation, file-based sliding-window rate
  limiting, structured JSONL logging, no shell injection
- Cron automation: hook-daily (6 AM feed fetch), watch-check (every 4h
  re-enrichment of watchlist IOCs)
- Local Ollama (brew service) for nomic-embed-text RAG embeddings and
  optional qwen2.5:14b chat
- Web UI: Investigate/Agents/History/Feeds/Settings/Audit/Users pages,
  multi-user auth, conversation sharing, notification bell with auto
  investigations, audit log with token + cost tracking
- Frozen Ledger smoke tests in `tests/scenarios/`

**What's not wired up (yet):**
- Slack — env vars are reserved (`SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`);
  no live integration

**Phase History:**
- Phase 1 (CLINCH): Prototype
- Phase 2 (HOOK): Production rebuild, 6 agents, Slack integration, enrichment APIs
- Phase 3: Coordinator routing overhaul, native tools, context passing, Lobster pipelines
- Phase 4: Install docs, production hardening, cron automation
- Phase 5: Config stabilization, channel standardization, Frozen Ledger test runner
- Phase 6: Shadowbox web UI, RAG memory, 7th agent (Wells), Ollama,
  multi-user auth, 8-source enrichment, watchlist monitoring, audit log,
  investigation lifecycle
- Phase 7: OpenClaw eliminated. Single FastAPI process with in-process
  agent runner. Build/deploy collapsed to one container. Azure target
  switches from 3 container apps to 2 (web + optional Ollama).

**Key Lessons:**
- Agents call OpenAI directly via the runner; tool calls (`exec`) run
  on the host filesystem with no sandbox. The `BLOCKED_PATTERNS` list
  in `agent_runner.py` is the only guardrail — keep it tight.
- Agents sometimes try to use `web_fetch` instead of `exec` for API
  calls despite TOOLS.md instructions. Stronger language in SOUL.md
  helps.
- `grep -c` returns exit code 1 on zero matches — use `|| true`, never
  `|| echo 0`.
- VT free tier is 4 req/min — rate limiting in `scripts/lib/common.py`
  is essential for batch operations.
- Root `INSTALL.md` is a one-line redirect to `install/INSTALL.md`
  (canonical guide).
- `restart.sh` covers only the web service now. The
  `ai.openclaw.gateway` plist still exists in `~/Library/LaunchAgents`
  on dev machines — leave it unloaded; do NOT bootstrap it.

**Config:** `.env` (gitignored). API keys for OpenAI, VT, Censys (ID +
Secret), AbuseIPDB, OTX, Shodan. Optional: `DATABASE_URL` for Postgres,
`OLLAMA_BASE_URL` to point at a remote Ollama.

**Repo Structure:**
```
hook/
+-- workspaces/{coordinator,triage-analyst,osint-researcher,incident-responder,threat-intel,report-writer,log-querier}/
|   +-- SOUL.md (personality, routing rules)
|   +-- TOOLS.md (tool instructions, API templates)
+-- web/
|   +-- api/{server.py, agent_runner.py, auth.py, watchlist.py, sse.py}
|   +-- src/                         # React + Vite + Tailwind frontend
+-- core/{db, rag, llm}/              # OpenSearch, RAG engine, Ollama provider
+-- scripts/
|   +-- lib/common.py
|   +-- enrich-{ip,domain,hash,batch}.sh, extract-iocs.sh, format-report.sh
|   +-- fetch-feeds.sh, watch-check.py, daily-check.sh, morning-briefing.sh
|   +-- restart.sh, test-agent.sh, backup-agents.sh
+-- config/{*.plist}                  # LaunchAgent templates
+-- deploy/azure-setup.sh             # Azure Container Apps provisioner
+-- data/{feeds, cache, faiss, investigations}/  # Runtime (gitignored)
+-- tests/{scenarios, mocks, results, ioc-lists, test_*.py, run-frozen-ledger.sh}
+-- docs/{BUILD-GUIDE, DEPLOY-AZURE, RESEARCH-INTER-AGENT-ROUTING, PIPELINES}.md
+-- install/{INSTALL.md, setup.sh}
+-- Dockerfile, docker-compose.yml, .github/workflows/deploy.yml
```

## What's Next

Priority:
1. **Azure deployment** — `azure_prompt.md` is the briefing for a Claude
   Code session running on the App Service container shell. Decision
   pending: separate Ollama Web App vs OpenAI embeddings.
2. **Real-world integration** — Connect to a live SIEM (Sentinel API),
   ingest live alerts, test with real IOCs.
3. **Monitoring/alerting** — Detect and report agent failures
   automatically.

Lower priority:
- Wire up Slack (Socket Mode, env vars are already reserved)
- Export investigation as markdown/PDF
- IOC quick-submit (batch enrich from pasted list)
- GreyNoise as 5th IP threat-intel source
- Custom skills per agent
- Agent tuning based on operational feedback

Please read the relevant files from the repo before making changes. No
emojis in operational output — executive/professional formatting only.
