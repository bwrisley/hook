# 🪝 HOOK — Hunting, Orchestration & Operational Knowledge

**by PUNCH Cyber**

HOOK is a multi-agent SOC assistant built on [OpenClaw](https://github.com/openclaw/openclaw). It provides AI-powered security operations through six specialist agents coordinated via Slack.

## Architecture

```
         Slack (#hook-test)
              │
              ▼
     ┌─── Coordinator ───┐
     │   (routes tasks)   │
     │                    │
     ▼        ▼           ▼
  Hunting  Orchestration  Operational
  Pillar     Pillar      Knowledge Pillar
     │         │              │
     ├─ Triage ├─ Coordinator ├─ Threat Intel
     │  Analyst│  (self)      │
     │         │              │
     └─ OSINT  └─ Incident   └─ Report
       Researcher Responder     Writer
```

## Agents

| Agent | Pillar | Purpose |
|-------|--------|---------|
| **coordinator** | — | Routes requests, chains workflows, handles simple queries |
| **triage-analyst** | Hunting | Alert triage: TP/FP/Suspicious/Escalate verdicts |
| **osint-researcher** | Hunting | IOC enrichment via VirusTotal, Censys, AbuseIPDB |
| **incident-responder** | Orchestration | NIST 800-61 IR guidance with platform-specific steps |
| **threat-intel** | Operational Knowledge | Structured analytic techniques (ACH, Key Assumptions) |
| **report-writer** | Operational Knowledge | Audience-adapted reports (analyst → board level) |

## Quick Start

1. Clone this repo
2. Copy `config/openclaw.json.template` to `~/.openclaw/openclaw.json`
3. Replace placeholders with your API keys and paths
4. Configure Slack app (see `install/INSTALL.md`)
5. Start OpenClaw: `openclaw gateway start`
6. Test in Slack: `@HOOK Hello`

Full installation guide: [install/INSTALL.md](install/INSTALL.md)

## Requirements

- [OpenClaw](https://github.com/openclaw/openclaw) installed
- OpenAI API key (GPT-4.1 + GPT-5)
- VirusTotal API key (free tier)
- Censys API credentials (free tier)
- AbuseIPDB API key (free tier)
- Slack workspace with app creation access

## Repository Structure

```
hook/
├── README.md
├── .gitignore
├── docs/
│   ├── RESEARCH-INTER-AGENT-ROUTING.md
│   └── skills/              # Reference docs (human-readable)
├── workspaces/              # Agent workspaces (SOUL.md + TOOLS.md)
│   ├── coordinator/
│   ├── triage-analyst/
│   ├── osint-researcher/
│   ├── incident-responder/
│   ├── threat-intel/
│   └── report-writer/
├── config/
│   ├── openclaw.json.template
│   ├── USER.md.template
│   └── Dockerfile.hook      # Custom image (future)
├── tests/
│   └── scenarios/
│       └── operation-frozen-ledger.md
└── install/
    ├── INSTALL.md
    └── setup.sh
```

## Inter-Agent Routing

HOOK uses OpenClaw's `sessions_spawn` for inter-agent communication. The coordinator agent receives all Slack messages and delegates to specialists:

```
User: "Enrich 45.77.65.211"
  → Coordinator: sessions_spawn(agentId: "osint-researcher", task: "Enrich IP 45.77.65.211...")
  → OSINT Researcher: runs VT + Censys + AbuseIPDB
  → Result announced back to Slack
```

See [docs/RESEARCH-INTER-AGENT-ROUTING.md](docs/RESEARCH-INTER-AGENT-ROUTING.md) for the full research on routing mechanisms.

## Test Scenarios

- **Operation Frozen Ledger** — Full attack chain: phishing → execution → C2 → credential dump → lateral movement → ransomware. Tests all six agents.

## Phase History

- **Phase 1 (CLINCH):** Prototype, proved the concept. [github.com/bwrisley/clinch](https://github.com/bwrisley/clinch)
- **Phase 2 (HOOK):** Production rebuild with inter-agent routing, clean architecture, and full documentation.

## License

Proprietary — PUNCH Cyber. All rights reserved.
