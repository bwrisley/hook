# HOOK Installation Guide

**HOOK — Hunting, Orchestration & Operational Knowledge**
by PUNCH Cyber

This guide walks through a complete fresh install of HOOK on macOS (Mac Studio). Every command is documented. If a step fails, check the Troubleshooting section at the bottom.

---

## Prerequisites

- macOS with Docker Desktop installed
- Git installed (via Homebrew: `brew install git`)
- GitHub account with SSH key configured
- OpenAI API key (GPT-4.1 + GPT-5 access)
- VirusTotal API key (free tier works)
- Censys API credentials (free tier works)
- Slack workspace with admin access to create apps

---

## Step 1: Clean Previous Install

```bash
# Remove old workspace and skills (if upgrading from CLINCH/Phase 1)
rm -rf /Users/$USER/.openclaw/workspace/*
rm -rf /Users/$USER/.openclaw/skills/*

# Verify clean
ls -la /Users/$USER/.openclaw/workspace/
ls -la /Users/$USER/.openclaw/skills/
# Both should be empty or not exist
```

---

## Step 2: Clone HOOK Repository

```bash
cd ~
git clone git@github.com:bwrisley/hook.git
cd hook

# Verify structure
ls -la workspaces/
# Should show: coordinator/ triage-analyst/ osint-researcher/ incident-responder/ threat-intel/ report-writer/
```

---

## Step 3: Install OpenClaw (if not already installed)

```bash
# Install via npm (Node.js 18+ required)
npm install -g @openclaw/openclaw

# Or via Homebrew
brew install openclaw

# Verify installation
openclaw --version

# Run onboarding wizard (sets up initial config)
openclaw onboard
```

---

## Step 4: Configure openclaw.json

```bash
# Backup existing config if present
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.backup 2>/dev/null

# Copy HOOK template
cp ~/hook/config/openclaw.json.template ~/.openclaw/openclaw.json

# Edit config — replace placeholders
# Use your preferred editor: nano, vim, or code
nano ~/.openclaw/openclaw.json
```

### Required Edits:

1. **Replace `HOOK_REPO_PATH`** with the absolute path to your HOOK repo:
   ```
   # Find and replace all instances of HOOK_REPO_PATH with:
   /Users/bww/hook
   ```

2. **Replace API keys:**
   ```
   YOUR_VIRUSTOTAL_API_KEY → your actual VT key
   YOUR_CENSYS_API_ID → your actual Censys API ID
   YOUR_CENSYS_API_SECRET → your actual Censys secret
   YOUR_ABUSEIPDB_API_KEY → your actual AbuseIPDB key
   ```

3. **Replace Slack tokens** (see Step 5):
   ```
   xoxb-YOUR-BOT-TOKEN → your bot token
   xapp-YOUR-APP-TOKEN → your app token
   ```

### Quick sed replacement:
```bash
# Replace HOOK_REPO_PATH (adjust path as needed)
sed -i '' 's|HOOK_REPO_PATH|/Users/bww/hook|g' ~/.openclaw/openclaw.json

# Verify
grep -c "HOOK_REPO_PATH" ~/.openclaw/openclaw.json
# Should return 0 (all replaced)
```

---

## Step 5: Configure Slack App

### 5a: Create Slack App
1. Go to https://api.slack.com/apps
2. Click **Create New App** → **From scratch**
3. Name: `HOOK` | Workspace: your workspace
4. Click **Create App**

### 5b: Enable Socket Mode
1. Left sidebar → **Socket Mode**
2. Toggle **Enable Socket Mode** → ON
3. Generate an app-level token:
   - Token Name: `hook-socket`
   - Scope: `connections:write`
   - Click **Generate**
   - Copy the `xapp-...` token → paste into openclaw.json as `appToken`

### 5c: Add Bot Token Scopes
1. Left sidebar → **OAuth & Permissions**
2. Scroll to **Scopes** → **Bot Token Scopes** → Add:
   - `app_mentions:read`
   - `chat:write`
   - `channels:history`
   - `channels:read`
   - `groups:history`
   - `groups:read`
   - `im:history`
   - `im:read`
   - `im:write`
   - `users:read`

### 5d: Install App to Workspace
1. Scroll up → **Install to Workspace** → **Allow**
2. Copy the **Bot User OAuth Token** (`xoxb-...`) → paste into openclaw.json as `botToken`

### 5e: Enable Event Subscriptions
1. Left sidebar → **Event Subscriptions**
2. Toggle **Enable Events** → ON
3. Subscribe to bot events:
   - `app_mention`
   - `message.channels`
   - `message.groups`
   - `message.im`
4. Click **Save Changes**

