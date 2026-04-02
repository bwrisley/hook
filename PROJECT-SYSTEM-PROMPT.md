HOOK — Hunting, Orchestration & Operational Knowledge
by PUNCH Cyber

Continue building HOOK, a multi-agent SOC assistant on OpenClaw. Repo: https://github.com/bwrisley/hook | Local: ~/PROJECTS/hook

## Current State (Phase 5 Complete)

6 agents operational on OpenClaw via native npm on Mac Studio (no Docker sandbox). Integrated with Slack (#hook channel) using Socket Mode. All agents route correctly via coordinator. All 6 Frozen Ledger smoke tests passing.

**Agents:** coordinator (gpt-4.1), triage-analyst (gpt-4.1), osint-researcher (gpt-4.1), incident-responder (gpt-5), threat-intel (gpt-5), report-writer (gpt-4.1)

**What works:**
- Coordinator routes to correct specialist via sessions_spawn
- Multi-step chains: triage -> OSINT -> IR/report with context passing
- Enrichment APIs: VirusTotal, Censys, AbuseIPDB (all live, rate-limited)
- Native tools: jq, dig, whois, nmap installed via Homebrew
- Hardened scripts: input validation, rate limiting (file-based sliding window), structured JSONL logging, no shell injection
- Lobster pipelines: ioc-enrich-ip, ioc-enrich-domain, alert-to-report, batch-ioc-check
- Cron automation: fetch-feeds.sh (Feodo/URLhaus/ThreatFox), watchlist.sh, daily-check.sh, morning-briefing.sh
- macOS LaunchAgents for scheduling (6 AM daily check, 8 AM briefing)
- Health check: scripts/health-check.sh validates full environment
- Config validation: scripts/validate-config.sh checks structure, schema, drift against template
- Install docs: comprehensive install/INSTALL.md + install/setup.sh for junior devs
- Smoke test: Operation Frozen Ledger (tests/scenarios/operation-frozen-ledger.md) — all 6 tests passing
- Test runner: tests/run-frozen-ledger.sh (print / --post / --log modes)

**Phase History:**
- Phase 1 (CLINCH): Prototype
- Phase 2 (HOOK): Production rebuild, 6 agents, Slack integration, enrichment APIs
- Phase 3: Coordinator routing overhaul, native tools, session memory/context passing, Lobster pipelines
- Phase 4: Install docs, production hardening (validation/rate-limiting/logging), cron & automation
- Phase 5: Config stabilization, channel standardization (#hook), config validation tooling, Frozen Ledger test runner, all 6 tests passing

**Key Lessons:**
- OpenClaw JSON schema is extremely strict — rejects unknown keys. Known invalid: auth, compaction, description, tools.lobster, session.dmScope, gateway.bind, gateway.controlUi as boolean (must be object), channels.slack.streaming (replaced by nativeStreaming)
- Agents run exec commands on macOS host (no sandbox) — env vars from openclaw.json are available
- Agents sometimes use web_fetch instead of exec for API calls despite TOOLS.md instructions
- grep -c returns exit code 1 on zero matches — use || true, never || echo 0
- VT free tier: 4 req/min — rate limiting is essential for batch operations
- Live config accumulates extra keys from OpenClaw (webhookPath, userTokenReadOnly, groupPolicy, gateway.auth, wizard, commands) — these are safe, managed by the platform
- Config template uses HOOK_CHANNEL_NAME placeholder; setup.sh prompts for channel name
- Root INSTALL.md is a redirect to install/INSTALL.md (the canonical guide)

**Config:** ~/.openclaw/openclaw.json (exec timeout 180s, subagent timeout 300s)

**Repo Structure:**
```
hook/
+-- workspaces/{coordinator,triage-analyst,osint-researcher,incident-responder,threat-intel,report-writer}/
|   +-- SOUL.md (personality, routing rules)
|   +-- TOOLS.md (tool instructions, API templates)
+-- scripts/
|   +-- lib/{common.py, slack-notify.sh}
|   +-- enrich-{ip,domain,hash,batch}.sh, extract-iocs.sh, format-report.sh
|   +-- fetch-feeds.sh, watchlist.sh, daily-check.sh, morning-briefing.sh
|   +-- health-check.sh, validate-config.sh, fix-channel-refs.sh, schedule-install.sh
+-- pipelines/{ioc-enrich-ip,ioc-enrich-domain,alert-to-report,batch-ioc-check}.yaml
+-- config/{openclaw.json.template, *.plist, Dockerfile.hook, build.sh, USER.md.template}
+-- data/{feeds/, reports/, watchlist.txt}
+-- tests/{scenarios/operation-frozen-ledger.md, run-frozen-ledger.sh, results/, ioc-lists/}
+-- docs/{RESEARCH-INTER-AGENT-ROUTING.md, PIPELINES.md, PHASE5-CHECKLIST.md, skills/}
+-- install/{INSTALL.md, setup.sh}
```

## What's Next

Priority from earlier planning (remaining items):
1. **Real-world integration** — Connect to actual SIEM (Sentinel API), ingest live alerts, test with real IOCs
2. **Docker sandboxing** — Production deployment with container isolation
3. **Monitoring/alerting** — Detect and report agent failures automatically

Other candidates:
- Additional threat feeds or enrichment sources
- Custom skills for agents
- Agent tuning based on operational feedback
- Automated test result capture from Slack API or OpenClaw session logs

Please read the relevant files from the repo before making changes. Always package deliverables as tar.gz for me to apply with `tar xzf`. Use `chmod +x` on scripts. No emojis in operational output — executive/professional formatting only.
