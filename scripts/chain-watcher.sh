#!/bin/bash
# chain-watcher.sh — Auto-continue HOOK chains
#
# Watches #hook for subagent announce messages and posts "continue"
# when the coordinator doesn't respond.
#
# Usage:
#   ./scripts/chain-watcher.sh              # Run in foreground
#   ./scripts/chain-watcher.sh --daemon     # Run as background daemon
#   ./scripts/chain-watcher.sh --stop       # Stop the daemon
#   ./scripts/chain-watcher.sh --status     # Check if running

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_DIR="${HOOK_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
LOG_DIR="${HOOK_LOG_DIR:-$HOME/.openclaw/logs/hook}"
PID_FILE="$LOG_DIR/chain-watcher.pid"
LOG_FILE="$LOG_DIR/chain-watcher.log"
PROCESSED_FILE="$LOG_DIR/chain-watcher-processed.txt"

POLL_INTERVAL="${HOOK_WATCHER_POLL:-5}"
RESPONSE_WAIT="${HOOK_WATCHER_WAIT:-10}"
CHANNEL_ID="${HOOK_SLACK_CHANNEL_ID:-}"
DAEMON=false

mkdir -p "$LOG_DIR"
touch "$PROCESSED_FILE"

log() {
    local msg="[$(date -u '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" >> "$LOG_FILE"
    if [ "$DAEMON" = "false" ]; then
        echo "$msg"
    fi
}

