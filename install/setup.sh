#!/bin/bash
# HOOK Setup Script — Automated installation for macOS
# Usage: cd ~/PROJECTS/hook && ./install/setup.sh
#
# This script automates file copy, placeholder replacement, and tool installation.
# Slack app setup and API key entry still require manual steps.

set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OPENCLAW_DIR="$HOME/.openclaw"
CONFIG_FILE="$OPENCLAW_DIR/openclaw.json"

echo ""
echo "🪝 HOOK Setup — Hunting, Orchestration & Operational Knowledge"
echo "   by PUNCH Cyber"
echo ""
echo "   HOOK repo:       $HOOK_DIR"
echo "   OpenClaw config: $OPENCLAW_DIR"
echo ""

# ─── Prerequisites ──────────────────────────────────────────────────

echo "Checking prerequisites..."
echo ""

MISSING=0

if ! command -v openclaw >/dev/null 2>&1; then
    echo "  ❌ OpenClaw not installed"
    echo "     Fix: npm install -g @openclaw/openclaw"
    MISSING=1
else
    echo "  ✅ OpenClaw $(openclaw --version 2>/dev/null | head -1 || echo 'installed')"
fi

if ! command -v git >/dev/null 2>&1; then
    echo "  ❌ Git not installed"
    echo "     Fix: brew install git"
    MISSING=1
else
    echo "  ✅ Git $(git --version | awk '{print $3}')"
fi

if ! command -v node >/dev/null 2>&1; then
    echo "  ❌ Node.js not installed"
    echo "     Fix: brew install node"
    MISSING=1
else
    echo "  ✅ Node.js $(node --version)"
fi

if ! command -v brew >/dev/null 2>&1; then
    echo "  ❌ Homebrew not installed"
    echo "     Fix: https://brew.sh"
    MISSING=1
else
    echo "  ✅ Homebrew $(brew --version | head -1 | awk '{print $2}')"
fi

if [ "$MISSING" -gt 0 ]; then
    echo ""
    echo "❌ Missing prerequisites. Install them and re-run this script."
    exit 1
fi

echo ""

# ─── Security Tools ─────────────────────────────────────────────────

echo "Checking security tools..."
echo ""

TOOLS_TO_INSTALL=""

if ! command -v jq >/dev/null 2>&1; then
    echo "  ⬜ jq — not installed"
    TOOLS_TO_INSTALL="$TOOLS_TO_INSTALL jq"
else
    echo "  ✅ jq $(jq --version 2>/dev/null)"
fi

if ! command -v dig >/dev/null 2>&1; then
    echo "  ⬜ dig — not installed"
    TOOLS_TO_INSTALL="$TOOLS_TO_INSTALL bind"
else
    echo "  ✅ dig $(dig -v 2>&1 | head -1)"
fi

if ! command -v nmap >/dev/null 2>&1; then
    echo "  ⬜ nmap — not installed"
    TOOLS_TO_INSTALL="$TOOLS_TO_INSTALL nmap"
else
    echo "  ✅ nmap $(nmap --version 2>&1 | head -1 | awk '{print $3}')"
fi

if ! command -v whois >/dev/null 2>&1; then
    echo "  ⬜ whois — not installed"
    TOOLS_TO_INSTALL="$TOOLS_TO_INSTALL whois"
else
    echo "  ✅ whois installed"
fi

if [ -n "$TOOLS_TO_INSTALL" ]; then
    echo ""
    read -rp "Install missing tools via brew? ($TOOLS_TO_INSTALL) [Y/n]: " INSTALL_TOOLS
    if [ "${INSTALL_TOOLS:-Y}" != "n" ] && [ "${INSTALL_TOOLS:-Y}" != "N" ]; then
        # shellcheck disable=SC2086
        brew install $TOOLS_TO_INSTALL
        echo "  ✅ Tools installed"
    else
        echo "  ⚠️  Skipped — some agents may not work correctly without these tools"
    fi
fi

echo ""

# ─── Make Scripts Executable ─────────────────────────────────────────

chmod +x "$HOOK_DIR/scripts/"*.sh 2>/dev/null || true
chmod +x "$HOOK_DIR/config/build.sh" 2>/dev/null || true
echo "✅ Scripts marked executable"

# ─── Config Setup ───────────────────────────────────────────────────

echo ""

# Backup existing config
if [ -f "$CONFIG_FILE" ]; then
    BACKUP="$CONFIG_FILE.backup.$(date +%Y%m%d-%H%M%S)"
    cp "$CONFIG_FILE" "$BACKUP"
    echo "📦 Backed up existing config to:"
    echo "   $BACKUP"
fi

# Copy template
cp "$HOOK_DIR/config/openclaw.json.template" "$CONFIG_FILE"
echo "📋 Copied config template"

