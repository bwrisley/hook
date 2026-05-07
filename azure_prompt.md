# Claude Code — Shadowbox Azure Deployment Session

You are deploying **Shadowbox**, a multi-agent SOC operations platform, to an **Azure App Service for Containers** instance. You are running directly on the App Service container shell.

## Environment Context

- **Platform**: Azure App Service for Linux (Web App for Containers)
- **OS**: Azure Linux 3 (RHEL-based, uses `tdnf` not `apt`)
- **App Service name**: `ShadowBox`
- **Resource group**: `rg-shadowbox`
- **Web App URL**: probably `shadowbox.azurewebsites.net` (verify with `echo $WEBSITE_HOSTNAME`)
- **CPU**: 2 cores (AMD EPYC)
- **RAM**: 3.8GB
- **Persistent storage**: `/home` (250GB SMB mount, survives restarts)
- **Ephemeral storage**: everything else (wiped on restart)
- **Running as**: root inside the container

## What's Already Done

The Shadowbox repo at https://github.com/bwrisley/hook is feature-complete with:
- 7 AI agents (Marshall coordinator, Tara triage, Hunter OSINT, Ward IR, Driver intel, Page reports, Wells log query)
- Multi-user web UI with auth, sharing, notifications, dashboard, audit log
- 8-source IOC enrichment (VT, AbuseIPDB, Censys, OTX, Shodan, URLhaus, ThreatFox, DNS)
- Watchlist monitoring with auto-investigation alerts
- RAG behavioral memory
- Investigation lifecycle management
- Single-container Docker setup (`Dockerfile`, `docker-compose.yml`)
- Azure deployment infrastructure (`deploy/azure-setup.sh`, GitHub Actions CI/CD)
- Documentation (`docs/BUILD-GUIDE.md`, `docs/DEPLOY-AZURE.md`)

## Architecture

Shadowbox is a **single FastAPI process**. Agents are not a separate service —
the in-process runner at `web/api/agent_runner.py` calls OpenAI directly,
handles tool calls (`exec`) inline, and streams results back over SSE. There
is no Node.js gateway, no second port, no exec-approval daemon.

## What You Need to Build

Adapt the existing Docker-based deployment to **Azure App Service for Containers** (not the Container Apps in the existing scripts). The architecture:

```
Internet
   |
   v
shadowbox.azurewebsites.net (App Service: ShadowBox)
   |
   +-- shadowbox web container (Dockerfile, port 7799)
           |
           +-> Azure Database for PostgreSQL (state)
           +-> /home/data (persistent: feeds, cache, FAISS, investigations)
           +-> OpenAI API (agents — direct, no intermediary)
           +-> Optional: shadowbox-ollama Web App (embeddings only)
           +-> Calls enrichment scripts which call VT/Censys/AbuseIPDB/OTX/Shodan
```

Embeddings for RAG can come from either:
- **Local Ollama** (separate Web App, P1v3 plan, ~$100/mo) — same model the Mac dev box uses
- **OpenAI embeddings** — eliminates the second Web App; pay-per-call instead

Pick one before provisioning.

## Critical Constraints

1. **One container per Web App** — App Service runs a single container. Cannot use docker-compose. The web tier needs a single Web App; Ollama (if used) needs a second one on a larger SKU.
2. **Only `/home` survives restarts** — all persistent data must live there.
3. **Single HTTP port exposed per Web App** — the web container exposes 7799; Ollama (if deployed) exposes 11434 over VNet integration only.
4. **Memory tight on web** — 3.8GB current is fine for the FastAPI process; Ollama would need its own larger Web App.
5. **DO NOT** use the docker-compose approach from the repo — that's for local dev only.
6. **DO NOT** use Container Apps — that's a different Azure service (`deploy/azure-setup.sh` targets Container Apps, useful as reference but not directly applicable to App Service).

## Your Task

Step by step:

### Phase 1: Reconnaissance (do first)

1. Verify the environment:
   ```bash
   uname -a
   tdnf --version || dnf --version
   echo $WEBSITE_HOSTNAME
   echo $WEBSITE_RESOURCE_GROUP
   az --version 2>/dev/null || echo "no az cli"
   docker --version 2>/dev/null || echo "no docker"
   ls /home
   ```

2. Check if `az` CLI is available. If not, you'll need to:
   - Either install it locally and use a different machine for Azure operations
   - Or do everything from the existing App Service (limited)

3. Read the existing repo: https://github.com/bwrisley/hook
   - Key files: `Dockerfile`, `web/api/agent_runner.py`, `web/api/server.py`, `deploy/azure-setup.sh`, `docs/BUILD-GUIDE.md`
   - These target Container Apps. You're adapting to App Service.

4. Decide: Ollama (separate Web App) or OpenAI embeddings (single Web App)? This affects Phase 2.

### Phase 2: Provision Azure Resources

Create using `az` CLI (or Azure Portal):

1. **Azure Database for PostgreSQL**
   - Name: `shadowbox-db`
   - Resource group: `rg-shadowbox`
   - SKU: Burstable B1ms (~$25/mo) for dev
   - Database name: `shadowbox`
   - Enable SSL, firewall to allow App Service subnet only

