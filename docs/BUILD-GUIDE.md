# Shadowbox Build & Deployment Guide

**For: Junior Engineers**
**Time: ~2 hours**
**Result: Shadowbox running in Azure, accessible at shadowbox.punchcyber.com**

---

## What You're Building

Shadowbox is a multi-agent SOC assistant. It has 4 containers:

| Container | What it does | Port |
|-----------|-------------|------|
| **shadowbox-web** | Web UI + API (what analysts use) | 7799 |
| **shadowbox-gateway** | AI agent runtime (OpenClaw) | 18789 |
| **shadowbox-ollama** | Local AI for embeddings | 11434 |
| **db** | PostgreSQL database | 5432 |

---

## Prerequisites

Before you start, you need:

- [ ] A Mac or Linux machine for running commands
- [ ] Azure account with admin access
- [ ] GitHub account with access to the `bwrisley/hook` repo
- [ ] The API keys (ask your lead for these):
  - OpenAI API key
  - VirusTotal API key
  - Censys API ID + Secret
  - AbuseIPDB API key
  - AlienVault OTX API key
  - Shodan API key
- [ ] DNS access to `punchcyber.com`

---

## Part 1: Install Tools (One Time)

### 1.1 Install Azure CLI

```bash
# Mac
brew install azure-cli

# Linux
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

Verify:
```bash
az --version
# Should show: azure-cli 2.x.x
```

### 1.2 Install Docker

```bash
# Mac
brew install --cask docker
# Open Docker Desktop from Applications and wait for it to start

# Linux
sudo apt-get install docker.io docker-compose-plugin
sudo usermod -aG docker $USER
# Log out and back in
```

Verify:
```bash
docker --version
# Should show: Docker version 2x.x.x
```

### 1.3 Install Node.js

```bash
brew install node@22
```

Verify:
```bash
node --version
# Should show: v22.x.x
```

### 1.4 Clone the Repository

```bash
cd ~/projects
git clone https://github.com/bwrisley/hook.git
cd hook
```

---

## Part 2: Test Locally with Docker (30 min)

Before deploying to Azure, verify everything works on your machine.

### 2.1 Create Environment File

```bash
cp .env.example .env
```

Edit `.env` and fill in ALL API keys:
```bash
nano .env
```

The file should look like this (with real keys):
```
OPENAI_API_KEY=sk-proj-xxx...
VT_API_KEY=xxx...
CENSYS_API_ID=xxx...
CENSYS_API_SECRET=xxx...
ABUSEIPDB_API_KEY=xxx...
OTX_API_KEY=xxx...
SHODAN_API_KEY=xxx...
```

Save and exit (Ctrl+X, Y, Enter in nano).

### 2.2 Build and Start

```bash
docker compose build
```

This takes 3-5 minutes the first time. You should see:
```
=> [web] Successfully built
=> [gateway] Successfully built
```

Start everything:
```bash
docker compose up -d
```

Check all containers are running:
```bash
docker compose ps
```

You should see 4 containers with status "Up":
```
NAME                 STATUS
hook-web-1           Up
hook-gateway-1       Up
hook-db-1            Up (healthy)
hook-ollama-1        Up
```

### 2.3 Pull AI Models into Ollama

```bash
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull qwen2.5:14b
```

The second model is ~9GB — wait for it to finish.

### 2.4 Verify It Works

Open your browser: **http://localhost:7799**

You should see the Shadowbox login page (orange/black theme).

Login: `admin` / `shadowbox`

Test: Type "Enrich 8.8.8.8" in the Investigate page. You should get a multi-source enrichment report within 30 seconds.

### 2.5 Stop Local Stack

```bash
docker compose down
```

---

## Part 3: Deploy to Azure (1 hour)

### 3.1 Login to Azure

```bash
az login
```

This opens a browser — sign in with your Azure account.

Set the correct subscription:
```bash
# List subscriptions
az account list --output table

# Set the right one
az account set --subscription "<subscription-name-or-id>"

# Verify
az account show --output table
```

### 3.2 Create Dev Environment

```bash
chmod +x deploy/azure-setup.sh
./deploy/azure-setup.sh dev
```

This takes 10-15 minutes. It creates:
- Resource group
- PostgreSQL database
- Key Vault for secrets
- Storage account
- 3 container apps (web, gateway, ollama)

**SAVE THE OUTPUT** — it contains the database password and next steps.

### 3.3 Add API Keys to Key Vault

Replace `<your-key>` with the actual keys:

```bash
KV="shadowbox-kv-dev"

az keyvault secret set --vault-name $KV \
    --name openai-api-key --value "<your-openai-key>"

az keyvault secret set --vault-name $KV \
    --name vt-api-key --value "<your-vt-key>"

az keyvault secret set --vault-name $KV \
    --name censys-api-id --value "<your-censys-id>"

az keyvault secret set --vault-name $KV \
    --name censys-api-secret --value "<your-censys-secret>"

az keyvault secret set --vault-name $KV \
    --name abuseipdb-api-key --value "<your-abuseipdb-key>"

az keyvault secret set --vault-name $KV \
    --name otx-api-key --value "<your-otx-key>"

az keyvault secret set --vault-name $KV \
    --name shodan-api-key --value "<your-shodan-key>"
```

### 3.4 Pull Ollama Models

```bash
RG="shadowbox-dev"

az containerapp exec \
    --name shadowbox-ollama \
    --resource-group $RG \
    --command "ollama pull nomic-embed-text"

az containerapp exec \
    --name shadowbox-ollama \
    --resource-group $RG \
    --command "ollama pull qwen2.5:14b"
```

Wait for both to complete.

### 3.5 Get Your URL

```bash
az containerapp show \
    --name shadowbox-web \
    --resource-group shadowbox-dev \
    --query "properties.configuration.ingress.fqdn" \
    --output tsv
