#!/bin/bash
# deploy/azure-setup.sh — Create Azure infrastructure for Shadowbox
#
# Prerequisites:
#   - Azure CLI installed and logged in (az login)
#   - Subscription selected (az account set --subscription <id>)
#
# Usage:
#   ./deploy/azure-setup.sh dev    # Create dev environment
#   ./deploy/azure-setup.sh prod   # Create prod environment
#
set -euo pipefail

ENV="${1:?Usage: azure-setup.sh <dev|prod>}"
REGION="eastus"
BASE_NAME="shadowbox"

if [ "$ENV" = "prod" ]; then
    RG="${BASE_NAME}-prod"
    DB_SKU="B_Standard_B2s"
    HOSTNAME="shadowbox.punchcyber.com"
    MIN_REPLICAS=1
    MAX_REPLICAS=5
else
    RG="${BASE_NAME}-dev"
    DB_SKU="B_Standard_B1ms"
    HOSTNAME="dev-shadowbox.punchcyber.com"
    MIN_REPLICAS=0
    MAX_REPLICAS=2
fi

echo "=== Creating Shadowbox $ENV environment ==="
echo "  Resource Group: $RG"
echo "  Region: $REGION"
echo "  Hostname: $HOSTNAME"
echo ""

# ── 1. Resource Group ──────────────────────────────────────────
echo "[1/8] Creating resource group..."
az group create --name "$RG" --location "$REGION" --output none

# ── 2. Container App Environment ───────────────────────────────
echo "[2/8] Creating Container App Environment..."
az containerapp env create \
    --name "${BASE_NAME}-env" \
    --resource-group "$RG" \
    --location "$REGION" \
    --output none

# ── 3. PostgreSQL ──────────────────────────────────────────────
echo "[3/8] Creating PostgreSQL server..."
DB_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
az postgres flexible-server create \
    --name "${BASE_NAME}-db-${ENV}" \
    --resource-group "$RG" \
    --location "$REGION" \
    --sku-name "$DB_SKU" \
    --admin-user shadowbox \
    --admin-password "$DB_PASS" \
    --database-name shadowbox \
    --tier Burstable \
    --storage-size 32 \
    --public-access 0.0.0.0 \
    --output none

DB_HOST="${BASE_NAME}-db-${ENV}.postgres.database.azure.com"
DB_URL="postgresql://shadowbox:${DB_PASS}@${DB_HOST}:5432/shadowbox?sslmode=require"
echo "  DB Host: $DB_HOST"

# ── 4. Key Vault ──────────────────────────────────────────────
echo "[4/8] Creating Key Vault..."
az keyvault create \
    --name "${BASE_NAME}-kv-${ENV}" \
    --resource-group "$RG" \
    --location "$REGION" \
    --output none

# Store secrets
echo "  Storing secrets in Key Vault..."
az keyvault secret set --vault-name "${BASE_NAME}-kv-${ENV}" --name "database-url" --value "$DB_URL" --output none
az keyvault secret set --vault-name "${BASE_NAME}-kv-${ENV}" --name "db-password" --value "$DB_PASS" --output none

echo ""
echo "=== IMPORTANT: Add your API keys to Key Vault ==="
echo "  az keyvault secret set --vault-name ${BASE_NAME}-kv-${ENV} --name openai-api-key --value <key>"
echo "  az keyvault secret set --vault-name ${BASE_NAME}-kv-${ENV} --name vt-api-key --value <key>"
echo "  az keyvault secret set --vault-name ${BASE_NAME}-kv-${ENV} --name censys-api-id --value <key>"
echo "  az keyvault secret set --vault-name ${BASE_NAME}-kv-${ENV} --name censys-api-secret --value <key>"
echo "  az keyvault secret set --vault-name ${BASE_NAME}-kv-${ENV} --name abuseipdb-api-key --value <key>"
echo "  az keyvault secret set --vault-name ${BASE_NAME}-kv-${ENV} --name otx-api-key --value <key>"
echo "  az keyvault secret set --vault-name ${BASE_NAME}-kv-${ENV} --name shodan-api-key --value <key>"
echo ""

# ── 5. Storage Account ────────────────────────────────────────
echo "[5/8] Creating Storage Account..."
STORAGE_NAME="${BASE_NAME}storage${ENV}"
az storage account create \
    --name "$STORAGE_NAME" \
    --resource-group "$RG" \
    --location "$REGION" \
    --sku Standard_LRS \
    --output none

az storage container create --name feeds --account-name "$STORAGE_NAME" --output none
az storage container create --name cache --account-name "$STORAGE_NAME" --output none
az storage container create --name faiss --account-name "$STORAGE_NAME" --output none

# ── 6. Deploy Ollama Container ─────────────────────────────────
echo "[6/8] Deploying Ollama..."
az containerapp create \
    --name "${BASE_NAME}-ollama" \
    --resource-group "$RG" \
    --environment "${BASE_NAME}-env" \
    --image ollama/ollama:latest \
    --cpu 2 --memory 8Gi \
    --min-replicas 1 --max-replicas 1 \
    --ingress internal --target-port 11434 \
    --output none

# ── 7. Deploy Gateway Container ───────────────────────────────
echo "[7/8] Deploying Gateway..."
az containerapp create \
    --name "${BASE_NAME}-gateway" \
    --resource-group "$RG" \
    --environment "${BASE_NAME}-env" \
    --image ghcr.io/bwrisley/hook/shadowbox-gateway:${ENV} \
    --cpu 1 --memory 2Gi \
    --min-replicas "$MIN_REPLICAS" --max-replicas "$MAX_REPLICAS" \
    --ingress internal --target-port 18789 \
    --env-vars "HOOK_DIR=/app" \
    --output none

# ── 8. Deploy Web Container ───────────────────────────────────
echo "[8/8] Deploying Web..."
az containerapp create \
    --name "${BASE_NAME}-web" \
    --resource-group "$RG" \
    --environment "${BASE_NAME}-env" \
    --image ghcr.io/bwrisley/hook/shadowbox-web:${ENV} \
    --cpu 1 --memory 2Gi \
    --min-replicas "$MIN_REPLICAS" --max-replicas "$MAX_REPLICAS" \
    --ingress external --target-port 7799 \
    --env-vars \
        "HOOK_DIR=/app" \
        "DATABASE_URL=secretref:database-url" \
        "OLLAMA_BASE_URL=http://${BASE_NAME}-ollama:11434" \
        "HOOK_GATEWAY_URL=http://${BASE_NAME}-gateway:18789" \
    --output none

# Get the web URL
WEB_URL=$(az containerapp show --name "${BASE_NAME}-web" --resource-group "$RG" --query "properties.configuration.ingress.fqdn" -o tsv)

echo ""
echo "=== Deployment Complete ==="
echo "  Web URL: https://${WEB_URL}"
echo "  Target:  https://${HOSTNAME}"
echo ""
echo "=== Next Steps ==="
echo "  1. Add API keys to Key Vault (commands above)"
echo "  2. Pull Ollama models:"
echo "     az containerapp exec --name ${BASE_NAME}-ollama --resource-group $RG --command 'ollama pull nomic-embed-text'"
echo "     az containerapp exec --name ${BASE_NAME}-ollama --resource-group $RG --command 'ollama pull qwen2.5:14b'"
echo "  3. Configure DNS: CNAME ${HOSTNAME} -> ${WEB_URL}"
echo "  4. Add custom domain + SSL in Azure Portal"
echo "  5. Login: admin / shadowbox (change immediately)"
echo ""
echo "  DB Password saved to Key Vault: ${BASE_NAME}-kv-${ENV}"
