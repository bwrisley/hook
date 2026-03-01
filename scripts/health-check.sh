#!/bin/bash
# health-check.sh — Validate the entire HOOK environment
# Usage: ./scripts/health-check.sh
# Run this after setup or when something isn't working.

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_FILE="$HOME/.openclaw/openclaw.json"
PASS=0
WARN=0
FAIL=0

pass() { echo "  ✅ $1"; PASS=$((PASS + 1)); }
warn() { echo "  ⚠️  $1"; WARN=$((WARN + 1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL + 1)); }

echo ""
echo "🪝 HOOK Health Check"
echo "   $(date -u '+%Y-%m-%d %H:%M UTC')"
echo ""

# ─── 1. Core Dependencies ───────────────────────────────────────────

echo "1. Core Dependencies"

command -v openclaw >/dev/null 2>&1 && pass "OpenClaw $(openclaw --version 2>/dev/null | head -1 || echo 'installed')" || fail "OpenClaw not installed (npm install -g @openclaw/openclaw)"
command -v node >/dev/null 2>&1 && pass "Node.js $(node --version)" || fail "Node.js not installed (brew install node)"
command -v python3 >/dev/null 2>&1 && pass "Python3 $(python3 --version 2>&1 | awk '{print $2}')" || fail "Python3 not installed"
command -v git >/dev/null 2>&1 && pass "Git $(git --version | awk '{print $3}')" || fail "Git not installed"
command -v curl >/dev/null 2>&1 && pass "curl installed" || fail "curl not installed"
echo ""

# ─── 2. Security Tools ──────────────────────────────────────────────

echo "2. Security Tools"

command -v jq >/dev/null 2>&1 && pass "jq $(jq --version 2>/dev/null)" || fail "jq not installed (brew install jq)"
command -v dig >/dev/null 2>&1 && pass "dig installed" || fail "dig not installed (brew install bind)"
command -v nmap >/dev/null 2>&1 && pass "nmap $(nmap --version 2>&1 | head -1 | awk '{print $3}')" || warn "nmap not installed (brew install nmap) — IR agent limited"
command -v whois >/dev/null 2>&1 && pass "whois installed" || warn "whois not installed (brew install whois) — OSINT agent limited"
command -v lobster >/dev/null 2>&1 && pass "Lobster CLI installed" || warn "Lobster not installed (optional — npm install -g @openclaw/lobster)"
echo ""

# ─── 3. Repository Structure ────────────────────────────────────────

echo "3. Repository ($HOOK_DIR)"

[ -d "$HOOK_DIR/workspaces" ] && pass "workspaces/ exists" || fail "workspaces/ missing"
[ -d "$HOOK_DIR/pipelines" ] && pass "pipelines/ exists" || fail "pipelines/ missing"
[ -d "$HOOK_DIR/scripts" ] && pass "scripts/ exists" || fail "scripts/ missing"

AGENT_COUNT=0
for agent in coordinator triage-analyst osint-researcher incident-responder threat-intel report-writer; do
    if [ -f "$HOOK_DIR/workspaces/$agent/SOUL.md" ] && [ -f "$HOOK_DIR/workspaces/$agent/TOOLS.md" ]; then
        AGENT_COUNT=$((AGENT_COUNT + 1))
    else
        fail "Workspace incomplete: $agent (needs SOUL.md + TOOLS.md)"
    fi
done
[ "$AGENT_COUNT" -eq 6 ] && pass "All 6 agent workspaces complete" || warn "Only $AGENT_COUNT/6 agent workspaces complete"

# Check scripts are executable
EXEC_COUNT=0
for script in enrich-ip.sh enrich-domain.sh enrich-hash.sh enrich-batch.sh extract-iocs.sh format-report.sh; do
    if [ -x "$HOOK_DIR/scripts/$script" ]; then
        EXEC_COUNT=$((EXEC_COUNT + 1))
    else
        warn "Script not executable: scripts/$script (fix: chmod +x scripts/$script)"
    fi
done
[ "$EXEC_COUNT" -eq 6 ] && pass "All 6 scripts executable" || true

[ -f "$HOOK_DIR/scripts/lib/common.py" ] && pass "Shared library scripts/lib/common.py exists" || fail "Missing scripts/lib/common.py"
echo ""

# ─── 4. Configuration ───────────────────────────────────────────────

echo "4. Configuration ($CONFIG_FILE)"

if [ ! -f "$CONFIG_FILE" ]; then
    fail "Config file not found at $CONFIG_FILE"
    echo "     Fix: ./install/setup.sh"