```

This prints something like: `shadowbox-web.kindmushroom-abc123.eastus.azurecontainerapps.io`

Open it in your browser with `https://` — you should see the login page.

### 3.6 Verify Health

```bash
WEB_URL="<url-from-step-3.5>"
curl -s "https://${WEB_URL}/api/health" | python3 -m json.tool
```

You should see `"status": "healthy"` or `"status": "degraded"` (degraded is OK if Ollama models are still loading).

---

## Part 4: Configure DNS (15 min)

### 4.1 Add CNAME Record

In your DNS provider (Cloudflare, Route53, etc.), add:

```
Type:  CNAME
Name:  dev-shadowbox    (or shadowbox for prod)
Value: <url-from-step-3.5>
TTL:   Auto
```

### 4.2 Add Custom Domain in Azure

1. Go to Azure Portal (https://portal.azure.com)
2. Search for "Container Apps"
3. Click `shadowbox-web`
4. Left menu > Custom domains
5. Click "Add custom domain"
6. Enter: `dev-shadowbox.punchcyber.com`
7. Choose "Managed certificate"
8. Click Validate, then Add

Wait 5-10 minutes for the SSL certificate to provision.

### 4.3 Test

Open: **https://dev-shadowbox.punchcyber.com**

Login: `admin` / `shadowbox`

**IMPORTANT: Change the admin password immediately.**
Go to Users page > admin > Reset PW.

---

## Part 5: Set Up CI/CD (20 min)

### 5.1 Create Azure Service Principal

```bash
# Get your subscription ID
SUB_ID=$(az account show --query id -o tsv)

az ad sp create-for-rbac \
    --name "shadowbox-deploy" \
    --role contributor \
    --scopes "/subscriptions/${SUB_ID}/resourceGroups/shadowbox-dev" \
    --sdk-auth
```

**COPY THE ENTIRE JSON OUTPUT** — you'll need it in the next step.

### 5.2 Add GitHub Secrets

1. Go to: https://github.com/bwrisley/hook/settings/secrets/actions
2. Click "New repository secret"
3. Name: `AZURE_CREDENTIALS`
4. Value: Paste the JSON from step 5.1
5. Click "Add secret"

### 5.3 Create GitHub Environments

1. Go to: https://github.com/bwrisley/hook/settings/environments
2. Click "New environment"
3. Name: `dev` — click "Configure environment" — no special settings needed
4. Click "New environment" again
5. Name: `prod` — click "Configure environment"
6. Check "Required reviewers" — add yourself
7. Save

### 5.4 Test CI/CD

```bash
# Create dev branch
git checkout -b dev
git push origin dev
```

Go to: https://github.com/bwrisley/hook/actions

You should see a workflow running. It will:
1. Run tests
2. Build Docker images
3. Push to GitHub Container Registry
4. Deploy to Azure dev environment

---

## Part 6: Deploy to Production

### 6.1 Create Production Environment

```bash
./deploy/azure-setup.sh prod
```

### 6.2 Repeat Steps 3.3-3.4 for Production

Use `shadowbox-kv-prod` and `shadowbox-prod` instead of dev.

### 6.3 Configure Production DNS

```
Type:  CNAME
Name:  shadowbox
Value: <prod-web-url>
```

### 6.4 Deploy

```bash
git checkout main
git merge dev
git push origin main
```

Go to GitHub Actions — the workflow will wait for approval (you configured this in 5.3). Click "Review deployments" > "Approve and deploy."

---

## Troubleshooting

### Container won't start

```bash
# Check logs
az containerapp logs show \
    --name shadowbox-web \
    --resource-group shadowbox-dev \
    --follow
```

### Database connection error

```bash
# Verify database is running
az postgres flexible-server show \
    --name shadowbox-db-dev \
    --resource-group shadowbox-dev \
    --query "state"
```

### Ollama models not loading

```bash
# Check Ollama logs
az containerapp logs show \
    --name shadowbox-ollama \
    --resource-group shadowbox-dev \
    --follow

# List loaded models
az containerapp exec \
    --name shadowbox-ollama \
    --resource-group shadowbox-dev \
    --command "ollama list"
```

### Enrichment timing out

Check that API keys are set in Key Vault:
```bash
az keyvault secret list \
    --vault-name shadowbox-kv-dev \
    --output table
```

### Can't access the web UI

1. Check the container is running: `az containerapp show --name shadowbox-web --resource-group shadowbox-dev --query "properties.runningStatus"`
2. Check ingress is external: should be "external" not "internal"
3. Check DNS CNAME is pointing to the right URL

### Need to restart everything

```bash
RG="shadowbox-dev"
az containerapp revision restart --name shadowbox-web --resource-group $RG
az containerapp revision restart --name shadowbox-gateway --resource-group $RG
az containerapp revision restart --name shadowbox-ollama --resource-group $RG
```

---

## Quick Reference

| What | Command |
|------|---------|
| View logs | `az containerapp logs show --name shadowbox-web --resource-group shadowbox-dev --follow` |
| Restart web | `az containerapp revision restart --name shadowbox-web --resource-group shadowbox-dev` |
| Scale up | `az containerapp update --name shadowbox-web --resource-group shadowbox-dev --max-replicas 5` |
| Check health | `curl https://dev-shadowbox.punchcyber.com/api/health` |
| DB backup | `pg_dump "<DATABASE_URL>" > backup.sql` |
| Add user | Login as admin > Users > Add User |
| Check Key Vault | `az keyvault secret list --vault-name shadowbox-kv-dev -o table` |

---

## Contacts

- **Architecture questions**: Ask your lead
- **Azure access issues**: IT / Cloud team
- **API key requests**: Security team lead
- **DNS changes**: IT / Network team
