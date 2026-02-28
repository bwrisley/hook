#!/bin/bash
# HOOK Setup Script — Automated installation for Mac Studio
# Usage: chmod +x install/setup.sh && ./install/setup.sh
#
# This script does NOT replace reading INSTALL.md — it automates the
# file copy and placeholder replacement steps. Slack setup and API key
# entry still require manual steps.

set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OPENCLAW_DIR="$HOME/.openclaw"
CONFIG_FILE="$OPENCLAW_DIR/openclaw.json"

echo "🪝 HOOK Setup — Hunting, Orchestration & Operational Knowledge"
echo "   by PUNCH Cyber"
echo ""
echo "HOOK repo: $HOOK_DIR"
echo "OpenClaw config: $OPENCLAW_DIR"
echo ""

# Check prerequisites
command -v openclaw >/dev/null 2>&1 || { echo "❌ OpenClaw not installed. Run: npm install -g @openclaw/openclaw"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "❌ Git not installed. Run: brew install git"; exit 1; }

echo "✅ Prerequisites checked"

# Backup existing config
if [ -f "$CONFIG_FILE" ]; then
    BACKUP="$CONFIG_FILE.backup.$(date +%Y%m%d-%H%M%S)"
    cp "$CONFIG_FILE" "$BACKUP"
    echo "📦 Backed up existing config to $BACKUP"
fi

# Copy template
cp "$HOOK_DIR/config/openclaw.json.template" "$CONFIG_FILE"
echo "📋 Copied config template"

# Replace HOOK_REPO_PATH
sed -i '' "s|HOOK_REPO_PATH|$HOOK_DIR|g" "$CONFIG_FILE"
echo "🔧 Set workspace paths to $HOOK_DIR"

# Prompt for API keys
echo ""
echo "Enter your API keys (leave blank to skip and edit later):"
echo ""

read -rp "VirusTotal API Key: " VT_KEY
if [ -n "$VT_KEY" ]; then
    sed -i '' "s|YOUR_VIRUSTOTAL_API_KEY|$VT_KEY|g" "$CONFIG_FILE"
    echo "  ✅ VT key set"
fi

read -rp "Censys API ID: " CENSYS_ID
if [ -n "$CENSYS_ID" ]; then
    sed -i '' "s|YOUR_CENSYS_API_ID|$CENSYS_ID|g" "$CONFIG_FILE"
    echo "  ✅ Censys ID set"
fi

read -rp "Censys API Secret: " CENSYS_SECRET
if [ -n "$CENSYS_SECRET" ]; then
    sed -i '' "s|YOUR_CENSYS_API_SECRET|$CENSYS_SECRET|g" "$CONFIG_FILE"
    echo "  ✅ Censys secret set"
fi

read -rp "AbuseIPDB API Key: " ABUSE_KEY
if [ -n "$ABUSE_KEY" ]; then
    sed -i '' "s|YOUR_ABUSEIPDB_API_KEY|$ABUSE_KEY|g" "$CONFIG_FILE"
    echo "  ✅ AbuseIPDB key set"
fi

echo ""
echo "Slack tokens must be configured manually:"
echo "  1. Create Slack app at https://api.slack.com/apps"
echo "  2. Follow the Slack setup steps in install/INSTALL.md"
echo "  3. Edit $CONFIG_FILE to add botToken and appToken"
echo ""

# Check for remaining placeholders
REMAINING=$(grep -c "YOUR_" "$CONFIG_FILE" 2>/dev/null || true)
if [ "$REMAINING" -gt 0 ]; then
    echo "⚠️  $REMAINING placeholder(s) still need to be replaced in $CONFIG_FILE"
    grep "YOUR_" "$CONFIG_FILE" | sed 's/^/   /'
else
    echo "✅ All placeholders replaced"
fi

echo ""
echo "🪝 HOOK setup complete!"
echo ""
echo "Next steps:"
echo "  1. Configure Slack app and add tokens to $CONFIG_FILE"
echo "  2. Start gateway: openclaw gateway start"
echo "  3. Verify agents: openclaw agents list --bindings"
echo "  4. Test in Slack: @HOOK Hello"
echo ""
echo "Full guide: $HOOK_DIR/install/INSTALL.md"
