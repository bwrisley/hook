#!/bin/bash
# slack-notify.sh — Post a message to Slack from HOOK scripts
# Usage: ./scripts/lib/slack-notify.sh "#hook" "message text"
#    or: echo "message" | ./scripts/lib/slack-notify.sh "#hook"
#
# Reads SLACK_BOT_TOKEN from environment or ~/.openclaw/openclaw.json

set -uo pipefail

CHANNEL="${1:?Usage: slack-notify.sh <channel> [message]}"
MESSAGE="${2:-}"

# Read from stdin if no message argument
if [ -z "$MESSAGE" ]; then
    MESSAGE=$(cat)
fi

if [ -z "$MESSAGE" ]; then
    echo "Error: no message provided" >&2
    exit 1
fi

# Get bot token from env or config
TOKEN="${SLACK_BOT_TOKEN:-}"
if [ -z "$TOKEN" ]; then
    CONFIG="$HOME/.openclaw/openclaw.json"
    if [ -f "$CONFIG" ]; then
        TOKEN=$(python3 -c "import json; print(json.load(open('$CONFIG')).get('channels',{}).get('slack',{}).get('botToken',''))" 2>/dev/null || true)
    fi
fi

if [ -z "$TOKEN" ] || [[ "$TOKEN" == xoxb-YOUR* ]]; then
    echo "Error: no Slack bot token found (set SLACK_BOT_TOKEN or configure openclaw.json)" >&2
    exit 1
fi

# Build JSON payload safely via python (avoids shell interpolation issues)
PAYLOAD=$(HOOK_SLACK_CHANNEL="$CHANNEL" HOOK_SLACK_MESSAGE="$MESSAGE" python3 -c "
import json, os
msg = os.environ['HOOK_SLACK_MESSAGE']
if len(msg) > 39000:
    msg = msg[:39000] + '\n\n_[truncated — full report in data/reports/]_'
print(json.dumps({'channel': os.environ['HOOK_SLACK_CHANNEL'], 'text': msg, 'mrkdwn': True}))
")

# Post to Slack
RESPONSE=$(curl -s -X POST "https://slack.com/api/chat.postMessage" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    --max-time 10 \
    -d "$PAYLOAD")

# Check response
OK=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ok',False))" 2>/dev/null || true)
if [ "$OK" = "True" ]; then
    echo "Posted to $CHANNEL"
else
    ERROR=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('error','unknown'))" 2>/dev/null || true)
    echo "Slack post failed: $ERROR" >&2
    exit 1
fi