# Replace HOOK_REPO_PATH
sed -i '' "s|HOOK_REPO_PATH|$HOOK_DIR|g" "$CONFIG_FILE"
echo "🔧 Set workspace paths to $HOOK_DIR"

# Prompt for API keys
echo ""
echo "─── API Keys ───────────────────────────────────────────────────"
echo "Enter your API keys (leave blank to skip and edit later):"
echo ""

read -rp "  VirusTotal API Key: " VT_KEY
if [ -n "$VT_KEY" ]; then
    sed -i '' "s|YOUR_VIRUSTOTAL_API_KEY|$VT_KEY|g" "$CONFIG_FILE"
    echo "    ✅ Set"
fi

read -rp "  Censys API ID: " CENSYS_ID
if [ -n "$CENSYS_ID" ]; then
    sed -i '' "s|YOUR_CENSYS_API_ID|$CENSYS_ID|g" "$CONFIG_FILE"
    echo "    ✅ Set"
fi

read -rp "  Censys API Secret: " CENSYS_SECRET
if [ -n "$CENSYS_SECRET" ]; then
    sed -i '' "s|YOUR_CENSYS_API_SECRET|$CENSYS_SECRET|g" "$CONFIG_FILE"
    echo "    ✅ Set"
fi

read -rp "  AbuseIPDB API Key: " ABUSE_KEY
if [ -n "$ABUSE_KEY" ]; then
    sed -i '' "s|YOUR_ABUSEIPDB_API_KEY|$ABUSE_KEY|g" "$CONFIG_FILE"
    echo "    ✅ Set"
fi

# ─── Validation ──────────────────────────────────────────────────────

echo ""
echo "─── Validation ─────────────────────────────────────────────────"

# Check for remaining placeholders
REMAINING=$(grep -c "YOUR_\|HOOK_REPO_PATH" "$CONFIG_FILE" 2>/dev/null || true)
if [ "$REMAINING" -gt 0 ]; then
    echo ""
    echo "  ⚠️  $REMAINING placeholder(s) still need to be replaced:"
    grep -n "YOUR_\|HOOK_REPO_PATH" "$CONFIG_FILE" | sed 's/^/     /'
else
    echo "  ✅ All API key placeholders replaced"
fi

# Check Slack tokens
SLACK_REMAINING=$(grep -c "xoxb-YOUR\|xapp-YOUR" "$CONFIG_FILE" 2>/dev/null || true)
if [ "$SLACK_REMAINING" -gt 0 ]; then
    echo "  ⚠️  Slack tokens still need to be configured (see Step 5 in INSTALL.md)"
else
    echo "  ✅ Slack tokens configured"
fi

# Validate JSON
if command -v python3 >/dev/null 2>&1; then
    if python3 -c "import json; json.load(open('$CONFIG_FILE'))" 2>/dev/null; then
        echo "  ✅ Config is valid JSON"
    else
        echo "  ❌ Config has JSON syntax errors — edit $CONFIG_FILE and fix"
    fi
fi

# Check agent workspaces exist
AGENT_COUNT=0
for agent in coordinator triage-analyst osint-researcher incident-responder threat-intel report-writer; do
    if [ -d "$HOOK_DIR/workspaces/$agent" ] && [ -f "$HOOK_DIR/workspaces/$agent/SOUL.md" ]; then
        AGENT_COUNT=$((AGENT_COUNT + 1))
    else
        echo "  ❌ Missing workspace: $agent"
    fi
done
echo "  ✅ $AGENT_COUNT/6 agent workspaces found"

# Check Lobster
if command -v lobster >/dev/null 2>&1; then
    echo "  ✅ Lobster CLI installed (deterministic pipelines available)"
else
    echo "  ℹ️  Lobster not installed (optional — run: npm install -g @openclaw/lobster)"
fi

# ─── Done ────────────────────────────────────────────────────────────

echo ""
echo "─── Next Steps ─────────────────────────────────────────────────"
echo ""
if [ "$SLACK_REMAINING" -gt 0 ]; then
    echo "  1. Create Slack app and add tokens to $CONFIG_FILE"
    echo "     (see Step 5 in $HOOK_DIR/install/INSTALL.md)"
    echo ""
    echo "  2. Start gateway:"
    echo "       openclaw gateway install"
    echo "       openclaw gateway start"
else
    echo "  1. Start gateway:"
    echo "       openclaw gateway install"
    echo "       openclaw gateway start"
fi
echo ""
echo "  Then verify:"
echo "       openclaw agents list --bindings"
echo "       openclaw channels status --probe"
echo ""
echo "  Test in Slack:"
echo "       @HOOK Hello, are you online?"
echo ""
echo "  Full guide: $HOOK_DIR/install/INSTALL.md"
echo ""
echo "🪝 HOOK setup complete!"
