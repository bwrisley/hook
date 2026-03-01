#!/bin/bash
# morning-briefing.sh — Post a morning threat summary to Slack
# Usage: ./scripts/morning-briefing.sh [--no-slack] [--days 1]
#
# Summarizes:
#   - Recent daily check results
#   - Current watchlist status
#   - Any high-risk IOCs found
#   - System health status
#
# Designed to run at start of business (e.g., 8:00 AM via cron)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_DIR="${HOOK_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
SLACK_CHANNEL="${HOOK_SLACK_CHANNEL:-#hook}"
REPORT_DIR="$HOOK_DIR/data/reports"
WATCHLIST="$HOOK_DIR/data/watchlist.txt"
LOG_DIR="${HOOK_LOG_DIR:-$HOME/.openclaw/logs/hook}"

NO_SLACK=false
LOOKBACK_DAYS=1
for arg in "$@"; do
    case "$arg" in
        --no-slack) NO_SLACK=true ;;
        --days) shift; LOOKBACK_DAYS="${1:-1}" ;;
    esac
done

# ─── Gather data ────────────────────────────────────────────────────

TODAY=$(date -u +%Y-%m-%d)

# Find recent daily reports
RECENT_JSON=$(find "$REPORT_DIR" -name "daily-feeds-*.json" -mtime -"$LOOKBACK_DAYS" 2>/dev/null | sort -r)

# Watchlist status
WATCHLIST_COUNT=0
WATCHLIST_HIGH=0
WATCHLIST_MEDIUM=0
if [ -f "$WATCHLIST" ] && [ -s "$WATCHLIST" ]; then
    WATCHLIST_COUNT=$(wc -l < "$WATCHLIST" | tr -d ' ')
    WATCHLIST_HIGH=$(grep -c "|HIGH$" "$WATCHLIST" || true)
    WATCHLIST_MEDIUM=$(grep -c "|MEDIUM$" "$WATCHLIST" || true)
fi

# Aggregate stats from recent JSON reports
TOTAL_ENRICHED=0
TOTAL_HIGH=0
TOTAL_MEDIUM=0
TOTAL_LOW=0
TOTAL_FEEDS=0

for json_file in $RECENT_JSON; do
    if [ -f "$json_file" ]; then
        STATS=$(python3 -c "
import json
try:
    d = json.load(open('$json_file'))
    s = d.get('summary', {})
    print(f\"{s.get('total',0)} {s.get('high',0)} {s.get('medium',0)} {s.get('low',0)}\")
except:
    print('0 0 0 0')
" 2>/dev/null || echo "0 0 0 0")
        read -r E H M L <<< "$STATS"
        TOTAL_ENRICHED=$((TOTAL_ENRICHED + ${E:-0}))
        TOTAL_HIGH=$((TOTAL_HIGH + ${H:-0}))
        TOTAL_MEDIUM=$((TOTAL_MEDIUM + ${M:-0}))
        TOTAL_LOW=$((TOTAL_LOW + ${L:-0}))
        TOTAL_FEEDS=$((TOTAL_FEEDS + 1))
    fi
done

# Gateway health
GW_STATUS="unknown"
if command -v openclaw >/dev/null 2>&1; then
    if openclaw gateway status 2>&1 | grep -qi "running\|active"; then
        GW_STATUS="operational"
    else
        GW_STATUS="DOWN — requires attention"
    fi
fi

# Recent enrichment log entries
LOG_ERRORS=0
LATEST_LOG="$LOG_DIR/enrichment-$(date -u +%Y-%m-%d).jsonl"
if [ -f "$LATEST_LOG" ]; then
    LOG_ERRORS=$(grep -c '"level":"ERROR"' "$LATEST_LOG" 2>/dev/null || true)
fi

# ─── Build briefing ────────────────────────────────────────────────

BRIEFING="*HOOK — Daily Threat Intelligence Briefing*"
BRIEFING+="\n$TODAY | PUNCH Cyber"
BRIEFING+="\n"
BRIEFING+="\n---"

# Threat posture
if [ "${TOTAL_HIGH:-0}" -gt 0 ] || [ "${WATCHLIST_HIGH:-0}" -gt 0 ]; then
    POSTURE="ELEVATED — high-risk indicators detected"
elif [ "${TOTAL_MEDIUM:-0}" -gt 0 ] || [ "${WATCHLIST_MEDIUM:-0}" -gt 0 ]; then
    POSTURE="GUARDED — medium-risk indicators present"
else
    POSTURE="NOMINAL — no significant threats detected"
fi
BRIEFING+="\n*Threat Posture:* $POSTURE"
BRIEFING+="\n"

# Feed intelligence
BRIEFING+="\n*Feed Intelligence (last ${LOOKBACK_DAYS}d)*"
if [ "$TOTAL_FEEDS" -gt 0 ]; then
    BRIEFING+="\n  IOCs analyzed: $TOTAL_ENRICHED"
    BRIEFING+="\n  High risk: $TOTAL_HIGH | Medium: $TOTAL_MEDIUM | Low: $TOTAL_LOW"
    if [ "${TOTAL_HIGH:-0}" -gt 0 ]; then
        BRIEFING+="\n  Action required: Review high-risk IOCs in daily report"
    fi
else
    BRIEFING+="\n  No automated checks completed in this period"
fi

# Watchlist
BRIEFING+="\n"
BRIEFING+="\n*Watchlist Status*"
BRIEFING+="\n  IOCs tracked: $WATCHLIST_COUNT"
if [ "${WATCHLIST_HIGH:-0}" -gt 0 ]; then
    BRIEFING+="\n  High risk: $WATCHLIST_HIGH (active monitoring)"
fi
if [ "${WATCHLIST_MEDIUM:-0}" -gt 0 ]; then
    BRIEFING+="\n  Medium risk: $WATCHLIST_MEDIUM"
fi
if [ "${WATCHLIST_COUNT:-0}" -eq 0 ]; then
    BRIEFING+="\n  No IOCs on watchlist"
fi

# System status
BRIEFING+="\n"
BRIEFING+="\n*System Status*"
BRIEFING+="\n  Gateway: $GW_STATUS"
if [ "${LOG_ERRORS:-0}" -gt 0 ]; then
    BRIEFING+="\n  Enrichment errors: $LOG_ERRORS (review log)"
else
    BRIEFING+="\n  Enrichment pipeline: nominal"
fi

BRIEFING+="\n---"
BRIEFING+="\n_Full report: data/reports/daily-${TODAY}.txt_"

# ─── Output / Post ──────────────────────────────────────────────────

echo -e "$BRIEFING"

if [ "$NO_SLACK" = false ]; then
    echo -e "$BRIEFING" | "$SCRIPT_DIR/lib/slack-notify.sh" "$SLACK_CHANNEL" 2>/dev/null
fi