get_token() {
    local token="${SLACK_BOT_TOKEN:-}"
    if [ -z "$token" ]; then
        local config="$HOME/.openclaw/openclaw.json"
        if [ -f "$config" ]; then
            token=$(python3 -c "
import json
with open('$config') as f:
    c = json.load(f)
# Try multiple possible locations for the token
t = c.get('channels',{}).get('slack',{}).get('botToken','')
if not t:
    t = c.get('env',{}).get('SLACK_BOT_TOKEN','')
print(t)
" 2>/dev/null || true)
        fi
    fi
    echo "$token"
}

setup() {
    local token
    token=$(get_token)
    if [ -z "$token" ]; then
        echo "ERROR: No Slack bot token found." >&2
        echo "Set SLACK_BOT_TOKEN env var or configure in openclaw.json" >&2
        exit 1
    fi
    log "Token found (${#token} chars)"

    if [ -z "$CHANNEL_ID" ]; then
        echo "ERROR: HOOK_SLACK_CHANNEL_ID not set." >&2
        echo "Export it: export HOOK_SLACK_CHANNEL_ID=C0AHNAL1370" >&2
        exit 1
    fi

    # Verify channel access
    local test_resp
    test_resp=$(curl -s -H "Authorization: Bearer $token" \
        "https://slack.com/api/conversations.history?channel=$CHANNEL_ID&limit=1" 2>/dev/null)

    if [ -z "$test_resp" ]; then
        echo "ERROR: Empty response from Slack API. Check network." >&2
        exit 1
    fi

    local ok
    ok=$(echo "$test_resp" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ok',False))" 2>/dev/null || echo "parse_error")

    if [ "$ok" != "True" ]; then
        local err
        err=$(echo "$test_resp" | python3 -c "import json,sys; print(json.load(sys.stdin).get('error','unknown'))" 2>/dev/null || echo "unknown")
        echo "ERROR: Cannot read channel $CHANNEL_ID: $err" >&2
        echo "The bot may need 'channels:history' and 'groups:history' scopes." >&2
        exit 1
    fi

    log "Channel access verified: $CHANNEL_ID"
}

watch_loop() {
    log "Chain watcher started (poll=${POLL_INTERVAL}s, wait=${RESPONSE_WAIT}s)"
    log "Monitoring channel: $CHANNEL_ID"

    local token
    token=$(get_token)

    while true; do
        # Fetch last 10 messages
        local resp
        resp=$(curl -s -H "Authorization: Bearer $token" \
            "https://slack.com/api/conversations.history?channel=$CHANNEL_ID&limit=25" 2>/dev/null)

        # Skip if empty or error
        if [ -z "$resp" ]; then
            sleep "$POLL_INTERVAL"
            continue
        fi

        # Process with python
        local action
        action=$(echo "$resp" | python3 -c "
import json, sys, time

try:
    data = json.load(sys.stdin)
except Exception:
    print('ERROR:bad_json')
    sys.exit(0)

if not data.get('ok'):
    print('ERROR:' + data.get('error', 'unknown'))
    sys.exit(0)

messages = data.get('messages', [])
if not messages:
    print('NONE')
    sys.exit(0)

# Load processed set
processed = set()
try:
    with open('$PROCESSED_FILE') as f:
        processed = set(line.strip() for line in f if line.strip())
except FileNotFoundError:
    pass

# Sort chronological (oldest first)
messages.sort(key=lambda m: float(m.get('ts', '0')))

now = time.time()
result = 'NONE'

for i, msg in enumerate(messages):
    ts = msg.get('ts', '')
    text = msg.get('text', '')

    # Skip already processed
    if ts in processed:
        continue

    # Detect announce: contains 'Subagent' and 'finished'
    if 'Subagent' not in text or 'finished' not in text:
        continue

    age = now - float(ts)

    # Too fresh — give coordinator time to respond
    if age < $RESPONSE_WAIT:
        continue

    # Check if coordinator already responded after this announce
    has_response = False
    for later in messages[i+1:]:
        later_ts = float(later.get('ts', '0'))
        if later_ts <= float(ts):
            continue
        later_text = later.get('text', '')
        # Any bot message that is NOT another announce counts as a response
        if later.get('bot_id') or later.get('app_id'):
            if 'Subagent' not in later_text or 'finished' not in later_text:
                has_response = True
                break
        # A user message saying 'continue' also counts
        if 'continue' in later_text.lower():
            has_response = True
            break

    # Mark as processed
    with open('$PROCESSED_FILE', 'a') as f:
        f.write(ts + '\n')

    if not has_response:
        # Extract agent name for logging
        agent = 'unknown'
        if 'Subagent ' in text:
            parts = text.split('Subagent ')[1].split(' ')
            agent = parts[0] if parts else 'unknown'
        print(f'CONTINUE:{agent}')
        sys.exit(0)

print(result)
" 2>/dev/null || echo "ERROR:python_crash")

        # Handle result
        case "$action" in
            CONTINUE:*)
                local agent="${action#CONTINUE:}"
                log "Announce from $agent detected — no coordinator response. Posting continue."

                local post_resp
                post_resp=$(curl -s -H "Authorization: Bearer $token" \
                    -H "Content-Type: application/json" \
                    -X POST "https://slack.com/api/chat.postMessage" \
		    -d "{\"channel\": \"$CHANNEL_ID\", \"text\": \"<@U0AHHUNEY4B> continue\"}"

                if [ -n "$post_resp" ]; then
                    local post_ok
                    post_ok=$(echo "$post_resp" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ok',False))" 2>/dev/null || echo "False")
                    if [ "$post_ok" = "True" ]; then
                        log "Posted 'continue' successfully"
                    else
                        local post_err
                        post_err=$(echo "$post_resp" | python3 -c "import json,sys; print(json.load(sys.stdin).get('error','unknown'))" 2>/dev/null || echo "unknown")
                        log "ERROR posting continue: $post_err"
                    fi
                else
                    log "ERROR: Empty response when posting continue"
                fi

                # Wait extra time for coordinator to process before next poll
                sleep 15
                ;;
            ERROR:*)
                local err="${action#ERROR:}"
                log "API error: $err"
                sleep 10
                ;;
            NONE)
                # Nothing to do
                ;;
        esac

        sleep "$POLL_INTERVAL"
    done
}

# ─── Trim processed file periodically ────────────────────────────
trim_processed() {
    if [ -f "$PROCESSED_FILE" ]; then
        tail -100 "$PROCESSED_FILE" > "$PROCESSED_FILE.tmp" 2>/dev/null && mv "$PROCESSED_FILE.tmp" "$PROCESSED_FILE"
    fi
}

# ─── Commands ─────────────────────────────────────────────────────

CMD="${1:-}"

case "$CMD" in
    --daemon)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "Chain watcher already running (PID $(cat "$PID_FILE"))"
            exit 0
        fi
        setup
        DAEMON=true
        log "Starting daemon..."
        watch_loop &
        echo $! > "$PID_FILE"
        echo "Chain watcher started (PID $!)"
        echo "Log: tail -f $LOG_FILE"
        ;;

    --stop)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                kill "$PID" 2>/dev/null
                rm -f "$PID_FILE"
                echo "Stopped (PID $PID)"
            else
                rm -f "$PID_FILE"
                echo "Not running (stale PID removed)"
            fi
        else
            echo "Not running"
        fi
        ;;

    --status)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "Running (PID $(cat "$PID_FILE"))"
            echo "Log: $LOG_FILE"
            echo "Processed: $(wc -l < "$PROCESSED_FILE" 2>/dev/null || echo 0) announces"
        else
            echo "Not running"
        fi
        ;;

    --reset)
        > "$PROCESSED_FILE"
        echo "Processed list cleared"
        ;;

    ""|--foreground)
        setup
        watch_loop
        ;;

    *)
        echo "HOOK Chain Watcher — Auto-continue agent chains"
        echo ""
        echo "Usage:"
        echo "  chain-watcher.sh              Run in foreground"
        echo "  chain-watcher.sh --daemon     Run as background daemon"
        echo "  chain-watcher.sh --stop       Stop the daemon"
        echo "  chain-watcher.sh --status     Check if running"
        echo "  chain-watcher.sh --reset      Clear processed announces"
        echo ""
        echo "Required: HOOK_SLACK_CHANNEL_ID env var"
        echo ""
        ;;
esac
