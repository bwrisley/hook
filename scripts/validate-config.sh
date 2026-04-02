#!/bin/bash
# validate-config.sh — Compare live openclaw.json against the template
# Detects: structural drift, missing keys, unexpected keys, placeholder remnants,
#          channel mismatches, workspace path issues
#
# Usage: ./scripts/validate-config.sh
#        ./scripts/validate-config.sh --fix    (apply safe fixes)

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$HOOK_DIR/config/openclaw.json.template"
CONFIG_FILE="${OPENCLAW_CONFIG:-$HOME/.openclaw/openclaw.json}"
FIX_MODE="${1:-}"

PASS=0
WARN=0
FAIL=0
FIXES=0

pass() { echo "  [PASS] $1"; PASS=$((PASS + 1)); }
warn() { echo "  [WARN] $1"; WARN=$((WARN + 1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL + 1)); }
info() { echo "  [INFO] $1"; }

echo ""
echo "HOOK Config Validation"
echo "  $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "  Template: $TEMPLATE"
echo "  Live:     $CONFIG_FILE"
echo ""

# ── Prerequisite checks ──────────────────────────────────────────────

if [ ! -f "$TEMPLATE" ]; then
    fail "Template not found: $TEMPLATE"
    echo "  Cannot continue without template."
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    fail "Live config not found: $CONFIG_FILE"
    echo "  Run ./install/setup.sh first."
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    fail "python3 required for JSON comparison"
    exit 1
fi

# ── 1. JSON Validity ──────────────────────────────────────────────────

echo "1. JSON Validity"

if python3 -c "import json; json.load(open('$TEMPLATE'))" 2>/dev/null; then
    pass "Template is valid JSON"
else
    fail "Template has JSON syntax errors"
fi

if python3 -c "import json; json.load(open('$CONFIG_FILE'))" 2>/dev/null; then
    pass "Live config is valid JSON"
else
    fail "Live config has JSON syntax errors — fix before continuing"
    exit 1
fi
echo ""

# ── 2. Placeholder Remnants ───────────────────────────────────────────

echo "2. Placeholder Check"

PLACEHOLDERS=$(grep -c "YOUR_\|HOOK_REPO_PATH\|HOOK_CHANNEL_NAME" "$CONFIG_FILE" 2>/dev/null || true)
if [ "$PLACEHOLDERS" -eq 0 ]; then
    pass "No unreplaced placeholders in live config"
else
    fail "$PLACEHOLDERS unreplaced placeholder(s):"
    grep -n "YOUR_\|HOOK_REPO_PATH\|HOOK_CHANNEL_NAME" "$CONFIG_FILE" | while read -r line; do
        echo "       $line"
    done
fi
echo ""

# ── 3. Structural Comparison ─────────────────────────────────────────

echo "3. Structure Comparison"

python3 - "$TEMPLATE" "$CONFIG_FILE" "$FIX_MODE" <<'PYEOF'
import json, sys

template_path = sys.argv[1]
config_path = sys.argv[2]
fix_mode = sys.argv[3] if len(sys.argv) > 3 else ""

with open(template_path) as f:
    template = json.load(f)
with open(config_path) as f:
    config = json.load(f)

pass_count = 0
warn_count = 0
fail_count = 0

def compare_keys(tmpl, conf, path=""):
    """Recursively compare top-level structure keys."""
    global pass_count, warn_count, fail_count
    
    if not isinstance(tmpl, dict) or not isinstance(conf, dict):
        return
    
    # Known placeholder keys — these intentionally differ between template and live
    PLACEHOLDER_KEYS = {"HOOK_CHANNEL_NAME"}
    
    for key in tmpl:
        full_path = f"{path}.{key}" if path else key
        if key in PLACEHOLDER_KEYS:
            continue
        if key not in conf:
            # Skip known replaceable fields
            if key in ("botToken", "appToken") and any(k.startswith("xo") for k in [conf.get("botToken", ""), conf.get("appToken", "")] if isinstance(k, str)):
                continue
            print(f"  [WARN] Missing key in live config: {full_path}")
            warn_count += 1
        else:
            if isinstance(tmpl[key], dict) and isinstance(conf[key], dict):
                compare_keys(tmpl[key], conf[key], full_path)
    
    for key in conf:
        full_path = f"{path}.{key}" if path else key
        if key not in tmpl and key not in PLACEHOLDER_KEYS:
            print(f"  [WARN] Extra key in live config (not in template): {full_path}")
            warn_count += 1

