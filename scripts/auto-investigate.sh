#!/bin/bash
# auto-investigate.sh — Proactive investigation trigger
#
# Called by daily-check.sh and watchlist.sh when high-risk IOCs are detected.
# Creates an investigation, registers IOCs, enriches unenriched ones,
# and posts detailed findings to Slack.
#
# Usage:
#   ./scripts/auto-investigate.sh --title "Feed alert: 3 HIGH risk IOCs" \
#     --source "daily-check" \
#     --iocs "ip:45.77.65.211,domain:evil.com,hash:abc123"
#
#   echo '{"high_risk_iocs": [...]}' | ./scripts/auto-investigate.sh \
#     --title "Watchlist risk escalation" --source "watchlist-check"
#
# Options:
#   --title <text>       Investigation title (required)
#   --source <name>      What triggered this (daily-check, watchlist-check, manual)
#   --iocs <csv>         Comma-separated type:value pairs
#   --no-slack           Skip Slack notification
#   --existing <INV-ID>  Add to existing investigation instead of creating new
#   stdin                JSON with high_risk_iocs array (alternative to --iocs)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_DIR="${HOOK_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
SLACK_CHANNEL="${HOOK_SLACK_CHANNEL:-#hook}"

# Parse args
TITLE=""
SOURCE="unknown"
IOCS_CSV=""
NO_SLACK=false
EXISTING_INV=""

while [ $# -gt 0 ]; do
    case "$1" in
        --title) TITLE="$2"; shift 2 ;;
        --source) SOURCE="$2"; shift 2 ;;
        --iocs) IOCS_CSV="$2"; shift 2 ;;
        --no-slack) NO_SLACK=true; shift ;;
        --existing) EXISTING_INV="$2"; shift 2 ;;
        *) shift ;;
    esac
done

if [ -z "$TITLE" ]; then
    echo '{"error": "Missing --title"}' >&2
    exit 1
fi

# Read IOCs from stdin JSON if no --iocs flag
STDIN_JSON=""
if [ -z "$IOCS_CSV" ] && [ ! -t 0 ]; then
    STDIN_JSON=$(cat)
fi

python3 - "$SCRIPT_DIR" "$HOOK_DIR" "$TITLE" "$SOURCE" "$IOCS_CSV" "$NO_SLACK" "$EXISTING_INV" "$SLACK_CHANNEL" <<PYEOF
import json, sys, os, subprocess

script_dir = sys.argv[1]
hook_dir = sys.argv[2]
title = sys.argv[3]
source = sys.argv[4]
iocs_csv = sys.argv[5]
no_slack = sys.argv[6] == 'true'
existing_inv = sys.argv[7]
slack_channel = sys.argv[8]
stdin_json = '''$STDIN_JSON'''

# Load common library
exec(open(os.path.join(script_dir, 'lib', 'common.py')).read())

SCRIPT = 'auto-investigate'
log_info(SCRIPT, f'Triggered by {source}: {title}')

# --- Parse IOCs ---

iocs = []  # list of (type, value)

if iocs_csv:
    for pair in iocs_csv.split(','):
        pair = pair.strip()
        if ':' in pair:
            t, v = pair.split(':', 1)
            iocs.append((t.strip(), v.strip()))

if stdin_json:
    try:
        data = json.loads(stdin_json)
        for item in data.get('high_risk_iocs', []):
            if isinstance(item, dict):
                iocs.append((item.get('type', 'unknown'), item.get('value', item.get('ioc', ''))))
            elif isinstance(item, str):
                # Auto-detect type
                result, hit, ioc_type = cache_lookup(item)
                iocs.append((ioc_type, item))
    except json.JSONDecodeError:
        log_warn(SCRIPT, 'Failed to parse stdin JSON')

if not iocs:
    log_warn(SCRIPT, 'No IOCs provided, nothing to investigate')
    print(json.dumps({'error': 'no_iocs', 'title': title}))
    sys.exit(0)

log_info(SCRIPT, f'{len(iocs)} IOCs to investigate')

# --- Create or reuse investigation ---

inv_script = os.path.join(script_dir, 'investigation.sh')

if existing_inv:
    inv_id = existing_inv
    log_info(SCRIPT, f'Adding to existing investigation: {inv_id}')
else:
    result = subprocess.run(
        [inv_script, 'create', title],
        capture_output=True, text=True, timeout=10
    )
    try:
        inv_data = json.loads(result.stdout)
        inv_id = inv_data['id']
        log_info(SCRIPT, f'Created investigation: {inv_id}')
    except (json.JSONDecodeError, KeyError):
        log_error(SCRIPT, 'Failed to create investigation', {'stdout': result.stdout[:200]})
        print(json.dumps({'error': 'create_failed'}))
        sys.exit(1)

# --- Register IOCs and collect enrichment ---

enriched_iocs = []

