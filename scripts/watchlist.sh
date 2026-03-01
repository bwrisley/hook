#!/bin/bash
# watchlist.sh — Manage a persistent IOC watchlist
# Usage:
#   ./scripts/watchlist.sh add <ioc> [<ioc> ...]    Add IOCs to watchlist
#   ./scripts/watchlist.sh remove <ioc>              Remove an IOC
#   ./scripts/watchlist.sh list                      Show current watchlist
#   ./scripts/watchlist.sh check                     Re-enrich all watchlist IOCs
#   ./scripts/watchlist.sh import <file>             Import IOCs from file (one per line)
#   ./scripts/watchlist.sh clear                     Clear entire watchlist
#
# Watchlist stored at: data/watchlist.txt (one IOC per line, with metadata)
# Format: <ioc>|<type>|<added_date>|<last_checked>|<last_risk>

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WATCHLIST="$HOOK_DIR/data/watchlist.txt"
MAX_WATCHLIST=200

mkdir -p "$(dirname "$WATCHLIST")"
touch "$WATCHLIST"

ACTION="${1:?Usage: watchlist.sh <add|remove|list|check|import|clear> [args]}"
shift

# ─── Helpers ────────────────────────────────────────────────────────

detect_type() {
    local ioc="$1"
    if echo "$ioc" | grep -qE '^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$'; then
        echo "ip"
    elif echo "$ioc" | grep -qE '^[a-fA-F0-9]{32,64}$'; then
        echo "hash"
    else
        echo "domain"
    fi
}

now_utc() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

# ─── Actions ────────────────────────────────────────────────────────

case "$ACTION" in
    add)
        if [ $# -eq 0 ]; then
            echo "Usage: watchlist.sh add <ioc> [<ioc> ...]" >&2
            exit 1
        fi
        CURRENT=$(wc -l < "$WATCHLIST" | tr -d ' ')
        ADDED=0
        for IOC in "$@"; do
            IOC=$(echo "$IOC" | tr '[:upper:]' '[:lower:]' | tr -d ' ')
            if [ -z "$IOC" ]; then continue; fi
            if grep -q "^${IOC}|" "$WATCHLIST" 2>/dev/null; then
                echo "  Already tracked: $IOC"
                continue
            fi
            if [ "$CURRENT" -ge "$MAX_WATCHLIST" ]; then
                echo "  Watchlist full ($MAX_WATCHLIST max). Remove items first." >&2
                break
            fi
            TYPE=$(detect_type "$IOC")
            echo "${IOC}|${TYPE}|$(now_utc)|never|unknown" >> "$WATCHLIST"
            echo "  Added: $IOC ($TYPE)"
            ADDED=$((ADDED + 1))
            CURRENT=$((CURRENT + 1))
        done
        echo "$ADDED IOC(s) added. Watchlist: $CURRENT total."
        ;;

    remove)
        IOC="${1:?Usage: watchlist.sh remove <ioc>}"
        IOC=$(echo "$IOC" | tr '[:upper:]' '[:lower:]' | tr -d ' ')
        if grep -q "^${IOC}|" "$WATCHLIST" 2>/dev/null; then
            grep -v "^${IOC}|" "$WATCHLIST" > "$WATCHLIST.tmp"
            mv "$WATCHLIST.tmp" "$WATCHLIST"
            echo "Removed: $IOC"
        else
            echo "Not found: $IOC" >&2
            exit 1
        fi
        ;;

    list)
        COUNT=$(wc -l < "$WATCHLIST" | tr -d ' ')
        if [ "$COUNT" -eq 0 ]; then
            echo "Watchlist is empty."
            exit 0
        fi
        echo "HOOK Watchlist ($COUNT IOCs):"
        echo "─────────────────────────────────────────────────────"
        printf "%-45s %-8s %-12s %s\n" "IOC" "TYPE" "RISK" "LAST CHECKED"
        echo "─────────────────────────────────────────────────────"
        while IFS='|' read -r ioc type added checked risk; do
            printf "%-45s %-8s %-12s %s\n" "$ioc" "$type" "$risk" "$checked"
        done < "$WATCHLIST"
        ;;

    check)
        COUNT=$(wc -l < "$WATCHLIST" | tr -d ' ')
        if [ "$COUNT" -eq 0 ]; then
            echo "Watchlist is empty. Nothing to check."
            exit 0
        fi
        echo "Re-enriching $COUNT watchlist IOCs..."
        NOW=$(now_utc)
        TEMP="$WATCHLIST.tmp"
        : > "$TEMP"

        while IFS='|' read -r ioc type added checked risk; do
            echo "  Checking: $ioc ($type)..."
            case "$type" in
                ip)     RESULT=$("$SCRIPT_DIR/enrich-ip.sh" "$ioc" 2>/dev/null) ;;
                domain) RESULT=$("$SCRIPT_DIR/enrich-domain.sh" "$ioc" 2>/dev/null) ;;
                hash)   RESULT=$("$SCRIPT_DIR/enrich-hash.sh" "$ioc" 2>/dev/null) ;;
                *)      RESULT='{"risk":"UNKNOWN"}' ;;
            esac
            NEW_RISK=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('risk','UNKNOWN'))" 2>/dev/null || echo "ERROR")

            # Detect risk changes
            if [ "$risk" != "unknown" ] && [ "$risk" != "$NEW_RISK" ]; then
                echo "  RISK CHANGE: $ioc $risk → $NEW_RISK"
            fi

            echo "${ioc}|${type}|${added}|${NOW}|${NEW_RISK}" >> "$TEMP"
        done < "$WATCHLIST"

        mv "$TEMP" "$WATCHLIST"
        echo "Watchlist check complete. $COUNT IOCs re-enriched."
        ;;

    import)
        FILE="${1:?Usage: watchlist.sh import <file>}"
        if [ ! -f "$FILE" ]; then
            echo "File not found: $FILE" >&2
            exit 1
        fi
        ADDED=0
        while IFS= read -r line; do
            IOC=$(echo "$line" | tr -d ' ' | tr '[:upper:]' '[:lower:]')
            if [ -z "$IOC" ] || [[ "$IOC" == \#* ]]; then continue; fi
            if grep -q "^${IOC}|" "$WATCHLIST" 2>/dev/null; then continue; fi
            TYPE=$(detect_type "$IOC")
            echo "${IOC}|${TYPE}|$(now_utc)|never|unknown" >> "$WATCHLIST"
            ADDED=$((ADDED + 1))
        done < "$FILE"
        TOTAL=$(wc -l < "$WATCHLIST" | tr -d ' ')
        echo "$ADDED IOC(s) imported. Watchlist: $TOTAL total."
        ;;

    clear)
        read -rp "Clear entire watchlist? [y/N]: " CONFIRM
        if [ "${CONFIRM:-N}" = "y" ] || [ "${CONFIRM:-N}" = "Y" ]; then
            : > "$WATCHLIST"
            echo "Watchlist cleared."
        else
            echo "Cancelled."
        fi
        ;;

    *)
        echo "Unknown action: $ACTION" >&2
        echo "Usage: watchlist.sh <add|remove|list|check|import|clear> [args]" >&2
        exit 1
        ;;
esac