### 5f: Create Test Channel
1. In Slack, create private channel: `#hook-test`
2. Invite the HOOK bot to the channel: `/invite @HOOK`

---

## Step 6: Copy USER.md (Optional)

```bash
# Copy the template and customize for your environment
cp ~/hook/config/USER.md.template ~/hook/workspaces/coordinator/USER.md
nano ~/hook/workspaces/coordinator/USER.md
# Fill in your organization's security stack details
```

---

## Step 7: Start OpenClaw Gateway

```bash
# Start the gateway
openclaw gateway start

# Or restart if already running
openclaw gateway restart

# Check status
openclaw gateway status

# Verify agents are loaded
openclaw agents list --bindings
```

### Expected output from `agents list`:
```
Agents:
  coordinator (default) → workspace: /Users/bww/hook/workspaces/coordinator
  triage-analyst → workspace: /Users/bww/hook/workspaces/triage-analyst
  osint-researcher → workspace: /Users/bww/hook/workspaces/osint-researcher
  incident-responder → workspace: /Users/bww/hook/workspaces/incident-responder
  threat-intel → workspace: /Users/bww/hook/workspaces/threat-intel
  report-writer → workspace: /Users/bww/hook/workspaces/report-writer

Bindings:
  slack → coordinator
```

---

## Step 8: Verify Slack Connection

```bash
# Check channel status
openclaw channels status --probe
```

In Slack `#hook-test`, send:
```
@HOOK Hello, are you online?
```

The coordinator should respond. If not, check the Troubleshooting section.

---

## Step 9: Test Single-Agent Enrichment

In `#hook-test`:
```
@HOOK Enrich this IP: 8.8.8.8
```

Expected: Coordinator runs a quick VT check directly (simple query, no specialist needed) and returns results showing Google's DNS server.

Then test specialist routing:
```
@HOOK Run a full enrichment on 45.77.65.211 using the OSINT researcher
```

Expected: Coordinator spawns osint-researcher subagent, which runs VT + Censys + AbuseIPDB checks and announces results.

---

## Step 10: Test Inter-Agent Routing

```
@HOOK Triage this alert and then enrich any IOCs you find:

AlertName: Suspicious Outbound Connection
Host: WKSTN-042 (10.20.30.42)
Process: rundll32.exe
Destination: 185.220.101.34:443
User: jdoe
```

Expected: Coordinator spawns triage-analyst → receives verdict with IOCs → spawns osint-researcher for enrichment.

---

## Step 11: Run Full Smoke Test

Use the Operation Frozen Ledger scenario from `tests/scenarios/operation-frozen-ledger.md`.

Run Test 6 (Full Chain) to validate the complete routing pipeline.

---

## Step 12: Push to GitHub

```bash
cd ~/hook
git add .
git commit -m "Initial HOOK setup - Phase 2 complete"
git remote add origin git@github.com:bwrisley/hook.git
git push -u origin main
```

---

## Troubleshooting

### Slack not responding
```bash
# Check gateway logs
openclaw gateway logs --tail 50

# Verify tokens are correct
openclaw channels status --probe

# Ensure bot is invited to #hook-test
```

### API calls failing
```bash
# Test VT key directly
curl -s "https://www.virustotal.com/api/v3/ip_addresses/8.8.8.8" \
  -H "x-apikey: YOUR_KEY" | python3 -m json.tool | head -5

# Test Censys key directly
curl -s -u "YOUR_ID:YOUR_SECRET" \
  "https://search.censys.io/api/v2/hosts/8.8.8.8" | python3 -m json.tool | head -5
```

### Agent routing not working
```bash
# Verify agent list
openclaw agents list --bindings

# Check if subagents are allowed
# Look for "allowAgents" in config under coordinator
grep -A5 "allowAgents" ~/.openclaw/openclaw.json
```

### Config validation errors
```bash
# Run config doctor
openclaw doctor

# Check for schema issues
openclaw config validate
```

### Common Pitfalls (from Phase 1)
- **Don't add `description` to agent entries** — not in schema
- **Don't add `allowedCommands`/`blockedCommands`** — not in schema
- **Don't put `bindings` under `agents`** — it's top-level
- **Don't use `web_fetch` for API calls** — use `exec` + `curl`
- **Don't assume `jq` exists** — use `python3` for JSON
- **Don't assume `dig`/`whois` exist** — use `python3` socket module

---

## Next Steps

After validation:
1. Customize `USER.md` for your environment
2. Build custom Docker image: `docker build -f config/Dockerfile.hook -t hook-openclaw:latest .`
3. Add more test scenarios to `tests/`
4. Consider Lobster workflows for automated IR playbooks (Phase 3)
