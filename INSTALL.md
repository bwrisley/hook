# HOOK Installation Guide

**HOOK** (Hunting, Orchestration & Operational Knowledge) by PUNCH Cyber
Multi-agent SOC assistant built on OpenClaw

**Last Updated:** 2026-03-01 (Phase 2 — verified working on macOS)

---

## Prerequisites

- macOS (tested on Mac Studio, Apple Silicon)
- Node.js 22+ (`brew install node@22`)
- OpenClaw 2026.2.26+ (`npm install -g openclaw`)
- OpenAI API key (GPT-4.1 and GPT-5 models)
- Slack workspace with admin access
- API keys for: VirusTotal, Censys, AbuseIPDB

---

## Step 1: Clone the Repository

```bash
cd ~/PROJECTS
git clone https://github.com/bwrisley/hook.git
cd hook
```

---

## Step 2: Configure OpenAI

```bash
openclaw configure
```

Select OpenAI as provider and enter your API key when prompted. This creates the auth profile that the gateway needs.

---

## Step 3: Fix macOS /home/node Restriction

OpenClaw's exec sandbox expects `/home/node` to exist. macOS blocks `/home` via automountd. This must be fixed before the gateway will run.

```bash
sudo vi /etc/auto_master
```

Find this line:

```
/home                     auto_home       -nobrowse,hidefromfinder
```

Comment it out:

```
#/home                     auto_home       -nobrowse,hidefromfinder
```

Save and exit, then run:

```bash
sudo automount -vc
sudo mkdir -p /home/node
sudo chown $(whoami) /home/node
```

Verify it exists:

```bash
ls -la /home/node
```

---

## Step 4: Create the Configuration

Copy the template and edit it:

```bash
cp ~/PROJECTS/hook/config/openclaw.json.template ~/.openclaw/openclaw.json
vi ~/.openclaw/openclaw.json
```

### Required edits:

**4a. API Keys** — Replace placeholders in the `env` section:

```json
"env": {
  "shellEnv": { "enabled": true },
  "VT_API_KEY": "YOUR_VIRUSTOTAL_KEY",
  "CENSYS_API_ID": "YOUR_CENSYS_ID",
  "CENSYS_API_SECRET": "YOUR_CENSYS_SECRET",
  "ABUSEIPDB_API_KEY": "YOUR_ABUSEIPDB_KEY"
}
```

**4b. Workspace Paths** — Update all workspace paths to match your system. Replace `/Users/bww` with your home directory:

```json
"workspace": "/Users/YOURUSERNAME/PROJECTS/hook/workspaces/coordinator"
```

Do this for all 6 agents: coordinator, triage-analyst, osint-researcher, incident-responder, threat-intel, report-writer.

**4c. Slack Tokens** — Leave as placeholders for now (Step 5 covers Slack setup):

```json
"botToken": "xoxb-YOUR-BOT-TOKEN",
"appToken": "xapp-YOUR-APP-TOKEN"
```

**4d. Slack Channel** — Set the channel name to match your Slack channel:

```json
"channels": {
  "#hook": { "allow": true }
}
```

### Critical config rules (learned the hard way):

- **No `auth` block** — OpenClaw manages auth via `openclaw configure`, not the config file
- **No `compaction` field** — Unrecognized by schema, causes crash on startup
- **No `streaming: true`** at top level — Use `"nativeStreaming": false` under slack channel only
- **No `gateway.controlUi`** — Invalid in current schema
- **No `gateway.bind`** — Invalid field, gateway defaults to loopback
- **No `description` field on agents** — Not in schema
- **No `allowedCommands`/`blockedCommands`** — Not in schema
- **`bindings` is top-level** — NOT under `agents`
- **Validate JSON after every edit:**

```bash
python3 -c "import json; json.load(open('$HOME/.openclaw/openclaw.json')); print('Valid JSON')"
```

---

## Step 5: Create the Slack App

### 5a. Create the app

1. Go to https://api.slack.com/apps
2. Click **Create New App** → **From scratch**
3. Name it `HOOK`, select your workspace
4. Click **Create App**

### 5b. Enable Socket Mode

1. Left sidebar → **Socket Mode**
2. Toggle **Enable Socket Mode** to ON
3. Create an app-level token with `connections:write` scope
4. Name it `hook-socket` → **Generate**
5. Copy the `xapp-...` token — this is your `appToken`

### 5c. Set Bot Token Scopes

1. Left sidebar → **OAuth & Permissions**
2. Under **Bot Token Scopes**, add:
   - `app_mentions:read`
   - `channels:history`
   - `channels:read`
   - `chat:write`
   - `groups:history`
   - `groups:read`
   - `im:history`
   - `im:read`
   - `reactions:write`
   - `files:read`
   - `files:write`
   - `users:read`

### 5d. Enable Event Subscriptions

1. Left sidebar → **Event Subscriptions**
2. Toggle **Enable Events** to ON
3. Under **Subscribe to bot events**, add:
   - `app_mention`
   - `message.channels`
   - `message.groups`
   - `message.im`

### 5e. Install to Workspace