compare_keys(template, config)

if pass_count + warn_count + fail_count == 0:
    print("  [PASS] Live config structure matches template")
else:
    if warn_count > 0:
        print(f"  [INFO] {warn_count} structural difference(s) found")
PYEOF
echo ""

# ── 4. Agent Configuration ───────────────────────────────────────────

echo "4. Agent Configuration"

python3 - "$CONFIG_FILE" <<'PYEOF'
import json, sys

with open(sys.argv[1]) as f:
    config = json.load(f)

agents = config.get("agents", {}).get("list", [])
expected = ["coordinator", "triage-analyst", "osint-researcher", "incident-responder", "threat-intel", "report-writer"]
found = [a.get("id") for a in agents]

for agent_id in expected:
    if agent_id in found:
        agent = next(a for a in agents if a.get("id") == agent_id)
        model = agent.get("model", {}).get("primary", "default")
        workspace = agent.get("workspace", "not set")
        
        # Check workspace path exists (basic check for placeholders)
        if "HOOK_REPO_PATH" in workspace:
            print(f"  [FAIL] {agent_id}: workspace still has placeholder ({workspace})")
        else:
            print(f"  [PASS] {agent_id}: model={model}, workspace=.../{agent_id}/")
    else:
        print(f"  [FAIL] {agent_id}: missing from config")

# Check coordinator is default
coord = next((a for a in agents if a.get("id") == "coordinator"), None)
if coord and coord.get("default") is True:
    print("  [PASS] coordinator is default agent")
else:
    print("  [FAIL] coordinator is not set as default")

# Check subagent allowlist
if coord:
    allowed = coord.get("subagents", {}).get("allowAgents", [])
    expected_subs = ["triage-analyst", "osint-researcher", "incident-responder", "threat-intel", "report-writer"]
    missing_subs = [s for s in expected_subs if s not in allowed]
    extra_subs = [s for s in allowed if s not in expected_subs]
    if not missing_subs and not extra_subs:
        print(f"  [PASS] coordinator allowAgents matches expected ({len(allowed)} agents)")
    else:
        if missing_subs:
            print(f"  [FAIL] coordinator missing from allowAgents: {', '.join(missing_subs)}")
        if extra_subs:
            print(f"  [WARN] coordinator has extra allowAgents: {', '.join(extra_subs)}")
PYEOF
echo ""

# ── 5. Workspace Path Validation ─────────────────────────────────────

echo "5. Workspace Paths"

python3 - "$CONFIG_FILE" <<'PYEOF'
import json, sys, os

with open(sys.argv[1]) as f:
    config = json.load(f)

agents = config.get("agents", {}).get("list", [])
for agent in agents:
    agent_id = agent.get("id", "unknown")
    workspace = agent.get("workspace", "")
    expanded = os.path.expanduser(workspace)
    
    if not workspace:
        print(f"  [WARN] {agent_id}: no workspace configured")
    elif not os.path.isdir(expanded):
        print(f"  [FAIL] {agent_id}: workspace does not exist: {expanded}")
    elif not os.path.isfile(os.path.join(expanded, "SOUL.md")):
        print(f"  [FAIL] {agent_id}: workspace missing SOUL.md")
    elif not os.path.isfile(os.path.join(expanded, "TOOLS.md")):
        print(f"  [FAIL] {agent_id}: workspace missing TOOLS.md")
    else:
        print(f"  [PASS] {agent_id}: {expanded}")
PYEOF
echo ""

# ── 6. Channel Configuration ─────────────────────────────────────────

echo "6. Slack Channel Configuration"

python3 - "$CONFIG_FILE" <<'PYEOF'
import json, sys, os

with open(sys.argv[1]) as f:
    config = json.load(f)

slack = config.get("channels", {}).get("slack", {})

# Check mode
mode = slack.get("mode", "not set")
if mode == "socket":
    print(f"  [PASS] Socket Mode enabled")
else:
    print(f"  [WARN] Mode is '{mode}', expected 'socket'")