2. **Azure Key Vault**
   - Name: `shadowbox-kv`
   - Store all API keys (OpenAI, VT, Censys, AbuseIPDB, OTX, Shodan)
   - Store DATABASE_URL

3. **App Service plans + Web Apps**:
   - `shadowbox` — existing, web UI + agent runner (current spec is fine)
   - `shadowbox-ollama` — only if you chose local embeddings; P1v3 (8GB RAM minimum)

4. **VNet integration** so the Web Apps can talk privately (only needed if Ollama is deployed)
   - Create VNet `shadowbox-vnet`
   - Subnets for app, db, ollama (if used)
   - Enable VNet integration on each Web App

5. **Azure Container Registry** (or use GitHub Container Registry)
   - Name: `shadowboxacr` (must be globally unique)
   - Or skip and use `ghcr.io/bwrisley/hook/*` (already configured in CI/CD)

### Phase 3: Build and Push Images

If using ACR:
```bash
az acr build --registry shadowboxacr --image shadowbox-web:latest -f Dockerfile .
```

If using GitHub Container Registry: the existing CI/CD already does this on push to `main`.

For Ollama (if deployed), use the official image: `ollama/ollama:latest`. There is no Shadowbox-specific gateway image — that tier was eliminated.

### Phase 4: Configure Web App(s)

For each Web App, set:

1. **Container settings** — point to the right image
2. **Environment variables** — pull from Key Vault using references
3. **`WEBSITES_PORT`** — set to the container's listening port (7799 for web; 11434 for Ollama if deployed)
4. **`WEBSITES_ENABLE_APP_SERVICE_STORAGE=true`** — mounts `/home` as persistent
5. **Always On** — enable to prevent cold starts
6. **VNet integration** — assign to the right subnet (only if Ollama is deployed)
7. **Health check path** — `/api/health` for shadowbox web

### Phase 5: Wire Internal Communication (only if Ollama is deployed)

The web Web App calls Ollama internally:

- `OLLAMA_BASE_URL=http://shadowbox-ollama.internal.azurewebsites.net:11434`

Use VNet integration + private DNS to keep traffic off the public internet.

If you chose OpenAI embeddings instead, set the relevant env var and skip this phase.

### Phase 6: Pull Ollama Models (only if Ollama is deployed)

SSH into the ollama Web App and run:
```bash
ollama pull nomic-embed-text
ollama pull qwen2.5:14b
```

Mount path: `/home/ollama-models` so models persist.

### Phase 7: Initialize Database

Run the SQL schema. The Python `WebSessionDB`, `AuthDB`, and `WatchlistDB` classes auto-create tables on first run, so just verify the connection works:

```bash
psql "postgresql://shadowbox:<pass>@shadowbox-db.postgres.database.azure.com:5432/shadowbox?sslmode=require" -c "\dt"
```

### Phase 8: Verify

1. Open https://shadowbox.azurewebsites.net
2. Login as `admin` / `shadowbox`
3. **Change admin password immediately**
4. Test enrichment: "Enrich 8.8.8.8"
5. Check `/api/health` shows all green

### Phase 9: Custom Domain + SSL

When ready to go public:
1. CNAME `shadowbox.punchcyber.com` → `shadowbox.azurewebsites.net`
2. Add custom domain in Azure Portal
3. Enable managed SSL certificate

## Key Files to Reference

- `Dockerfile` — Shadowbox web image (single-container, includes the agent runner)
- `web/api/server.py` — main FastAPI app
- `web/api/agent_runner.py` — in-process OpenAI agent runner (replaces the old gateway)
- `web/api/database.py` — already supports PostgreSQL via DATABASE_URL env var
- `docs/BUILD-GUIDE.md` — junior engineer guide for Container Apps (adapt for App Service)

## Code Changes That May Be Needed

The codebase is designed for both SQLite and PostgreSQL. Verify these still work:

1. `web/api/database.py` — database adapter (already done)
2. `web/api/server.py` — uses SQLite directly in some places. If switching to PostgreSQL, may need to refactor `WebSessionDB`, `AuthDB`, `WatchlistDB`, `AgentTracker` to use the `Database` adapter class.
3. `core/llm/ollama_provider.py` — already supports `OLLAMA_BASE_URL` env var (only relevant if you chose local Ollama embeddings)
4. `core/rag/engine.py` — uses Ollama embeddings (768 dims) by default; swap to OpenAI embeddings if you skipped the Ollama Web App

## What I Want From You

Work step by step through Phases 1-9. Ask questions if Azure CLI is not available or if the Ollama-vs-OpenAI-embeddings decision hasn't been made. Don't assume — always verify environment state before building. Confirm each phase before moving to the next.

Start with **Phase 1: Reconnaissance**. Run the commands and report back what you find before doing anything else.

## Background Context You Should Know

- The user is bww at PUNCH Cyber
- They've been building this for several phases (Phase 6 was the web UI buildout; Phase 7 eliminated the OpenClaw gateway in favor of a direct OpenAI agent runner)
- The Mac Studio is the dev environment, will be deprecated once Azure is working
- Default admin login is `admin` / `shadowbox` — must be changed
- All API keys are currently in `.env` (gitignored) on the Mac Studio — they will need to be re-added in Azure Key Vault
