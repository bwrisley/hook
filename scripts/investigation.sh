#!/bin/bash
# investigation.sh — Manage HOOK investigations (stateful context across Slack messages)
#
# Usage:
#   ./scripts/investigation.sh create "Cobalt Strike on WKSTN-FIN-042"
#   ./scripts/investigation.sh status [INV-ID]
#   ./scripts/investigation.sh add-ioc <INV-ID> <type> <value> [context]
#   ./scripts/investigation.sh add-finding <INV-ID> <agent> <summary> [detail_file]
#   ./scripts/investigation.sh set-status <INV-ID> <status>
#   ./scripts/investigation.sh get <INV-ID>                  (full JSON state)
#   ./scripts/investigation.sh context <INV-ID>              (formatted context for agent handoff)
#   ./scripts/investigation.sh list [--active|--closed|--all]
#   ./scripts/investigation.sh close <INV-ID> [disposition]
#   ./scripts/investigation.sh active                        (show active investigation, if any)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INV_DIR="${HOOK_DATA_DIR:-$HOOK_DIR/data}/investigations"
CMD="${1:-help}"

# --- Helpers ---------------------------------------------------------------

generate_id() {
    local date_part
    date_part=$(date -u '+%Y%m%d')
    local seq=1
    while [ -d "$INV_DIR/INV-${date_part}-$(printf '%03d' $seq)" ]; do
        seq=$((seq + 1))
    done
    echo "INV-${date_part}-$(printf '%03d' $seq)"
}

now_utc() {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
}

ensure_dir() {
    mkdir -p "$INV_DIR"
}

get_state() {
    local inv_id="$1"
    local state_file="$INV_DIR/$inv_id/state.json"
    if [ ! -f "$state_file" ]; then
        echo "Investigation not found: $inv_id" >&2
        return 1
    fi
    cat "$state_file"
}

# --- Commands --------------------------------------------------------------

case "$CMD" in
    create)
        TITLE="${2:?Usage: investigation.sh create \"<title>\"}"
        ensure_dir
        INV_ID=$(generate_id)
        INV_PATH="$INV_DIR/$INV_ID"
        mkdir -p "$INV_PATH/findings"

        python3 - "$INV_ID" "$TITLE" "$INV_PATH" <<'PYEOF'
import json, sys
from datetime import datetime, timezone

inv_id = sys.argv[1]
title = sys.argv[2]
inv_path = sys.argv[3]
now = datetime.now(timezone.utc).isoformat()

state = {
    'id': inv_id,
    'title': title,
    'status': 'active',
    'created_at': now,
    'updated_at': now,
    'disposition': None,
    'iocs': [],
    'findings': [],
    'timeline': [
        {'timestamp': now, 'event': 'Investigation created', 'agent': 'system'}
    ],
    'tags': [],
    'notes': []
}

with open(f'{inv_path}/state.json', 'w') as f:
    json.dump(state, f, indent=2)

print(json.dumps({'id': inv_id, 'title': title, 'path': inv_path, 'status': 'active'}, indent=2))
PYEOF
        ;;

    status)
        INV_ID="${2:-}"
        if [ -z "$INV_ID" ]; then
            # Show active investigation
            exec "$0" active
        fi
        python3 - "$INV_DIR" "$INV_ID" <<'PYEOF'
import json, sys
from datetime import datetime, timezone

inv_dir = sys.argv[1]
inv_id = sys.argv[2]
state_file = f'{inv_dir}/{inv_id}/state.json'

try:
    with open(state_file) as f:
        s = json.load(f)
except FileNotFoundError:
    print(f'Investigation not found: {inv_id}')
    sys.exit(1)

now = datetime.now(timezone.utc)
created = datetime.fromisoformat(s['created_at'].replace('Z', '+00:00'))
age = now - created
hours = age.total_seconds() / 3600

print(f'')
print(f'  Investigation: {s["id"]}')
print(f'  Title:         {s["title"]}')
print(f'  Status:        {s["status"].upper()}')
print(f'  Created:       {s["created_at"]}')
print(f'  Age:           {hours:.1f} hours')
print(f'  IOCs:          {len(s["iocs"])}')
print(f'  Findings:      {len(s["findings"])}')
print(f'  Timeline:      {len(s["timeline"])} events')
if s.get('disposition'):
    print(f'  Disposition:   {s["disposition"]}')
if s.get('tags'):
    print(f'  Tags:          {", ".join(s["tags"])}')
print(f'')