1. Left sidebar → **Install App**
2. Click **Install to Workspace** → **Allow**
3. Copy the `xoxb-...` Bot User OAuth Token — this is your `botToken`

### 5f. Configure Bot Display

1. Left sidebar → **App Home**
2. Set **Display Name (Bot Name)** to `HOOK`
3. Toggle **Always Show My Bot as Online** to ON

### 5g. Add Tokens to Config

```bash
vi ~/.openclaw/openclaw.json
```

Replace the placeholder tokens with your real `xoxb-...` and `xapp-...` tokens.

### 5h. Add Bot to Channel

In Slack, go to your `#hook` channel:

1. Click the channel name at the top
2. Go to **Integrations** tab
3. Click **Add apps**
4. Select **HOOK**

---

## Step 6: Start the Gateway

```bash
openclaw gateway stop
openclaw gateway install --force
openclaw gateway start
```

Wait 10 seconds, then verify:

```bash
openclaw gateway status
```

You should see: `Runtime: running` and `RPC probe: ok`

### Verify Slack connection:

```bash
openclaw channels status --probe
```

You should see: `Slack default: enabled, configured, running, bot:config, app:config, works`

### Verify agents:

```bash
openclaw agents list --bindings
```

You should see all 6 agents listed with correct workspace paths:
- coordinator (default, with slack routing)
- triage-analyst
- osint-researcher
- incident-responder
- threat-intel
- report-writer

---

## Step 7: Test

In the `#hook` Slack channel, try these prompts:

```
# OSINT enrichment
@HOOK analyze this IP: 185.220.101.252

# Alert triage
@HOOK triage this alert: Suricata SID 2024897 ET TROJAN Win32/Emotet CnC Activity detected from 10.0.1.45 to 185.220.101.252

# Incident response
@HOOK we have confirmed Emotet on host WIN-PC0145 (10.0.1.45). What containment steps should we take?

# Threat intelligence
@HOOK map this campaign to MITRE ATT&CK: phishing Excel macro, Emotet loader, Cobalt Strike beacon, lateral movement via SMB, Mimikatz

# Reporting
@HOOK write an executive summary of the Emotet incident for the CISO

# Full test scenario
@HOOK run Operation Frozen Ledger from the test scenarios
```

---

## Troubleshooting

### Gateway crashes on start

Check the error log:

```bash
tail -20 ~/.openclaw/logs/gateway.err.log
```

Common causes:
- Invalid JSON in config (validate with python3 one-liner above)
- Slack tokens still set to placeholders (set `"enabled": false` under slack to start without Slack)
- Schema validation errors (run `openclaw doctor --fix`)

### Gateway starts but Slack doesn't connect

```bash
openclaw channels status --probe
```

If Slack shows `invalid_auth`:
- Verify bot token starts with `xoxb-`
- Verify app token starts with `xapp-`
- Confirm Socket Mode is enabled in the Slack app settings
- Reinstall the app to workspace if tokens were regenerated

### Bot ignores messages in Slack

The log will show `"reason":"no-mention"` — this means the bot received the message but didn't see a valid @mention.

Fix: Type `@` in the channel and select the bot from the autocomplete dropdown. Plain-text `@HOOK` without autocomplete doesn't create a real mention.

If the bot doesn't appear in autocomplete, add it to the channel via **Integrations** → **Add apps**.

### ENOENT: /home/node

The exec sandbox can't find its working directory. Follow Step 3 to unlock `/home` on macOS.

### Port 18789 already in use

```bash
lsof -i :18789
```

Kill whatever is using it:

```bash
docker stop <container_name>
docker rm <container_name>
```

Or if it's a stale OpenClaw process:

```bash
kill <pid>
```

### Config token mismatch warning

If you see "Config token differs from service token":

```bash
openclaw gateway stop
openclaw gateway install --force
openclaw gateway start
```

---

## Architecture

```
Slack (#hook) → Coordinator → spawns specialist agents
                    │
                    ├── triage-analyst (GPT-4.1) — Alert classification
                    ├── osint-researcher (GPT-4.1) — IOC enrichment via VT/Censys/AbuseIPDB
                    ├── incident-responder (GPT-5) — NIST 800-61 containment
                    ├── threat-intel (GPT-5) — MITRE ATT&CK mapping & attribution
                    └── report-writer (GPT-4.1) — Executive summaries & reports
```

All inter-agent communication uses `sessions_spawn` (not `agentToAgent` — see docs/RESEARCH-INTER-AGENT-ROUTING.md for details on bug #5813).

---

## File Locations

| Item | Path |
|------|------|
| Repository | `~/PROJECTS/hook` |
| Config | `~/.openclaw/openclaw.json` |
| Gateway log | `/tmp/openclaw/openclaw-YYYY-MM-DD.log` |
| Gateway stdout | `~/.openclaw/logs/gateway.log` |
| Gateway stderr | `~/.openclaw/logs/gateway.err.log` |
| Agent workspaces | `~/PROJECTS/hook/workspaces/<agent-id>/` |
| Exec sandbox | `/home/node` |
