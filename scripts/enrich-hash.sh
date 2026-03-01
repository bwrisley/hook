#!/bin/bash
# enrich-hash.sh — File hash enrichment (VirusTotal)
# Usage: ./scripts/enrich-hash.sh <SHA256|SHA1|MD5>
# Output: JSON object with VT findings
# Requires: $VT_API_KEY

set -euo pipefail

HASH="${1:?Usage: enrich-hash.sh <HASH>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

python3 - "$HASH" "$SCRIPT_DIR" <<'PYEOF'
import sys, os

script_dir = sys.argv[2]
exec(open(os.path.join(script_dir, 'lib', 'common.py')).read())

SCRIPT = 'enrich-hash'

try:
    file_hash = validate_hash(sys.argv[1])
except ValueError as e:
    error_exit(SCRIPT, str(e), sys.argv[1][:80])

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

# Risk assessment
vt_data = results['sources'].get('virustotal', {})
vt_mal = vt_data.get('malicious', 0)
if not vt_data.get('found', True):
    results['risk'] = 'UNKNOWN'
elif vt_mal > 10:
    results['risk'] = 'HIGH'
elif vt_mal > 0:
    results['risk'] = 'MEDIUM'
else:
    results['risk'] = 'LOW'

log_info(SCRIPT, f'Enrichment complete for {file_hash[:16]}...', {'risk': results['risk']})
output_json(results)
PYEOF