if s['iocs']:
    print(f'  IOCs:')
    for ioc in s['iocs']:
        risk = ioc.get('risk', '?')
        ctx = ioc.get('context', '')
        print(f'    [{ioc["type"]:8s}] {ioc["value"]:50s} risk={risk:7s} {ctx}')
    print(f'')

if s['findings']:
    print(f'  Findings:')
    for f in s['findings']:
        print(f'    [{f["agent"]:20s}] {f["summary"]}')
    print(f'')
PYEOF
        ;;

    add-ioc)
        INV_ID="${2:?Usage: investigation.sh add-ioc <INV-ID> <type> <value> [context]}"
        IOC_TYPE="${3:?Missing IOC type (ip/domain/hash/url/email)}"
        IOC_VALUE="${4:?Missing IOC value}"
        IOC_CONTEXT="${5:-}"

        python3 - "$INV_DIR" "$INV_ID" "$IOC_TYPE" "$IOC_VALUE" "$IOC_CONTEXT" "$SCRIPT_DIR" <<'PYEOF'
import json, sys, os
from datetime import datetime, timezone

inv_dir, inv_id, ioc_type, ioc_value, ioc_context, script_dir = sys.argv[1:7]
state_file = f'{inv_dir}/{inv_id}/state.json'

try:
    with open(state_file) as f:
        s = json.load(f)
except FileNotFoundError:
    print(f'{{"error": "Investigation not found: {inv_id}"}}')
    sys.exit(1)

now = datetime.now(timezone.utc).isoformat()

# Check for duplicate
existing = [i for i in s['iocs'] if i['value'] == ioc_value]
if existing:
    # Update context if new context provided
    if ioc_context and not existing[0].get('context'):
        existing[0]['context'] = ioc_context
        existing[0]['updated_at'] = now
        s['updated_at'] = now
        with open(state_file, 'w') as f:
            json.dump(s, f, indent=2)
        print(json.dumps({'action': 'updated', 'ioc': ioc_value, 'inv_id': inv_id}))
    else:
        print(json.dumps({'action': 'duplicate', 'ioc': ioc_value, 'inv_id': inv_id}))
    sys.exit(0)

# Check cache for existing enrichment
risk = 'UNKNOWN'
try:
    exec(open(os.path.join(script_dir, 'lib', 'common.py')).read())
    cached, hit, detected_type = cache_lookup(ioc_value)
    if hit and cached:
        risk = cached.get('risk', 'UNKNOWN')
except Exception:
    pass

ioc_entry = {
    'type': ioc_type,
    'value': ioc_value,
    'context': ioc_context,
    'risk': risk,
    'added_at': now,
    'enriched': risk != 'UNKNOWN'
}

s['iocs'].append(ioc_entry)
s['updated_at'] = now
s['timeline'].append({
    'timestamp': now,
    'event': f'IOC added: {ioc_type}:{ioc_value}',
    'agent': 'system'
})

with open(state_file, 'w') as f:
    json.dump(s, f, indent=2)

print(json.dumps({'action': 'added', 'ioc': ioc_entry, 'inv_id': inv_id}, indent=2))
PYEOF
        ;;

    add-finding)
        INV_ID="${2:?Usage: investigation.sh add-finding <INV-ID> <agent> <summary> [detail_file]}"
        AGENT="${3:?Missing agent name}"
        SUMMARY="${4:?Missing summary}"
        DETAIL_FILE="${5:-}"

        python3 - "$INV_DIR" "$INV_ID" "$AGENT" "$SUMMARY" "$DETAIL_FILE" <<'PYEOF'
import json, sys
from datetime import datetime, timezone

inv_dir, inv_id, agent, summary, detail_file = sys.argv[1:6]
state_file = f'{inv_dir}/{inv_id}/state.json'

try:
    with open(state_file) as f:
        s = json.load(f)
except FileNotFoundError:
    print(f'{{"error": "Investigation not found: {inv_id}"}}')
    sys.exit(1)

now = datetime.now(timezone.utc).isoformat()

# Read detail from file if provided
detail = ''
if detail_file:
    try:
        with open(detail_file) as f:
            detail = f.read()
    except FileNotFoundError:
        detail = f'(detail file not found: {detail_file})'

finding = {
    'agent': agent,
    'summary': summary,
    'detail': detail,
    'timestamp': now
}

# Also save full detail to findings/ directory
finding_idx = len(s['findings']) + 1
finding_file = f'{inv_dir}/{inv_id}/findings/{finding_idx:03d}-{agent}.md'
with open(finding_file, 'w') as f:
    f.write(f'# Finding {finding_idx}: {agent}\n')
    f.write(f'**Timestamp:** {now}\n')
    f.write(f'**Summary:** {summary}\n\n')
    if detail:
        f.write(f'## Detail\n\n{detail}\n')

