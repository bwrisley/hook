# Shadowbox Azure Deployment Guide

## Architecture

```
Internet -> Azure App Gateway (WAF + SSL)
                    |
         Azure Container Apps Environment
         |              |              |
    shadowbox-web  shadowbox-gateway  shadowbox-ollama
    (FastAPI+React) (OpenClaw+Agents)  (Embeddings+Chat)
         |
    Azure PostgreSQL     Azure Key Vault     Azure Blob Storage
    (sessions, messages, (API keys,          (feeds, cache,
     activity, auth)      secrets)            RAG vectors)
```

## Prerequisites

- Azure CLI installed (`brew install azure-cli`)
- Azure subscription with Owner or Contributor access
- GitHub repository with container registry access
- Domain: `shadowbox.punchcyber.com` (DNS access)

## Step 1: Azure Login

```bash
az login
az account set --subscription "<your-subscription-id>"
az account show  # Verify correct subscription
```

## Step 2: Create Dev Environment

```bash
./deploy/azure-setup.sh dev
```

This creates:
- Resource group: `shadowbox-dev`
- PostgreSQL (Burstable B1ms): `shadowbox-db-dev`
- Key Vault: `shadowbox-kv-dev`
- Storage Account: `shadowboxstoragedev`
- Container Apps: `shadowbox-web`, `shadowbox-gateway`, `shadowbox-ollama`

## Step 3: Add API Keys to Key Vault

```bash
KV="shadowbox-kv-dev"

az keyvault secret set --vault-name $KV --name openai-api-key --value "<your-key>"
az keyvault secret set --vault-name $KV --name vt-api-key --value "<your-key>"
az keyvault secret set --vault-name $KV --name censys-api-id --value "<your-key>"
az keyvault secret set --vault-name $KV --name censys-api-secret --value "<your-key>"
az keyvault secret set --vault-name $KV --name abuseipdb-api-key --value "<your-key>"
az keyvault secret set --vault-name $KV --name otx-api-key --value "<your-key>"
az keyvault secret set --vault-name $KV --name shodan-api-key --value "<your-key>"
```

## Step 4: Pull Ollama Models

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

## Step 5: Configure OpenClaw

The gateway needs an `openclaw.json` config. Create it in the gateway container's volume:

```bash
az containerapp exec \
    --name shadowbox-gateway \
    --resource-group $RG \
    --command "cat > /home/node/.openclaw/openclaw.json" < deploy/openclaw-azure.json
```

Use `deploy/openclaw-azure.json` as template (provided in the repo).

## Step 6: Verify Deployment

```bash
# Get the web URL
WEB_URL=$(az containerapp show \
    --name shadowbox-web \
    --resource-group $RG \
    --query "properties.configuration.ingress.fqdn" -o tsv)

echo "https://${WEB_URL}"

# Test health
curl -s "https://${WEB_URL}/api/health" | python3 -m json.tool
```

Login with default credentials: `admin` / `shadowbox`

**Change the admin password immediately.**

## Step 7: Configure DNS

Add a CNAME record for your domain:

```
dev-shadowbox.punchcyber.com  CNAME  <web-url-from-step-6>
```

Then add the custom domain in Azure Portal:
1. Container Apps > shadowbox-web > Custom Domains
2. Add `dev-shadowbox.punchcyber.com`
3. Enable managed SSL certificate

## Step 8: Set Up GitHub Actions

### Create Azure Service Principal

```bash
az ad sp create-for-rbac \
    --name "shadowbox-deploy" \
    --role contributor \
    --scopes /subscriptions/<subscription-id>/resourceGroups/shadowbox-dev \
            /subscriptions/<subscription-id>/resourceGroups/shadowbox-prod \
    --sdk-auth
```

### Add GitHub Secrets

In GitHub repo Settings > Secrets > Actions:

| Secret | Value |
|--------|-------|
| `AZURE_CREDENTIALS` | Output from `az ad sp create-for-rbac` above |

### Create Environments

In GitHub repo Settings > Environments:

1. Create `dev` environment (auto-deploy from `dev` branch)
2. Create `prod` environment (require approval, deploy from `main`)

## Step 9: Create Production Environment

```bash
./deploy/azure-setup.sh prod
```

Repeat Steps 3-7 for production with:
- Resource group: `shadowbox-prod`
- Key Vault: `shadowbox-kv-prod`
- Domain: `shadowbox.punchcyber.com`

## Step 10: Deploy via CI/CD

```bash
# Dev deployment
git checkout -b dev
git push origin dev  # Auto-deploys to dev

# Prod deployment
git checkout main
git merge dev
git push origin main  # Auto-deploys to prod (after approval)
```

## Operational Guide

### Scaling

```bash
# Scale web app
az containerapp update \
    --name shadowbox-web \
    --resource-group shadowbox-prod \
    --min-replicas 2 --max-replicas 10

# Scale gateway
az containerapp update \
    --name shadowbox-gateway \
    --resource-group shadowbox-prod \
    --min-replicas 2 --max-replicas 5
```

### Logs

```bash
# Web logs
az containerapp logs show \
    --name shadowbox-web \
    --resource-group shadowbox-prod \
    --follow

# Gateway logs
az containerapp logs show \
    --name shadowbox-gateway \
    --resource-group shadowbox-prod \
    --follow
```

### Database Backup

Azure PostgreSQL includes automatic daily backups (7-day retention on Basic, 35-day on Standard).

Manual backup:
```bash
pg_dump "postgresql://shadowbox:<password>@shadowbox-db-prod.postgres.database.azure.com:5432/shadowbox?sslmode=require" > backup.sql
```

### Rotate API Keys

```bash
KV="shadowbox-kv-prod"
az keyvault secret set --vault-name $KV --name openai-api-key --value "<new-key>"

# Restart containers to pick up new secrets
az containerapp revision restart \
    --name shadowbox-web \
    --resource-group shadowbox-prod
```

### Monitoring

Set up Azure Monitor alerts:
1. Container App > Monitoring > Alerts
2. Create alert for: CPU > 80%, Memory > 80%, HTTP 5xx > 5/min
3. Action group: email to SOC team

## Cost Estimate (Dev)

| Resource | SKU | Estimated Monthly |
|----------|-----|------------------|
| Container App (web) | 1 vCPU, 2GB | ~$35 |
| Container App (gateway) | 1 vCPU, 2GB | ~$35 |
| Container App (ollama) | 2 vCPU, 8GB | ~$100 |
| PostgreSQL | B1ms | ~$25 |
| Storage | Standard LRS | ~$5 |
| Key Vault | Standard | ~$1 |
| **Total** | | **~$200/month** |

Production costs scale with replicas and PostgreSQL tier.

## Security Checklist

- [ ] Change default admin password
- [ ] API keys in Key Vault (not in env files or code)
- [ ] PostgreSQL SSL enforced (`sslmode=require`)
- [ ] Container Apps ingress: web=external, gateway=internal, ollama=internal
- [ ] WAF enabled on Application Gateway (prod)
- [ ] Azure AD integration for admin access (future)
- [ ] Network Security Group restricts DB access to Container App subnet
- [ ] Automatic OS patching on container images
- [ ] Log Analytics workspace for audit trail
