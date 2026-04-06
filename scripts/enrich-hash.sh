#!/bin/bash
# enrich-hash.sh — File hash enrichment (VirusTotal)
# Usage: ./scripts/enrich-hash.sh <SHA256|SHA1|MD5>
#        ./scripts/enrich-hash.sh --no-cache <HASH>    (skip cache, force live)
# Output: JSON object with VT findings
# Requires: $VT_API_KEY

set -euo pipefail

NO_CACHE=0
if [ "${1:-}" = "--no-cache" ]; then
    NO_CACHE=1
    shift
fi

HASH="${1:?Usage: enrich-hash.sh [--no-cache] <HASH>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

python3 - "$HASH" "$SCRIPT_DIR" "$NO_CACHE" <<'PYEOF'
import sys, os

hash_arg = sys.argv[1]
script_dir = sys.argv[2]
no_cache = sys.argv[3] == '1'

exec(open(os.path.join(script_dir, 'lib', 'common.py')).read())

SCRIPT = 'enrich-hash'

try:
    file_hash = validate_hash(hash_arg)
except ValueError as e:
    error_exit(SCRIPT, str(e), hash_arg[:80])

# Check cache first
if not no_cache:
    cached, hit = cache_get('hash', file_hash)
    if hit:
        log_info(SCRIPT, f'Cache hit for {file_hash[:16]}...')
        output_json(cached)
        sys.exit(0)

log_info(SCRIPT, f'Starting enrichment for {file_hash[:16]}...')
results = {'ioc': file_hash, 'type': 'hash', 'sources': {}}

vt_key = os.environ.get('VT_API_KEY', '')
if vt_key:
    vt = curl_json([
        'https://www.virustotal.com/api/v3/files/' + file_hash,
        '-H', 'x-apikey: ' + vt_key
    ], api_name='virustotal')
    if 'error' in vt and isinstance(vt.get('error'), dict):
        results['sources']['virustotal'] = {
            'error': vt['error'].get('message', 'not_found'),
            'found': False
        }
    elif 'error' in vt:
        results['sources']['virustotal'] = {'error': vt['error'], 'found': False}
        log_warn(SCRIPT, f'VT lookup failed for hash', vt)
    else:
        attrs = vt.get('data', {}).get('attributes', {})
        stats = attrs.get('last_analysis_stats', {})
        results['sources']['virustotal'] = {
            'found': True,
            'malicious': stats.get('malicious', 0),
            'suspicious': stats.get('suspicious', 0),
            'harmless': stats.get('harmless', 0),
            'undetected': stats.get('undetected', 0),
            'type_description': attrs.get('type_description', 'unknown'),
            'names': attrs.get('names', [])[:10],
            'size': attrs.get('size', 0),
            'sha256': attrs.get('sha256', ''),
            'sha1': attrs.get('sha1', ''),
            'md5': attrs.get('md5', ''),
            'tags': attrs.get('tags', [])[:10],
            'first_seen': attrs.get('first_submission_date', 0),
            'last_seen': attrs.get('last_analysis_date', 0),
            'popular_threat_name': attrs.get('popular_threat_classification', {}).get('suggested_threat_label', 'unknown')
        }
else:
    results['sources']['virustotal'] = {'error': 'no_api_key'}

# AlienVault OTX
otx_key = os.environ.get('OTX_API_KEY', '')
if otx_key:
    rate_limit_wait('otx')
    hash_type = 'FileHash-SHA256' if len(file_hash) == 64 else 'FileHash-MD5' if len(file_hash) == 32 else 'FileHash-SHA1'
    otx = curl_json([
        'https://otx.alienvault.com/api/v1/indicators/file/' + file_hash + '/general',
        '-H', 'X-OTX-API-KEY: ' + otx_key
    ], api_name='otx')
    if 'error' not in otx:
        pulses = otx.get('pulse_info', {})
        pulse_count = pulses.get('count', 0)
        pulse_names = [p.get('name', '') for p in pulses.get('pulses', [])[:5]]
        pulse_tags = []
        for p in pulses.get('pulses', [])[:10]:
            pulse_tags.extend(p.get('tags', []))
        pulse_tags = list(set(pulse_tags))[:10]
        results['sources']['otx'] = {
            'pulse_count': pulse_count,
            'pulse_names': pulse_names,
            'tags': pulse_tags,
        }
    else:
        results['sources']['otx'] = otx
        log_warn(SCRIPT, f'OTX lookup failed for {file_hash[:16]}', otx)
else:
    results['sources']['otx'] = {'error': 'no_api_key'}

# Risk assessment
vt_data = results['sources'].get('virustotal', {})
vt_mal = vt_data.get('malicious', 0)
otx_pulses = results['sources'].get('otx', {}).get('pulse_count', 0)
if not vt_data.get('found', True):
    results['risk'] = 'UNKNOWN'
elif vt_mal > 10 or otx_pulses > 5:
    results['risk'] = 'HIGH'
elif vt_mal > 0 or otx_pulses > 0:
    results['risk'] = 'MEDIUM'
else:
    results['risk'] = 'LOW'

# Cache the result
cache_put('hash', file_hash, results)

log_info(SCRIPT, f'Enrichment complete for {file_hash[:16]}...', {'risk': results['risk']})
output_json(results)
PYEOF
