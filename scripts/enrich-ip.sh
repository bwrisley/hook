#!/bin/bash
# enrich-ip.sh — Multi-source IP enrichment (VT + AbuseIPDB + Censys + DNS)
# Usage: ./scripts/enrich-ip.sh <IP>
# Output: JSON object with combined findings
# Requires: $VT_API_KEY, $ABUSEIPDB_API_KEY, $CENSYS_API_ID, $CENSYS_API_SECRET

set -euo pipefail

IP="${1:?Usage: enrich-ip.sh <IP>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

python3 - "$IP" "$SCRIPT_DIR" <<'PYEOF'
import sys, os

# Load shared library
script_dir = sys.argv[2]
exec(open(os.path.join(script_dir, 'lib', 'common.py')).read())

SCRIPT = 'enrich-ip'

# Validate input (prevents shell injection + catches garbage)
try:
    ip = validate_ip(sys.argv[1])
except ValueError as e:
    error_exit(SCRIPT, str(e), sys.argv[1][:80])

log_info(SCRIPT, f'Starting enrichment for {ip}')
results = {'ioc': ip, 'type': 'ip', 'sources': {}}

# VirusTotal
vt_key = os.environ.get('VT_API_KEY', '')
if vt_key:
    vt = curl_json([
        'https://www.virustotal.com/api/v3/ip_addresses/' + ip,
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
            'country': attrs.get('country', 'unknown'),
            'as_owner': attrs.get('as_owner', 'unknown'),
            'asn': attrs.get('asn', 0),
            'network': attrs.get('network', 'unknown')
        }
    else:
        results['sources']['virustotal'] = vt
        log_warn(SCRIPT, f'VT lookup failed for {ip}', vt)
else:
    results['sources']['virustotal'] = {'error': 'no_api_key'}

# AbuseIPDB
abuse_key = os.environ.get('ABUSEIPDB_API_KEY', '')
if abuse_key:
    abuse = curl_json([
        '-G', 'https://api.abuseipdb.com/api/v2/check',
        '-d', 'ipAddress=' + ip,
        '-d', 'maxAgeInDays=90',
        '-H', 'Key: ' + abuse_key,
        '-H', 'Accept: application/json'
    ], api_name='abuseipdb')
    if 'error' not in abuse:
        data = abuse.get('data', {})
        results['sources']['abuseipdb'] = {
            'abuse_confidence': data.get('abuseConfidenceScore', 0),
            'total_reports': data.get('totalReports', 0),
            'isp': data.get('isp', 'unknown'),
            'domain': data.get('domain', 'unknown'),
            'country': data.get('countryCode', 'unknown'),
            'usage_type': data.get('usageType', 'unknown')
        }
    else:
        results['sources']['abuseipdb'] = abuse
        log_warn(SCRIPT, f'AbuseIPDB lookup failed for {ip}', abuse)
else:
    results['sources']['abuseipdb'] = {'error': 'no_api_key'}

# Censys
censys_id = os.environ.get('CENSYS_API_ID', '')
censys_secret = os.environ.get('CENSYS_API_SECRET', '')
if censys_id and censys_secret:
    censys = curl_json([
        '-u', censys_id + ':' + censys_secret,
        'https://search.censys.io/api/v2/hosts/' + ip
    ], api_name='censys')
    if 'error' not in censys:
        result = censys.get('result', {})
        services = result.get('services', [])
        results['sources']['censys'] = {
            'services_count': len(services),
            'ports': [s.get('port', 0) for s in services],
            'service_names': [s.get('service_name', '?') for s in services],
            'os': result.get('operating_system', {}).get('product', 'unknown') if isinstance(result.get('operating_system'), dict) else 'unknown',
            'autonomous_system': result.get('autonomous_system', {}).get('name', 'unknown') if isinstance(result.get('autonomous_system'), dict) else 'unknown'
        }
    else:
        results['sources']['censys'] = censys
        log_warn(SCRIPT, f'Censys lookup failed for {ip}', censys)
else:
    results['sources']['censys'] = {'error': 'no_api_key'}

# DNS (reverse)
ptr = run_cmd(['dig', '-x', ip, '+short'])
results['sources']['dns'] = {'ptr': ptr if ptr else 'none'}

# Risk assessment
vt_mal = results['sources'].get('virustotal', {}).get('malicious', 0)
abuse_score = results['sources'].get('abuseipdb', {}).get('abuse_confidence', 0)
if vt_mal > 5 or abuse_score > 75:
    results['risk'] = 'HIGH'
elif vt_mal > 0 or abuse_score > 25:
    results['risk'] = 'MEDIUM'
else:
    results['risk'] = 'LOW'

log_info(SCRIPT, f'Enrichment complete for {ip}', {'risk': results['risk']})
output_json(results)
PYEOF
