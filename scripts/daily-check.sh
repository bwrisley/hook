#!/bin/bash
# daily-check.sh — Automated daily threat check (designed for cron/LaunchAgent)
# Usage: ./scripts/daily-check.sh [--no-slack] [--feeds-only] [--watchlist-only]
#
# What it does:
#   1. Fetch fresh IOCs from threat feeds
#   2. Enrich new IOCs (via batch pipeline)
#   3. Re-check watchlist items for risk changes
#   4. Generate daily report
#   5. Post summary to Slack
#
# Outputs:
#   data/reports/daily-<date>.json    Full enrichment results
#   data/reports/daily-<date>.txt     Human-readable report
#   ~/.openclaw/logs/hook/daily-<date>.log   Run log
#
# Environment:
#   HOOK_SLACK_CHANNEL   — Channel to post to (default: #hook)
#   HOOK_MAX_FEED_ENRICH — Max IOCs to enrich from feeds (default: 20)
#   HOOK_DIR             — Path to HOOK repo (auto-detected)

set -uo pipefail

# ─── Setup ──────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_DIR="${HOOK_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
DATE=$(date -u +%Y-%m-%d)
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SLACK_CHANNEL="${HOOK_SLACK_CHANNEL:-#hook}"
MAX_FEED_ENRICH="${HOOK_MAX_FEED_ENRICH:-20}"
REPORT_DIR="$HOOK_DIR/data/reports"
LOG_DIR="${HOOK_LOG_DIR:-$HOME/.openclaw/logs/hook}"
LOG_FILE="$LOG_DIR/daily-$DATE.log"

# Parse flags
NO_SLACK=false
FEEDS_ONLY=false
WATCHLIST_ONLY=false
for arg in "$@"; do
    case "$arg" in
        --no-slack) NO_SLACK=true ;;
        --feeds-only) FEEDS_ONLY=true ;;
        --watchlist-only) WATCHLIST_ONLY=true ;;
    esac
done

mkdir -p "$REPORT_DIR" "$LOG_DIR"

# ─── Logging ────────────────────────────────────────────────────────

log() {
    local msg="[$(date -u +%H:%M:%S)] $1"
    echo "$msg" | tee -a "$LOG_FILE"
}

log "═══════════════════════════════════════════════════"
log "HOOK Daily Check — $DATE"
log "═══════════════════════════════════════════════════"

# ─── Step 1: Fetch Feeds ───────────────────────────────────────────

FEED_IOCS=0
FEED_FILE=""

if [ "$WATCHLIST_ONLY" = false ]; then
    log "Step 1: Fetching threat feeds..."
    FEED_RESULT=$("$SCRIPT_DIR/fetch-feeds.sh" all 2>&1 | tee -a "$LOG_FILE")
    FEED_FILE="$HOOK_DIR/data/feeds/combined-$DATE.txt"
    if [ -f "$FEED_FILE" ]; then
        FEED_IOCS=$(wc -l < "$FEED_FILE" | tr -d ' ')
        log "  → $FEED_IOCS IOCs fetched"
    else
        log "  → No feed file generated"
    fi
else
    log "Step 1: Skipped (--watchlist-only)"
fi

# ─── Step 2: Enrich New Feed IOCs ──────────────────────────────────

FEED_HIGH=0
FEED_ENRICHED=0
FEED_REPORT=""

if [ "$WATCHLIST_ONLY" = false ] && [ "$FEED_IOCS" -gt 0 ]; then
    log "Step 2: Enriching top $MAX_FEED_ENRICH feed IOCs..."

    # Take a sample (rate limits mean we can't enrich everything)
    SAMPLE_FILE="$REPORT_DIR/feed-sample-$DATE.txt"
    head -"$MAX_FEED_ENRICH" "$FEED_FILE" > "$SAMPLE_FILE"

    # Convert to extract-iocs format and enrich
    ENRICH_RESULT=$(cat "$SAMPLE_FILE" \
        | "$SCRIPT_DIR/extract-iocs.sh" \
        | "$SCRIPT_DIR/enrich-batch.sh" 2>&1)

    if [ -n "$ENRICH_RESULT" ]; then
        echo "$ENRICH_RESULT" > "$REPORT_DIR/daily-feeds-$DATE.json"
        FEED_ENRICHED=$(echo "$ENRICH_RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('summary',{}).get('total',0))" 2>/dev/null || echo 0)
        FEED_HIGH=$(echo "$ENRICH_RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('summary',{}).get('high',0))" 2>/dev/null || echo 0)

        # Generate formatted report
        FEED_REPORT=$(echo "$ENRICH_RESULT" | "$SCRIPT_DIR/format-report.sh" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('report',''))" 2>/dev/null || echo "")
        log "  → $FEED_ENRICHED IOCs enriched, $FEED_HIGH HIGH risk"
    else
        log "  → Enrichment returned no results"
    fi
