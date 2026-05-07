# HOOK Installation Guide

**HOOK / Shadowbox — Hunting, Orchestration & Operational Knowledge**
by PUNCH Cyber

A start-to-finish guide for setting up Shadowbox on macOS for local
development. Every step is explained; if you follow this guide you will
have a working multi-agent SOC assistant accessible at
http://localhost:7799.

**Time estimate:** 15–30 minutes (most of it is downloading Ollama models).

---

## Architecture Overview

```
Browser (http://localhost:7799)
    │
    ▼
FastAPI web service (uvicorn, port 7799)
    │
    ├── In-process agent runner (web/api/agent_runner.py)
    │       └── calls OpenAI API directly
    │
    ├── SQLite (data/hook-web.db) — sessions, messages, users, watchlist
    │
    ├── Ollama (localhost:11434) — embeddings + local chat
    │
    └── Enrichment scripts (scripts/enrich-*.sh) — VT, Censys, AbuseIPDB,
                                                   OTX, Shodan, URLhaus,
                                                   ThreatFox, DNS
```

There is no Node.js gateway, no Slack daemon, and no separate exec-approval
service. The web container is the whole stack.

---

## Prerequisites

### Accounts & API Keys

OpenAI is required. The threat-intel sources are recommended but optional —
agents will gracefully skip a source if its key is unset.

| Service     | Sign Up                                     | What you need                | Free tier               |
|-------------|---------------------------------------------|------------------------------|-------------------------|
| OpenAI      | https://platform.openai.com                 | API key (gpt-4.1, gpt-5)     | Pay-as-you-go (required)|
| VirusTotal  | https://www.virustotal.com/gui/join-us      | API key                      | 4 req/min               |
| Censys      | https://search.censys.io/register           | API ID + Secret              | 250 queries/month       |
| AbuseIPDB   | https://www.abuseipdb.com/register          | API key                      | 1000 checks/day         |
| AlienVault OTX | https://otx.alienvault.com/                | API key                      | Free, generous          |
| Shodan      | https://account.shodan.io/register          | API key                      | Limited free tier       |

### Software

| Tool      | Check                | Install                          |
|-----------|----------------------|----------------------------------|
| macOS     | —                    | Tested on Apple Silicon          |
| Homebrew  | `brew --version`     | https://brew.sh                  |
| Python ≥ 3.13 | `python3 --version` | `brew install python@3.13`     |
| Node ≥ 22 | `node --version`     | `brew install node@22`           |
| Git       | `git --version`      | `brew install git`               |
| Ollama    | `ollama --version`   | `brew install ollama`            |

The setup script will check these and offer to install the missing ones.

---

## Step 1: Clone the Repository

```bash
cd ~/projects   # or wherever you keep repos
git clone git@github.com:bwrisley/hook.git
cd hook
```

---

## Step 2: Run the Setup Script

```bash
./install/setup.sh
```

The script will:

1. Verify prerequisites (Python 3.13+, Node 22+, Homebrew, Ollama)
2. Offer to `brew install` any missing CLI tools (jq, bind, whois, nmap)
3. Create `.venv/` and install Python dependencies
4. Install npm packages and build the frontend bundle
5. Create `.env` from the template if it doesn't exist, and prompt for keys
6. Start Ollama if it isn't already running
7. Offer to pull the embedding model (`nomic-embed-text`) and the local
   chat model (`qwen2.5:14b`, ~9 GB — skippable)
8. Offer to install the macOS LaunchAgent so the web UI auto-starts at login

If you skip the API-key prompts you can edit `.env` later by hand. The
prompts only fill blank values — existing entries are preserved.

---

## Step 3: Verify

The setup script ends by hitting `http://localhost:7799/api/status`. If
that responded `200 OK` you're done. Otherwise, start the service manually:

```bash
./scripts/restart.sh web
curl -s http://localhost:7799/api/status
```

You should see something like:

```json
{
  "name": "HOOK",
  "version": "6.0.0",
  "agent_provider": {"status": "ok", "provider": "openai"},
  "agent_count": 7,
  "active_investigations": 0
}
```

Open `http://localhost:7799` in your browser. The default login is:

- Username: `admin`
- Password: `shadowbox`

**Change the admin password immediately** — Settings → Users → admin → Reset PW.

---

## Step 4: First Test

In the **Investigate** page, type:

```
Enrich 8.8.8.8
```

Expected: Hunter (osint-researcher) runs VT + AbuseIPDB + Censys + OTX +
Shodan + URLhaus + ThreatFox + DNS in parallel and returns a multi-source
enrichment report within ~30 seconds.

Then try a routing test:

```
Triage this alert: PowerShell encoded command on WKSTN-FIN-042 contacting 45.77.65.211
```

Expected: Marshall (coordinator) routes to Tara (triage-analyst), who
returns a verdict, MITRE mapping, and recommended next steps.

---

## Manual Setup (Alternative)

If you'd rather do it by hand:

