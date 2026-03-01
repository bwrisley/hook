#!/bin/bash
# enrich-batch.sh — Enrich all IOCs from extract-iocs.sh output
# Usage: echo '{"iocs":{"ips":["1.2.3.4"],...}}' | ./scripts/enrich-batch.sh
# Output: JSON object with enrichment results for each IOC
# Rate limiting is handled automatically by individual enrichment scripts

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

python3 - "$SCRIPT_DIR" <<'PYEOF'
import json, subprocess, sys, os, time

script_dir = sys.argv[1]
exec(open(os.path.join(script_dir, 'lib', 'common.py')).read())

SCRIPT = 'enrich-batch'
MAX_IOCS = int(os.environ.get('HOOK_MAX_BATCH_IOCS', '50'))

# Read and validate input
try:
    ioc_data = json.load(sys.stdin)
except json.JSONDecodeError as e:
    error_exit(SCRIPT, f'Invalid JSON input: {e}')

iocs = ioc_data.get('iocs', {})
total_count = sum(len(v) for v in iocs.values() if isinstance(v, list))

if total_count == 0:
    output_json({'enrichments': [], 'summary': {'total': 0, 'high': 0, 'medium': 0, 'low': 0, 'unknown': 0, 'errors': 0}})
    sys.exit(0)

if total_count > MAX_IOCS:
    log_warn(SCRIPT, f'Batch size {total_count} exceeds limit {MAX_IOCS}, truncating')

log_info(SCRIPT, f'Starting batch enrichment', {'total_iocs': min(total_count, MAX_IOCS)})

results = {'enrichments': [], 'summary': {'high': 0, 'medium': 0, 'low': 0, 'unknown': 0, 'errors': 0}}
processed = 0

def run_enrich(script, arg):
    try:
        r = subprocess.run(
            ['bash', os.path.join(script_dir, script), arg],
            capture_output=True, text=True, timeout=90,
            env=os.environ.copy()
        )
        if r.stdout.strip():
            return json.loads(r.stdout)
        return {'ioc': arg, 'error': 'no_output', 'stderr': r.stderr[:200]}
    except subprocess.TimeoutExpired:
        log_warn(SCRIPT, f'{script} timed out for {arg[:40]}')
        return {'ioc': arg, 'error': 'timeout'}
    except json.JSONDecodeError:
        log_warn(SCRIPT, f'{script} returned invalid JSON for {arg[:40]}')
        return {'ioc': arg, 'error': 'invalid_json'}
    except Exception as e:
        log_error(SCRIPT, f'{script} failed for {arg[:40]}: {e}')
        return {'ioc': arg, 'error': str(e)[:200]}

def tally(result):
    risk = result.get('risk', 'UNKNOWN').upper()
    if 'error' in result and risk == 'UNKNOWN':
        results['summary']['errors'] += 1
    elif risk == 'HIGH': results['summary']['high'] += 1
    elif risk == 'MEDIUM': results['summary']['medium'] += 1
    elif risk == 'LOW': results['summary']['low'] += 1
    else: results['summary']['unknown'] += 1

# Enrich IPs
for ip in iocs.get('ips', [])[:MAX_IOCS]:
    result = run_enrich('enrich-ip.sh', ip)
    results['enrichments'].append(result)
    tally(result)
    processed += 1

# Enrich domains
for domain in iocs.get('domains', [])[:MAX_IOCS - processed]:
    result = run_enrich('enrich-domain.sh', domain)
    results['enrichments'].append(result)
    tally(result)
    processed += 1

# Enrich hashes (SHA256 first, then SHA1, then MD5)
all_hashes = iocs.get('sha256', []) + iocs.get('sha1', []) + iocs.get('md5', [])
for hash_val in all_hashes[:MAX_IOCS - processed]:
    result = run_enrich('enrich-hash.sh', hash_val)
    results['enrichments'].append(result)
    tally(result)
    processed += 1

results['summary']['total'] = len(results['enrichments'])
log_info(SCRIPT, 'Batch enrichment complete', results['summary'])
output_json(results)
PYEOF