else
    log "Step 2: Skipped (no feed IOCs or --watchlist-only)"
fi

# ─── Step 3: Re-check Watchlist ────────────────────────────────────

WATCHLIST_COUNT=0
WATCHLIST_CHANGES=""

if [ "$FEEDS_ONLY" = false ]; then
    WATCHLIST_FILE="$HOOK_DIR/data/watchlist.txt"
    if [ -f "$WATCHLIST_FILE" ] && [ -s "$WATCHLIST_FILE" ]; then
        WATCHLIST_COUNT=$(wc -l < "$WATCHLIST_FILE" | tr -d ' ')
        log "Step 3: Re-checking $WATCHLIST_COUNT watchlist IOCs..."

        # Capture output for change detection
        WATCHLIST_OUTPUT=$("$SCRIPT_DIR/watchlist.sh" check 2>&1 | tee -a "$LOG_FILE")
        WATCHLIST_CHANGES=$(echo "$WATCHLIST_OUTPUT" | grep "RISK CHANGE:" || true)

        if [ -n "$WATCHLIST_CHANGES" ]; then
            log "  → Risk changes detected!"
        else
            log "  → No risk changes"
        fi
    else
        log "Step 3: Watchlist empty, skipping"
    fi
else
    log "Step 3: Skipped (--feeds-only)"
fi

# ─── Step 4: Generate Daily Report ─────────────────────────────────

log "Step 4: Generating daily report..."

REPORT="$REPORT_DIR/daily-$DATE.txt"

cat > "$REPORT" <<EOF
===================================================
HOOK Daily Threat Report — $DATE
PUNCH Cyber
===================================================

FEED SUMMARY
   Sources: Feodo Tracker, URLhaus, ThreatFox
   Total IOCs fetched: $FEED_IOCS
   IOCs enriched: $FEED_ENRICHED
   HIGH risk: $FEED_HIGH

WATCHLIST
   IOCs tracked: $WATCHLIST_COUNT
EOF

if [ -n "$WATCHLIST_CHANGES" ]; then
    cat >> "$REPORT" <<EOF
   Risk changes detected:
$WATCHLIST_CHANGES
EOF
else
    cat >> "$REPORT" <<EOF
   No risk changes detected
EOF
fi

# Add high-risk alerts
if [ "$FEED_HIGH" -gt 0 ]; then
    cat >> "$REPORT" <<EOF

HIGH RISK IOCs FROM FEEDS
$FEED_REPORT
EOF
fi

cat >> "$REPORT" <<EOF

===================================================
Full data: $REPORT_DIR/daily-feeds-$DATE.json
Log: $LOG_FILE
===================================================
EOF

log "  → Report saved: $REPORT"

# ─── Step 5: Post to Slack ──────────────────────────────────────────

if [ "$NO_SLACK" = false ]; then
    log "Step 5: Posting summary to Slack ($SLACK_CHANNEL)..."

    # Build a concise Slack message
    SLACK_MSG="*HOOK Daily Threat Check — $DATE*"
    SLACK_MSG+="\n\n*Feeds:* $FEED_IOCS IOCs fetched, $FEED_ENRICHED enriched"

    if [ "$FEED_HIGH" -gt 0 ]; then
        SLACK_MSG+="\n*ALERT: $FEED_HIGH HIGH risk IOC(s) identified in feeds*"
    else
        SLACK_MSG+="\nNo high-risk IOCs in today's feeds"
    fi

    SLACK_MSG+="\n*Watchlist:* $WATCHLIST_COUNT IOCs tracked"

    if [ -n "$WATCHLIST_CHANGES" ]; then
        SLACK_MSG+="\n*Risk changes detected* — review daily report for details"
    fi

    # Post via slack-notify
    echo -e "$SLACK_MSG" | "$SCRIPT_DIR/lib/slack-notify.sh" "$SLACK_CHANNEL" 2>&1 | tee -a "$LOG_FILE"
else
    log "Step 5: Skipped (--no-slack)"
fi

# ─── Done ───────────────────────────────────────────────────────────

log "═══════════════════════════════════════════════════"
log "Daily check complete."
log "  Feed IOCs: $FEED_IOCS fetched, $FEED_ENRICHED enriched, $FEED_HIGH high risk"
log "  Watchlist: $WATCHLIST_COUNT tracked"
log "  Report: $REPORT"
log "═══════════════════════════════════════════════════"

# Exit with alert code if high-risk IOCs found
if [ "$FEED_HIGH" -gt 0 ]; then
    exit 2  # 2 = high risk alert
fi
exit 0