# Check channels
channels = slack.get("channels", {})
if not channels:
    print(f"  [FAIL] No channels configured in channels.slack.channels")
else:
    for ch_name, ch_config in channels.items():
        allowed = ch_config.get("allow", False)
        status = "allowed" if allowed else "not allowed"
        print(f"  [PASS] Channel: {ch_name} ({status})")

# Check for HOOK_CHANNEL_NAME placeholder
raw = open(sys.argv[1]).read()
if "HOOK_CHANNEL_NAME" in raw:
    print(f"  [FAIL] Channel placeholder HOOK_CHANNEL_NAME not replaced")

# Check env var alignment
env_channel = os.environ.get("HOOK_SLACK_CHANNEL", "#hook")
config_channels = list(channels.keys())
if config_channels and env_channel not in config_channels:
    print(f"  [WARN] HOOK_SLACK_CHANNEL env var ({env_channel}) does not match config channel(s): {', '.join(config_channels)}")
    print(f"         Scripts use HOOK_SLACK_CHANNEL for Slack notifications")
    print(f"         Ensure config channel matches or set the env var")
PYEOF
echo ""

# ── 7. Binding Check ──────────────────────────────────────────────────

echo "7. Bindings"

python3 - "$CONFIG_FILE" <<'PYEOF'
import json, sys

with open(sys.argv[1]) as f:
    config = json.load(f)

bindings = config.get("bindings", [])
if not bindings:
    print("  [FAIL] No bindings configured — Slack messages won't reach agents")
else:
    for b in bindings:
        agent = b.get("agentId", "unknown")
        match = b.get("match", {})
        channel = match.get("channel", "any")
        print(f"  [PASS] {agent} bound to channel: {channel}")
    
    coord_bound = any(b.get("agentId") == "coordinator" for b in bindings)
    if coord_bound:
        print("  [PASS] coordinator is bound (required for routing)")
    else:
        print("  [FAIL] coordinator is not bound — all messages will bypass routing")
PYEOF
echo ""

# ── 8. Known Schema Pitfalls ──────────────────────────────────────────

echo "8. OpenClaw Schema Pitfalls"

python3 - "$CONFIG_FILE" <<'PYEOF'
import json, sys

with open(sys.argv[1]) as f:
    config = json.load(f)
    raw = open(sys.argv[1]).read()

# Known invalid keys that OpenClaw rejects
INVALID_KEYS = {
    "auth": "root level",
    "compaction": "root level",
    "description": "agent level",
}

issues = 0

# Check root level
for key in ["auth", "compaction", "description"]:
    if key in config:
        print(f"  [FAIL] Invalid root key '{key}' — OpenClaw will reject this")
        issues += 1

# Check agent level
for agent in config.get("agents", {}).get("list", []):
    agent_id = agent.get("id", "unknown")
    for key in ["description", "auth"]:
        if key in agent:
            print(f"  [FAIL] Invalid key '{key}' in agent '{agent_id}' — OpenClaw will reject")
            issues += 1

# Check for known invalid patterns
if isinstance(config.get("gateway", {}).get("controlUi"), bool):
    print(f"  [FAIL] gateway.controlUi must be an object, not a boolean")
    issues += 1

if "streaming" in config.get("channels", {}).get("slack", {}):
    print(f"  [FAIL] channels.slack.streaming is invalid — use 'nativeStreaming' instead")
    issues += 1

if config.get("channels", {}).get("slack", {}).get("streaming") is not None:
    pass  # already caught above

# Check tools.lobster (invalid)
if "lobster" in config.get("tools", {}):
    print(f"  [FAIL] tools.lobster is invalid — Lobster is configured via CLI, not openclaw.json")
    issues += 1

# Check session.dmScope (invalid)
if "dmScope" in config.get("session", {}):
    print(f"  [FAIL] session.dmScope is invalid — remove it")
    issues += 1

if issues == 0:
    print("  [PASS] No known schema violations detected")
PYEOF
echo ""

# ── Summary ───────────────────────────────────────────────────────────

echo "--- Summary ---"
echo ""
echo "  Config validation complete. Review any [FAIL] or [WARN] items above."
echo "  Template: $TEMPLATE"
echo "  Live:     $CONFIG_FILE"
echo ""
