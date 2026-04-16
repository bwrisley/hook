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
- Full Docker setup (Dockerfile, Dockerfile.gateway, docker-compose.yml)
- Azure deployment infrastructure (deploy/azure-setup.sh, GitHub Actions CI/CD)
- Documentation (docs/BUILD-GUIDE.md, docs/DEPLOY-AZURE.md)

## What You Need to Build

Adapt the existing Docker-based deployment to **Azure App Service for Containers** (not the Container Apps in the existing scripts). The architecture:

```
Internet
   |
   v
shadowbox.azurewebsites.net (App Service: ShadowBox)
   |
   +-- shadowbox web container (existing Dockerfile, port 7799)
   |       |
   |       +-> Azure Database for PostgreSQL (state)
   |       +-> /home/data (persistent: feeds, cache, FAISS, investigations)
   |       +-> shadowbox-gateway (HTTP, internal)
   |       +-> shadowbox-ollama (HTTP, internal)
   |
shadowbox-gateway.azurewebsites.net (separate App Service)
   |
   +-- OpenClaw gateway container (existing Dockerfile.gateway, port 18789)
   |       +-> calls OpenAI API (already accessible)
   |       +-> calls enrichment scripts which call VT/Censys/AbuseIPDB/OTX/Shodan
   |
shadowbox-ollama.azurewebsites.net (separate App Service, larger SKU)
   |
   +-- Ollama container (port 11434)
           +-> nomic-embed-text + qwen2.5:14b models
           +-> needs 8GB+ RAM (P1v3 plan or higher)
           +-> models stored in /home/ollama-models (persistent)
```

## Critical Constraints

1. **One container per Web App** — App Service runs a single container. Cannot use docker-compose. Must split into 3 separate Web Apps.
2. **Only `/home` survives restarts** — all persistent data must live there
3. **Single HTTP port exposed per Web App** — internal services communicate via VNet integration
4. **Memory tight on web** — 3.8GB current. Ollama needs its own larger Web App.
5. **DO NOT** use the docker-compose approach from the repo — that's for local dev only.
6. **DO NOT** use Container Apps — that's a different Azure service (deploy/azure-setup.sh targets Container Apps, useful as reference but not directly applicable).

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
   - Key files: `Dockerfile`, `Dockerfile.gateway`, `deploy/azure-setup.sh`, `docs/BUILD-GUIDE.md`
   - These target Container Apps. You're adapting to App Service.

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

3. **Three App Service plans + Web Apps**:
   - `shadowbox` — existing, web UI (current spec is fine)
   - `shadowbox-gateway` — new, OpenClaw (S1 minimum, 1.75GB RAM)
   - `shadowbox-ollama` — new, P1v3 (8GB RAM minimum, 4GB models + overhead)

4. **VNet integration** so the three Web Apps can talk privately
   - Create VNet `shadowbox-vnet`
   - Subnets for app, db, ollama
   - Enable VNet integration on each Web App

5. **Azure Container Registry** (or use GitHub Container Registry)
   - Name: `shadowboxacr` (must be globally unique)
   - Or skip and use `ghcr.io/bwrisley/hook/*` (already configured in CI/CD)

### Phase 3: Build and Push Images

If using ACR:
```bash
az acr build --registry shadowboxacr --image shadowbox-web:latest -f Dockerfile .
az acr build --registry shadowboxacr --image shadowbox-gateway:latest -f Dockerfile.gateway .
```

If using GitHub Container Registry: the existing CI/CD already does this on push to `main`.

For Ollama, use the official image: `ollama/ollama:latest`

### Phase 4: Configure Web Apps

For each Web App, set:

1. **Container settings** — point to the right image
2. **Environment variables** — pull from Key Vault using references
3. **`WEBSITES_PORT`** — set to the container's listening port (7799, 18789, 11434)
4. **`WEBSITES_ENABLE_APP_SERVICE_STORAGE=true`** — mounts `/home` as persistent
5. **Always On** — enable to prevent cold starts
6. **VNet integration** — assign to the right subnet
7. **Health check path** — `/api/health` for shadowbox web

### Phase 5: Wire Internal Communication

The three Web Apps must talk to each other internally:

- Web app calls Gateway: set `HOOK_GATEWAY_URL=http://shadowbox-gateway.internal.azurewebsites.net:18789`
- Web app calls Ollama: set `OLLAMA_BASE_URL=http://shadowbox-ollama.internal.azurewebsites.net:11434`

Use VNet integration + private DNS to keep traffic off the public internet.

### Phase 6: Pull Ollama Models

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

- `Dockerfile` — Shadowbox web image
- `Dockerfile.gateway` — OpenClaw gateway image
- `web/api/server.py` — main FastAPI app
- `web/api/database.py` — already supports PostgreSQL via DATABASE_URL env var
- `deploy/openclaw-azure.json` — gateway config template
- `docs/BUILD-GUIDE.md` — junior engineer guide for Container Apps (adapt for App Service)

## Code Changes That May Be Needed

The codebase is designed for both SQLite and PostgreSQL. Verify these still work:

1. `web/api/database.py` — database adapter (already done)
2. `web/api/server.py` — uses SQLite directly in some places. If switching to PostgreSQL, may need to refactor `WebSessionDB`, `AuthDB`, `WatchlistDB`, `AgentTracker` to use the `Database` adapter class.
3. `core/llm/ollama_provider.py` — already supports `OLLAMA_BASE_URL` env var
4. `core/rag/engine.py` — uses Ollama embeddings (768 dims)

## What I Want From You

Work step by step through Phases 1-9. Ask questions if Azure CLI is not available. Don't assume — always verify environment state before building. Confirm each phase before moving to the next.

Start with **Phase 1: Reconnaissance**. Run the commands and report back what you find before doing anything else.

## Background Context You Should Know

- The user is bww at PUNCH Cyber
- They've been building this for several phases (Phase 6 was the web UI buildout)
- The Mac Studio is the dev environment, will be deprecated once Azure is working
- Default admin login is `admin` / `shadowbox` — must be changed
- All API keys are currently in `.env` (gitignored) on the Mac Studio — they will need to be re-added in Azure Key Vault