finding['file'] = finding_file
s['findings'].append(finding)
s['updated_at'] = now
s['timeline'].append({
    'timestamp': now,
    'event': f'Finding from {agent}: {summary}',
    'agent': agent
})

with open(state_file, 'w') as f:
    json.dump(s, f, indent=2)

print(json.dumps({'action': 'added', 'finding_idx': finding_idx, 'agent': agent, 'inv_id': inv_id}, indent=2))
PYEOF
        ;;

    set-status)
        INV_ID="${2:?Usage: investigation.sh set-status <INV-ID> <status>}"
        STATUS="${3:?Missing status (active/contained/eradication/recovery/closed)}"

        python3 - "$INV_DIR" "$INV_ID" "$STATUS" <<'PYEOF'
import json, sys
from datetime import datetime, timezone

inv_dir, inv_id, new_status = sys.argv[1:4]
valid = ['active', 'contained', 'eradication', 'recovery', 'closed', 'monitoring']
if new_status not in valid:
    print(f'{{"error": "Invalid status. Valid: {", ".join(valid)}"}}')
    sys.exit(1)

state_file = f'{inv_dir}/{inv_id}/state.json'
with open(state_file) as f:
    s = json.load(f)

now = datetime.now(timezone.utc).isoformat()
old_status = s['status']
s['status'] = new_status
s['updated_at'] = now
s['timeline'].append({
    'timestamp': now,
    'event': f'Status changed: {old_status} -> {new_status}',
    'agent': 'system'
})

with open(state_file, 'w') as f:
    json.dump(s, f, indent=2)

print(json.dumps({'inv_id': inv_id, 'old_status': old_status, 'new_status': new_status}))
PYEOF
        ;;

    get)
        INV_ID="${2:?Usage: investigation.sh get <INV-ID>}"
        get_state "$INV_ID"
        ;;

    context)
        INV_ID="${2:?Usage: investigation.sh context <INV-ID>}"
        python3 - "$INV_DIR" "$INV_ID" <<'PYEOF'
import json, sys

inv_dir, inv_id = sys.argv[1:3]
state_file = f'{inv_dir}/{inv_id}/state.json'

try:
    with open(state_file) as f:
        s = json.load(f)
except FileNotFoundError:
    print(f'Investigation not found: {inv_id}')
    sys.exit(1)

# Build formatted context for agent handoff
lines = []
lines.append(f'## Active Investigation: {s["id"]}')
lines.append(f'**Title:** {s["title"]}')
lines.append(f'**Status:** {s["status"].upper()}')
lines.append(f'**Created:** {s["created_at"]}')
lines.append('')

if s['iocs']:
    lines.append('### Known IOCs')
    for ioc in s['iocs']:
        risk = ioc.get('risk', '?')
        ctx = f' -- {ioc["context"]}' if ioc.get('context') else ''
        enriched = ' (enriched)' if ioc.get('enriched') else ' (not yet enriched)'
        lines.append(f'- [{ioc["type"]}] {ioc["value"]} (risk: {risk}){enriched}{ctx}')
    lines.append('')

if s['findings']:
    lines.append('### Prior Findings')
    for f in s['findings']:
        lines.append(f'**{f["agent"]}** ({f["timestamp"]}):')
        lines.append(f'{f["summary"]}')
        if f.get('detail'):
            # Include first 500 chars of detail
            detail_preview = f['detail'][:500]
            if len(f['detail']) > 500:
                detail_preview += '...'
            lines.append(detail_preview)
        lines.append('')

if s['timeline']:
    lines.append('### Timeline')
    for evt in s['timeline'][-10:]:  # Last 10 events
        lines.append(f'- {evt["timestamp"]} [{evt["agent"]}] {evt["event"]}')
    if len(s['timeline']) > 10:
        lines.append(f'- ... and {len(s["timeline"]) - 10} earlier events')

print('\n'.join(lines))
PYEOF
        ;;

    list)
        FILTER="${2:---active}"
        python3 - "$INV_DIR" "$FILTER" <<'PYEOF'
import json, sys, os
from datetime import datetime, timezone

inv_dir = sys.argv[1]
filter_flag = sys.argv[2] if len(sys.argv) > 2 else '--active'

if not os.path.isdir(inv_dir):
    print('No investigations found.')
    sys.exit(0)

entries = []
now = datetime.now(timezone.utc)

