#!/bin/bash
# enrich-domain.sh — Multi-source domain enrichment (VT + DNS + WHOIS)
# Usage: ./scripts/enrich-domain.sh <DOMAIN>
# Output: JSON object with combined findings
# Requires: $VT_API_KEY

set -euo pipefail

DOMAIN="${1:?Usage: enrich-domain.sh <DOMAIN>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

python3 - "$DOMAIN" "$SCRIPT_DIR" <<'PYEOF'
import sys, os

script_dir = sys.argv[2]
exec(open(os.path.join(script_dir, 'lib', 'common.py')).read())

SCRIPT = 'enrich-domain'

try:
    domain = validate_domain(sys.argv[1])
except ValueError as e:
    error_exit(SCRIPT, str(e), sys.argv[1][:80])

log_info(SCRIPT, f'Starting enrichment for {domain}')
results = {'ioc': domain, 'type': 'domain', 'sources': {}}

# VirusTotal
vt_key = os.environ.get('VT_API_KEY', '')
if vt_key:
    vt = curl_json([
        'https://www.virustotal.com/api/v3/domains/' + domain,
        '-H', 'x-apikey: ' + vt_key
    ], api_name='virustotal')
    if 'error' not in vt:
        attrs = vt.get('data', {}).get('attributes', {})
        stats = attrs.get('last_analysis_stats', {})
        results['sources']['virustotal'] = {
            'malicious': stats.get('malicious', 0),
            'suspicious': stats.get('suspicious', 0),
            'harmless': stats.get('harmless', 0),
            'undetected': stats.get('undetected', 0),
            'registrar': attrs.get('registrar', 'unknown'),
            'creation_date': attrs.get('creation_date', 0),
            'reputation': attrs.get('reputation', 0),
            'categories': attrs.get('categories', {})
        }
    else:
        results['sources']['virustotal'] = vt
        log_warn(SCRIPT, f'VT lookup failed for {domain}', vt)
else:
    results['sources']['virustotal'] = {'error': 'no_api_key'}

# DNS records
dns = {}
for rtype in ['A', 'MX', 'NS', 'TXT']:
    out = run_cmd(['dig', domain, rtype, '+short'])
    dns[rtype.lower()] = out.splitlines() if out else []
dns['dmarc'] = run_cmd(['dig', '_dmarc.' + domain, 'TXT', '+short']).splitlines()
results['sources']['dns'] = dns

# WHOIS
whois_raw = run_cmd(['whois', domain], timeout=10)
whois_parsed = {}
for line in whois_raw.splitlines():
    line_lower = line.lower().strip()
    if 'registrar:' in line_lower or 'registrar name:' in line_lower:
        whois_parsed['registrar'] = line.split(':', 1)[-1].strip()
    elif 'creation date:' in line_lower or 'created:' in line_lower:
        whois_parsed['created'] = line.split(':', 1)[-1].strip()
    elif 'expir' in line_lower and 'date' in line_lower:
        whois_parsed['expires'] = line.split(':', 1)[-1].strip()
    elif 'name server:' in line_lower:
        whois_parsed.setdefault('name_servers', []).append(line.split(':', 1)[-1].strip())
    elif 'registrant country:' in line_lower or 'country:' in line_lower:
        if 'country' not in whois_parsed:
            whois_parsed['country'] = line.split(':', 1)[-1].strip()
results['sources']['whois'] = whois_parsed if whois_parsed else {'error': 'parse_failed'}

# Risk assessment
vt_mal = results['sources'].get('virustotal', {}).get('malicious', 0)
if vt_mal > 5:
    results['risk'] = 'HIGH'
elif vt_mal > 0:
    results['risk'] = 'MEDIUM'
else:
    results['risk'] = 'LOW'

log_info(SCRIPT, f'Enrichment complete for {domain}', {'risk': results['risk']})
output_json(results)
PYEOF