for ioc_type, ioc_value in iocs:
    if not ioc_value:
        continue

    # Add to investigation
    subprocess.run(
        [inv_script, 'add-ioc', inv_id, ioc_type, ioc_value, f'Auto-detected by {source}'],
        capture_output=True, text=True, timeout=10
    )

    # Check cache for enrichment
    cached, hit = cache_get(ioc_type, ioc_value)
    if hit and cached:
        enriched_iocs.append({
            'type': ioc_type,
            'value': ioc_value,
            'risk': cached.get('risk', 'UNKNOWN'),
            'sources': cached.get('sources', {}),
            'from_cache': True
        })
        continue

    # Enrich live if not cached
    enrich_script = None
    if ioc_type == 'ip':
        enrich_script = os.path.join(script_dir, 'enrich-ip.sh')
    elif ioc_type == 'domain':
        enrich_script = os.path.join(script_dir, 'enrich-domain.sh')
    elif ioc_type == 'hash':
        enrich_script = os.path.join(script_dir, 'enrich-hash.sh')

    if enrich_script:
        try:
            r = subprocess.run(
                [enrich_script, ioc_value],
                capture_output=True, text=True, timeout=120
            )
            if r.stdout.strip():
                edata = json.loads(r.stdout)
                enriched_iocs.append({
                    'type': ioc_type,
                    'value': ioc_value,
                    'risk': edata.get('risk', 'UNKNOWN'),
                    'sources': edata.get('sources', {}),
                    'from_cache': False
                })
            else:
                enriched_iocs.append({
                    'type': ioc_type,
                    'value': ioc_value,
                    'risk': 'ERROR',
                    'sources': {},
                    'from_cache': False
                })
        except Exception as e:
            log_warn(SCRIPT, f'Enrichment failed for {ioc_value}: {e}')
            enriched_iocs.append({
                'type': ioc_type,
                'value': ioc_value,
                'risk': 'ERROR',
                'sources': {},
                'from_cache': False
            })
    else:
        enriched_iocs.append({
            'type': ioc_type,
            'value': ioc_value,
            'risk': 'UNKNOWN',
            'sources': {},
            'from_cache': False
        })

# --- Record finding ---

high_count = sum(1 for i in enriched_iocs if i['risk'] == 'HIGH')
med_count = sum(1 for i in enriched_iocs if i['risk'] == 'MEDIUM')
total = len(enriched_iocs)

summary = f'Auto-enrichment ({source}): {total} IOCs processed, {high_count} HIGH, {med_count} MEDIUM risk'

subprocess.run(
    [inv_script, 'add-finding', inv_id, f'auto-{source}', summary],
    capture_output=True, text=True, timeout=10
)

# --- Build Slack message ---

if not no_slack:
    lines = []
    lines.append(f'*HOOK Proactive Alert* -- {source}')
    lines.append(f'*Investigation:* {inv_id}')
    lines.append(f'*Title:* {title}')
    lines.append(f'')
    lines.append(f'*{total} IOCs investigated:* {high_count} HIGH, {med_count} MEDIUM risk')
    lines.append(f'')

    for ioc in enriched_iocs:
        risk_emoji = {'HIGH': ':red_circle:', 'MEDIUM': ':large_orange_circle:', 'LOW': ':white_circle:'}.get(ioc['risk'], ':black_circle:')
        cached_tag = ' (cached)' if ioc['from_cache'] else ''
        line = f'{risk_emoji} `{ioc["value"]}` [{ioc["type"]}] -- *{ioc["risk"]}*{cached_tag}'

        # Add key details
        details = []
        src = ioc.get('sources', {})
        vt = src.get('virustotal', {})
        abuse = src.get('abuseipdb', {})
        if vt.get('malicious', 0) > 0:
            details.append(f'VT: {vt["malicious"]} malicious')
        if abuse.get('abuse_confidence', 0) > 0:
            details.append(f'AbuseIPDB: {abuse["abuse_confidence"]}%')
        if vt.get('country'):
            details.append(f'{vt["country"]}')
        if vt.get('as_owner') and vt['as_owner'] != 'unknown':
            details.append(f'{vt["as_owner"]}')
        if details:
            line += f'\n    {" | ".join(details)}'

        lines.append(line)

    lines.append(f'')
    lines.append(f'_View full investigation: `./scripts/investigation.sh status {inv_id}`_')

    slack_msg = '\n'.join(lines)

    try:
        notify = os.path.join(script_dir, 'lib', 'slack-notify.sh')
        subprocess.run(
            [notify, slack_channel],
            input=slack_msg, capture_output=True, text=True, timeout=15
        )
        log_info(SCRIPT, f'Alert posted to {slack_channel}')
    except Exception as e:
        log_warn(SCRIPT, f'Slack notification failed: {e}')

# --- Output ---

result = {
    'inv_id': inv_id,
    'source': source,
    'iocs_total': total,
    'iocs_high': high_count,
    'iocs_medium': med_count,
    'enriched': enriched_iocs
}

log_info(SCRIPT, f'Auto-investigation complete: {inv_id}', {
    'total': total, 'high': high_count, 'medium': med_count
})

print(json.dumps(result, indent=2))
PYEOF