for name in sorted(os.listdir(inv_dir), reverse=True):
    state_file = os.path.join(inv_dir, name, 'state.json')
    if not os.path.isfile(state_file):
        continue
    try:
        with open(state_file) as f:
            s = json.load(f)
        if filter_flag == '--active' and s['status'] == 'closed':
            continue
        if filter_flag == '--closed' and s['status'] != 'closed':
            continue
        created = datetime.fromisoformat(s['created_at'].replace('Z', '+00:00'))
        age = (now - created).total_seconds() / 3600
        entries.append((
            s['id'], s['status'].upper(), s['title'][:50],
            len(s['iocs']), len(s['findings']), f'{age:.1f}h'
        ))
    except Exception:
        entries.append((name, 'ERROR', '?', 0, 0, '?'))

if not entries:
    scope = 'active' if filter_flag == '--active' else 'closed' if filter_flag == '--closed' else 'any'
    print(f'No {scope} investigations found.')
    sys.exit(0)

print(f'')
print(f'  {"ID":20s}  {"STATUS":12s}  {"TITLE":50s}  {"IOCs":5s}  {"FIND":5s}  {"AGE":8s}')
print(f'  {"--":20s}  {"------":12s}  {"-----":50s}  {"----":5s}  {"----":5s}  {"---":8s}')
for inv_id, status, title, iocs, findings, age in entries:
    print(f'  {inv_id:20s}  {status:12s}  {title:50s}  {iocs:5d}  {findings:5d}  {age:>8s}')
print(f'\n  {len(entries)} investigation(s)')
print(f'')
PYEOF
        ;;

    close)
        INV_ID="${2:?Usage: investigation.sh close <INV-ID> [disposition]}"
        DISPOSITION="${3:-resolved}"

        python3 - "$INV_DIR" "$INV_ID" "$DISPOSITION" <<'PYEOF'
import json, sys
from datetime import datetime, timezone

inv_dir, inv_id, disposition = sys.argv[1:4]
state_file = f'{inv_dir}/{inv_id}/state.json'

try:
    with open(state_file) as f:
        s = json.load(f)
except FileNotFoundError:
    print(f'{{"error": "Investigation not found: {inv_id}"}}')
    sys.exit(1)

now = datetime.now(timezone.utc).isoformat()
s['status'] = 'closed'
s['disposition'] = disposition
s['closed_at'] = now
s['updated_at'] = now
s['timeline'].append({
    'timestamp': now,
    'event': f'Investigation closed: {disposition}',
    'agent': 'system'
})

with open(state_file, 'w') as f:
    json.dump(s, f, indent=2)

print(json.dumps({'inv_id': inv_id, 'status': 'closed', 'disposition': disposition}))
PYEOF
        ;;

    active)
        python3 - "$INV_DIR" <<'PYEOF'
import json, sys, os

inv_dir = sys.argv[1]
if not os.path.isdir(inv_dir):
    print('No active investigation.')
    sys.exit(0)

# Find most recently updated active investigation
active = None
latest = ''
for name in os.listdir(inv_dir):
    state_file = os.path.join(inv_dir, name, 'state.json')
    if not os.path.isfile(state_file):
        continue
    try:
        with open(state_file) as f:
            s = json.load(f)
        if s['status'] != 'closed' and s['updated_at'] > latest:
            active = s
            latest = s['updated_at']
    except Exception:
        continue

if active:
    print(json.dumps({
        'id': active['id'],
        'title': active['title'],
        'status': active['status'],
        'iocs': len(active['iocs']),
        'findings': len(active['findings'])
    }, indent=2))
else:
    print('No active investigation.')
    sys.exit(1)
PYEOF
        ;;

    help|*)
        echo ""
        echo "HOOK Investigation Manager"
        echo ""
        echo "Usage: investigation.sh <command> [args]"
        echo ""
        echo "  create <title>                    Create new investigation"
        echo "  status [INV-ID]                   Show investigation status (or active)"
        echo "  add-ioc <ID> <type> <val> [ctx]   Add IOC to investigation"
        echo "  add-finding <ID> <agent> <summary> Add finding from agent"
        echo "  set-status <ID> <status>          Update status (active/contained/...)"
        echo "  get <ID>                          Full JSON state"
        echo "  context <ID>                      Formatted context for agent handoff"
        echo "  list [--active|--closed|--all]     List investigations"
        echo "  close <ID> [disposition]           Close investigation"
        echo "  active                            Show current active investigation"
        echo ""
        echo "Statuses: active, contained, eradication, recovery, monitoring, closed"
        echo "Dispositions: resolved, false-positive, escalated, inconclusive"
        echo ""
        exit 0
        ;;
esac