```bash
# 1. Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Frontend
cd web && npm ci && npm run build && cd ..

# 3. CLI tools
brew install jq bind whois nmap

# 4. Ollama
brew install ollama
brew services start ollama
ollama pull nomic-embed-text
ollama pull qwen2.5:14b   # optional

# 5. Config
cp .env.example .env
# edit .env and fill in API keys

# 6. Start
./scripts/restart.sh web
```

---

## Optional: Install the LaunchAgent

The repo ships a plist at `config/com.punchcyber.hook.web.plist`. The setup
script can install and load it for you, or you can do it manually:

```bash
# Render the template into your LaunchAgents directory
HOOK_DIR="$(pwd)"
LOG_DIR="$HOME/.openclaw/logs/hook"
mkdir -p "$LOG_DIR"
sed -e "s|HOOK_REPO_PATH|$HOOK_DIR|g" -e "s|HOOK_LOG_PATH|$LOG_DIR|g" \
    config/com.punchcyber.hook.web.plist \
    > ~/Library/LaunchAgents/com.punchcyber.hook.web.plist

# Load it (will auto-start at login from now on)
launchctl bootstrap "gui/$(id -u)" \
    ~/Library/LaunchAgents/com.punchcyber.hook.web.plist

# Verify
./scripts/restart.sh status
```

Once loaded, manage it with `./scripts/restart.sh web|stop|status`.

---

## Troubleshooting

### Web won't start

```bash
# Tail the LaunchAgent logs
tail -50 ~/.openclaw/logs/hook/web-stderr.log

# Or run uvicorn in the foreground to see the traceback
.venv/bin/python -m uvicorn web.api.server:app --host 0.0.0.0 --port 7799
```

Common causes: missing Python dependency, port 7799 already bound, syntax
error in `.env`, frontend not built (no `web/dist/` directory).

### API keys not picked up

The web service reads `.env` on startup. After editing `.env`, restart:

```bash
./scripts/restart.sh web
```

Verify keys are loaded:

```bash
curl -s http://localhost:7799/api/health | python3 -m json.tool | grep -A 8 api_keys
```

### Ollama unreachable / RAG empty

```bash
brew services list | grep ollama
curl -s http://localhost:11434/api/tags | python3 -m json.tool

# If it's not running:
brew services start ollama

# If models are missing:
ollama pull nomic-embed-text
```

The `agent_provider` health check is OpenAI-only — Ollama is optional and
its status surfaces under `checks.ollama` in `/api/health`.

### Database locked / corrupted

```bash
# Reset the dev database (destroys all conversations/users/watchlist)
./scripts/restart.sh stop
mv data/hook-web.db data/hook-web.db.bak
./scripts/restart.sh web
```

The schema is recreated on first request; admin login resets to `admin/shadowbox`.

### Enrichment script failing for one source

Each script supports `--source <name>` for single-source debugging:

```bash
./scripts/enrich-ip.sh 8.8.8.8 --source virustotal
./scripts/enrich-ip.sh 8.8.8.8 --source censys
./scripts/enrich-ip.sh 8.8.8.8 --source abuseipdb
```

If all sources fail, check the corresponding key in `.env`. If one
source fails, the API likely changed or the key is over its quota.

---

## File Reference

| File / Dir                              | Purpose                                                      |
|-----------------------------------------|--------------------------------------------------------------|
| `web/api/server.py`                     | FastAPI app — routes, auth, DB, audit log                    |
| `web/api/agent_runner.py`               | In-process OpenAI agent runner with exec tool support        |
| `web/src/`                              | React frontend (Vite + Tailwind)                             |
| `workspaces/<agent>/SOUL.md`            | Agent personality, routing rules, capabilities               |
| `workspaces/<agent>/TOOLS.md`           | Tool instructions and command templates                      |
| `scripts/enrich-*.sh`                   | IOC enrichment scripts (one per IOC type)                    |
| `scripts/restart.sh`                    | Start/stop/status for the web LaunchAgent                    |
| `data/hook-web.db`                      | SQLite — sessions, messages, users, watchlist (gitignored)   |
| `data/feeds/`, `data/cache/`            | Threat-feed snapshots and enrichment cache (gitignored)      |
| `data/faiss/`                           | RAG vector store (gitignored)                                |
| `.env`                                  | API keys and runtime config (gitignored)                     |
| `config/com.punchcyber.hook.web.plist`  | LaunchAgent template (placeholders for HOOK_REPO_PATH etc.)  |

---

## What's Next

1. Open `http://localhost:7799`, change the admin password, and create
   accounts for your team.
2. Add IOCs to the watchlist (Investigations → Watchlist) — re-enrichment
   runs automatically every 4 hours via `com.punchcyber.hook.watch-check`.
3. To deploy to Azure, see `docs/DEPLOY-AZURE.md` (Container Apps) or
   `azure_prompt.md` (Azure App Service for Containers).
4. Slack integration is planned but not yet wired up — env vars are
   reserved in `.env.example` (`SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`).
