#!/bin/bash
# ioc-cache.sh — Manage the HOOK IOC enrichment cache
#
# Usage:
#   ./scripts/ioc-cache.sh stats              Show cache statistics
#   ./scripts/ioc-cache.sh lookup <IOC>        Look up a cached IOC (auto-detects type)
#   ./scripts/ioc-cache.sh list [ip|domain|hash]   List cached IOCs
#   ./scripts/ioc-cache.sh clear               Clear all cache entries
#   ./scripts/ioc-cache.sh clear --stale       Clear only expired entries
#   ./scripts/ioc-cache.sh clear ip            Clear all IP cache entries
#   ./scripts/ioc-cache.sh clear ip --stale    Clear only expired IP entries

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CMD="${1:-stats}"

case "$CMD" in
    stats)
        python3 - "$SCRIPT_DIR" <<'PYEOF'
import sys, os
script_dir = sys.argv[1]
exec(open(os.path.join(script_dir, 'lib', 'common.py')).read())

stats = cache_stats()
print('')
print('HOOK IOC Cache Statistics')
print(f'  Cache directory: {stats["cache_dir"]}')
print('')
print(f'  Total entries:  {stats["total"]}')
print(f'  Fresh:          {stats["fresh"]}')
print(f'  Stale:          {stats["stale"]}')
print('')
for ioc_type, type_stats in stats['by_type'].items():
    ttl = CACHE_TTL.get(ioc_type, 24)
    print(f'  {ioc_type:8s}  {type_stats["total"]:4d} total  {type_stats["fresh"]:4d} fresh  {type_stats["stale"]:4d} stale  (TTL: {ttl}h)')
print('')
PYEOF
        ;;

    lookup)
        IOC="${2:?Usage: ioc-cache.sh lookup <IOC>}"
        python3 - "$SCRIPT_DIR" "$IOC" <<'PYEOF'
import sys, os
script_dir = sys.argv[1]
ioc_value = sys.argv[2].strip()
exec(open(os.path.join(script_dir, 'lib', 'common.py')).read())

result, hit, ioc_type = cache_lookup(ioc_value)
if hit:
    output_json(result)
else:
    print(f'Not in cache (type detected: {ioc_type})')
    sys.exit(1)
PYEOF
        ;;

    list)
        TYPE_FILTER="${2:-}"
        python3 - "$SCRIPT_DIR" "$TYPE_FILTER" <<'PYEOF'
import sys, os, json
from datetime import datetime, timezone

script_dir = sys.argv[1]
type_filter = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else ''
exec(open(os.path.join(script_dir, 'lib', 'common.py')).read())

now = datetime.now(timezone.utc)
types = [type_filter] if type_filter else ['ip', 'domain', 'hash']
entries = []

for ioc_type in types:
    type_dir = os.path.join(CACHE_DIR, ioc_type)
    if not os.path.isdir(type_dir):
        continue
    for fname in sorted(os.listdir(type_dir)):
        if not fname.endswith('.json'):
            continue
        fpath = os.path.join(type_dir, fname)
        try:
            with open(fpath, 'r') as f:
                entry = json.load(f)
            cached_at = datetime.fromisoformat(entry['cached_at'])
            ttl = entry.get('ttl_hours', CACHE_TTL.get(ioc_type, 24))
            age_hours = (now - cached_at).total_seconds() / 3600
            fresh = age_hours < ttl
            risk = entry.get('result', {}).get('risk', '?')
            ioc_val = entry.get('ioc_value', fname.replace('.json', ''))
            status = 'FRESH' if fresh else 'STALE'
            entries.append((ioc_type, ioc_val, risk, f'{age_hours:.1f}h', f'{ttl}h', status))
        except Exception:
            entries.append((ioc_type, fname, '?', '?', '?', 'ERROR'))

if not entries:
    print('Cache is empty.')
    sys.exit(0)

# Print table
print('')
print(f'  {"TYPE":8s}  {"IOC":50s}  {"RISK":7s}  {"AGE":8s}  {"TTL":6s}  {"STATUS":6s}')
print(f'  {"----":8s}  {"---":50s}  {"----":7s}  {"---":8s}  {"---":6s}  {"------":6s}')
for t, ioc, risk, age, ttl, status in entries:
    ioc_display = ioc[:50] if len(ioc) <= 50 else ioc[:47] + '...'
    print(f'  {t:8s}  {ioc_display:50s}  {risk:7s}  {age:>8s}  {ttl:>6s}  {status:6s}')
print(f'\n  {len(entries)} entries')
print('')
PYEOF
        ;;

    clear)
        TYPE_FILTER="${2:-}"
        STALE_ONLY=0
        # Parse args: clear [type] [--stale]
        for arg in "${@:2}"; do
            case "$arg" in
                --stale) STALE_ONLY=1 ;;
                ip|domain|hash) TYPE_FILTER="$arg" ;;
            esac
        done
        python3 - "$SCRIPT_DIR" "$TYPE_FILTER" "$STALE_ONLY" <<'PYEOF'
import sys, os
script_dir = sys.argv[1]
type_filter = sys.argv[2] if sys.argv[2] else None
stale_only = sys.argv[3] == '1'
exec(open(os.path.join(script_dir, 'lib', 'common.py')).read())

removed = cache_clear(ioc_type=type_filter, stale_only=stale_only)
scope = type_filter or 'all types'
mode = 'stale' if stale_only else 'all'
print(f'Cleared {removed} {mode} cache entries ({scope})')
PYEOF
        ;;

    *)
        echo "Usage: ioc-cache.sh {stats|lookup|list|clear}"
        echo ""
        echo "  stats                     Show cache statistics"
        echo "  lookup <IOC>              Look up a cached IOC"
        echo "  list [ip|domain|hash]     List cached IOCs"
        echo "  clear [type] [--stale]    Clear cache entries"
        exit 1
        ;;
esac