else
    pass "Config file exists"

    # Valid JSON
    if python3 -c "import json; json.load(open('$CONFIG_FILE'))" 2>/dev/null; then
        pass "Valid JSON"
    else
        fail "Config has JSON syntax errors"
    fi

    # Placeholders
    PLACEHOLDERS=$(grep -c "YOUR_\|HOOK_REPO_PATH" "$CONFIG_FILE" 2>/dev/null || true)
    if [ "$PLACEHOLDERS" -eq 0 ]; then
        pass "No unreplaced placeholders"
    else
        fail "$PLACEHOLDERS placeholder(s) still present"
        grep "YOUR_\|HOOK_REPO_PATH" "$CONFIG_FILE" | head -5 | sed 's/^/     /'
    fi

    # API keys present (check they're not empty)
    for key in VT_API_KEY CENSYS_API_ID CENSYS_API_SECRET ABUSEIPDB_API_KEY; do
        VAL=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('env',{}).get('$key',''))" 2>/dev/null)
        if [ -n "$VAL" ] && [[ "$VAL" != YOUR_* ]]; then
            pass "$key configured"
        else
            warn "$key missing or placeholder"
        fi
    done

    # Slack tokens
    BOT_TOKEN=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('channels',{}).get('slack',{}).get('botToken',''))" 2>/dev/null)
    APP_TOKEN=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('channels',{}).get('slack',{}).get('appToken',''))" 2>/dev/null)
    [[ "$BOT_TOKEN" == xoxb-* ]] && [[ "$BOT_TOKEN" != *YOUR* ]] && pass "Slack botToken configured" || warn "Slack botToken missing or placeholder"
    [[ "$APP_TOKEN" == xapp-* ]] && [[ "$APP_TOKEN" != *YOUR* ]] && pass "Slack appToken configured" || warn "Slack appToken missing or placeholder"

    # Agent count in config
    CONF_AGENTS=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(len(c.get('agents',{}).get('list',[])))" 2>/dev/null)
    [ "$CONF_AGENTS" -eq 6 ] && pass "6 agents in config" || warn "Expected 6 agents in config, found $CONF_AGENTS"
fi
echo ""

# ─── 5. Gateway Status ──────────────────────────────────────────────

echo "5. Gateway"

if command -v openclaw >/dev/null 2>&1; then
    GW_STATUS=$(openclaw gateway status 2>&1 || true)
    if echo "$GW_STATUS" | grep -qi "running\|active"; then
        pass "Gateway is running"
    else
        warn "Gateway may not be running (openclaw gateway start)"
    fi
else
    warn "Cannot check gateway — OpenClaw not installed"
fi
echo ""

# ─── 6. API Connectivity ────────────────────────────────────────────

echo "6. API Connectivity (live checks, may take a moment)"

# VirusTotal
VT_KEY=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('env',{}).get('VT_API_KEY',''))" 2>/dev/null)
if [ -n "$VT_KEY" ] && [[ "$VT_KEY" != YOUR_* ]]; then
    VT_RESP=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" \
        "https://www.virustotal.com/api/v3/ip_addresses/8.8.8.8" \
        -H "x-apikey: $VT_KEY" 2>/dev/null)
    [ "$VT_RESP" = "200" ] && pass "VirusTotal API responding (HTTP $VT_RESP)" || fail "VirusTotal API error (HTTP $VT_RESP)"
else
    warn "VirusTotal API not tested — no key configured"
fi

# AbuseIPDB
ABUSE_KEY=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('env',{}).get('ABUSEIPDB_API_KEY',''))" 2>/dev/null)
if [ -n "$ABUSE_KEY" ] && [[ "$ABUSE_KEY" != YOUR_* ]]; then
    ABUSE_RESP=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" \
        -G "https://api.abuseipdb.com/api/v2/check" \
        -d "ipAddress=8.8.8.8" -d "maxAgeInDays=1" \
        -H "Key: $ABUSE_KEY" -H "Accept: application/json" 2>/dev/null)
    [ "$ABUSE_RESP" = "200" ] && pass "AbuseIPDB API responding (HTTP $ABUSE_RESP)" || fail "AbuseIPDB API error (HTTP $ABUSE_RESP)"
else
    warn "AbuseIPDB API not tested — no key configured"
fi

# Censys
CENSYS_ID=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('env',{}).get('CENSYS_API_ID',''))" 2>/dev/null)
CENSYS_SECRET=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('env',{}).get('CENSYS_API_SECRET',''))" 2>/dev/null)
if [ -n "$CENSYS_ID" ] && [[ "$CENSYS_ID" != YOUR_* ]]; then
    CENSYS_RESP=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" \
        -u "$CENSYS_ID:$CENSYS_SECRET" \
        "https://search.censys.io/api/v2/hosts/8.8.8.8" 2>/dev/null)
    [ "$CENSYS_RESP" = "200" ] && pass "Censys API responding (HTTP $CENSYS_RESP)" || fail "Censys API error (HTTP $CENSYS_RESP)"
else
    warn "Censys API not tested — no key configured"
fi
echo ""

# ─── 7. Log Directory ───────────────────────────────────────────────

echo "7. Logging"

LOG_DIR="${HOOK_LOG_DIR:-$HOME/.openclaw/logs/hook}"
if [ -d "$LOG_DIR" ]; then
    LOG_COUNT=$(ls -1 "$LOG_DIR"/enrichment-*.jsonl 2>/dev/null | wc -l | tr -d ' ')
    LATEST=$(ls -t "$LOG_DIR"/enrichment-*.jsonl 2>/dev/null | head -1)
    pass "Log directory exists ($LOG_DIR)"
    if [ -n "$LATEST" ]; then
        LINES=$(wc -l < "$LATEST" | tr -d ' ')
        pass "Latest log: $(basename "$LATEST") ($LINES entries)"
    fi
else
    warn "Log directory not yet created (will be created on first enrichment run)"
fi
echo ""

# ─── Summary ─────────────────────────────────────────────────────────

echo "─── Summary ────────────────────────────────────────────────────"
echo ""
TOTAL=$((PASS + WARN + FAIL))
echo "  ✅ $PASS passed  ⚠️  $WARN warnings  ❌ $FAIL failures  ($TOTAL checks)"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo "  Status: NOT READY — fix the failures above"
    exit 1
elif [ "$WARN" -gt 0 ]; then
    echo "  Status: READY (with limitations)"
    exit 0
else
    echo "  Status: FULLY OPERATIONAL"
    exit 0
fi
