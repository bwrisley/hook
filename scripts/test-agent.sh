#!/bin/bash
# scripts/test-agent.sh -- Quick agent test helper
# Usage: ./scripts/test-agent.sh <agent-id> "message"
set -euo pipefail

AGENT="${1:?Usage: test-agent.sh <agent-id> \"message\"}"
MESSAGE="${2:?Usage: test-agent.sh <agent-id> \"message\"}"
TIMEOUT="${3:-180}"
OUTFILE="/tmp/hook-result.json"

echo "[Shadowbox] Sending to ${AGENT}..."
openclaw agent --agent "$AGENT" --message "$MESSAGE" --timeout "$TIMEOUT" --json > "$OUTFILE"

echo ""
python3 -c "
import json
d = json.load(open('$OUTFILE'))
text = d['result']['payloads'][0]['text']
print(text)
"
