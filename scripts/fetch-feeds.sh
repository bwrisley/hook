#!/bin/bash
# fetch-feeds.sh — Download IOCs from public threat intelligence feeds
# Usage: ./scripts/fetch-feeds.sh [--feeds all|feodo|urlhaus|threatfox]
#
# Feeds:
#   feodo     — Feodo Tracker botnet C2 IPs (abuse.ch)
#   urlhaus   — Malware distribution URLs/domains (abuse.ch)
#   threatfox — Crowd-sourced IOCs (abuse.ch)
#
# Output: One IOC per line in data/feeds/<feed>-<date>.txt
#         Combined file: data/feeds/combined-<date>.txt

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FEED_DIR="$HOOK_DIR/data/feeds"
DATE=$(date -u +%Y-%m-%d)
FEEDS="${1:---feeds}"
FEED_LIST="${2:-all}"

# Parse --feeds flag
if [ "$FEEDS" = "--feeds" ]; then
    FEED_LIST="${FEED_LIST:-all}"
elif [ "$FEEDS" != "--feeds" ]; then
    FEED_LIST="$FEEDS"
fi

mkdir -p "$FEED_DIR"

# Load shared library for logging
exec 3>&1  # save stdout
source_log() {
    local level="$1" msg="$2"
    echo "[$level] fetch-feeds: $msg" >&3
}

TOTAL_NEW=0
COMBINED="$FEED_DIR/combined-$DATE.txt"
: > "$COMBINED"  # truncate or create

# ─── Feodo Tracker (botnet C2 IPs) ─────────────────────────────────

fetch_feodo() {
    local OUTPUT="$FEED_DIR/feodo-$DATE.txt"
    source_log "INFO" "Fetching Feodo Tracker C2 IPs..."

    local RAW
    RAW=$(curl -s --max-time 30 "https://feodotracker.abuse.ch/downloads/ipblocklist.txt" 2>/dev/null)

    if [ -z "$RAW" ]; then
        source_log "WARN" "Feodo Tracker: empty response"
        return
    fi

    # Strip comments and blank lines, extract IPs
    echo "$RAW" | grep -v '^#' | grep -v '^$' | head -500 > "$OUTPUT"
    local COUNT
    COUNT=$(wc -l < "$OUTPUT" | tr -d ' ')
    source_log "INFO" "Feodo Tracker: $COUNT IPs → $OUTPUT"
    cat "$OUTPUT" >> "$COMBINED"
    TOTAL_NEW=$((TOTAL_NEW + COUNT))
}

# ─── URLhaus (malware distribution domains) ─────────────────────────

fetch_urlhaus() {
    local OUTPUT="$FEED_DIR/urlhaus-$DATE.txt"
    source_log "INFO" "Fetching URLhaus online domains..."

    local RAW
    RAW=$(curl -s --max-time 30 "https://urlhaus.abuse.ch/downloads/text_online/" 2>/dev/null)

    if [ -z "$RAW" ]; then
        source_log "WARN" "URLhaus: empty response"
        return
    fi

    # Extract domains from URLs, deduplicate
    echo "$RAW" | grep -v '^#' | grep -v '^$' \
        | sed 's|https\?://||' | cut -d'/' -f1 | cut -d':' -f1 \
        | sort -u | head -500 > "$OUTPUT"
    local COUNT
    COUNT=$(wc -l < "$OUTPUT" | tr -d ' ')
    source_log "INFO" "URLhaus: $COUNT domains → $OUTPUT"
    cat "$OUTPUT" >> "$COMBINED"
    TOTAL_NEW=$((TOTAL_NEW + COUNT))
}

# ─── ThreatFox (crowd-sourced IOCs) ────────────────────────────────

fetch_threatfox() {
    local OUTPUT="$FEED_DIR/threatfox-$DATE.txt"
    source_log "INFO" "Fetching ThreatFox recent IOCs..."

    # ThreatFox API — get IOCs from last 24 hours
    local RAW
    RAW=$(curl -s --max-time 30 -X POST "https://threatfox-api.abuse.ch/api/v1/" \
        -H "Content-Type: application/json" \
        -d '{"query": "get_iocs", "days": 1}' 2>/dev/null)

    if [ -z "$RAW" ]; then
        source_log "WARN" "ThreatFox: empty response"
        return
    fi

    # Extract IOC values (IPs, domains, hashes)
    echo "$RAW" | python3 -c "
import json, sys, re
try:
    data = json.load(sys.stdin)
    iocs = data.get('data', [])
    if not isinstance(iocs, list):
        iocs = []
    seen = set()
    for entry in iocs[:500]:
        ioc = entry.get('ioc', '').strip()
        # Clean port suffixes from IPs (e.g., '1.2.3.4:443')
        if ':' in ioc and not ioc.startswith('http'):
            ioc = ioc.split(':')[0]
        if ioc and ioc not in seen:
            seen.add(ioc)
            print(ioc)
except Exception as e:
    print(f'# parse error: {e}', file=sys.stderr)
" > "$OUTPUT" 2>/dev/null

    local COUNT
    COUNT=$(wc -l < "$OUTPUT" | tr -d ' ')
    source_log "INFO" "ThreatFox: $COUNT IOCs → $OUTPUT"
    cat "$OUTPUT" >> "$COMBINED"
    TOTAL_NEW=$((TOTAL_NEW + COUNT))
}

# ─── Run feeds ──────────────────────────────────────────────────────

source_log "INFO" "Starting feed fetch for $DATE"

case "$FEED_LIST" in
    all)
        fetch_feodo
        fetch_urlhaus
        fetch_threatfox
        ;;
    feodo)
        fetch_feodo
        ;;
    urlhaus)
        fetch_urlhaus
        ;;
    threatfox)
        fetch_threatfox
        ;;
    *)
        echo "Unknown feed: $FEED_LIST (options: all, feodo, urlhaus, threatfox)" >&2
        exit 1
        ;;
esac

# Deduplicate combined file
if [ -f "$COMBINED" ]; then
    sort -u "$COMBINED" -o "$COMBINED"
    TOTAL_NEW=$(wc -l < "$COMBINED" | tr -d ' ')
fi

source_log "INFO" "Feed fetch complete: $TOTAL_NEW unique IOCs → $COMBINED"

# Output summary as JSON for piping
python3 -c "
import json
print(json.dumps({
    'date': '$DATE',
    'total_iocs': $TOTAL_NEW,
    'combined_file': '$COMBINED',
    'feed_dir': '$FEED_DIR'
}, indent=2))
"
