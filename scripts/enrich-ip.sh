#!/bin/bash
# enrich-ip.sh — Multi-source IP enrichment
# Usage: ./scripts/enrich-ip.sh [options] <IP>
#   --no-cache           Skip cache, force live queries
#   --source <sources>   Comma-separated list of sources to query
#                        Options: virustotal,abuseipdb,censys,otx,shodan,urlhaus,threatfox,dns
#                        Default: all
# Output: JSON object with combined findings

set -euo pipefail

NO_CACHE=0
SOURCES="all"
while [[ "${1:-}" == --* ]]; do
    case "$1" in
        --no-cache) NO_CACHE=1; shift ;;
        --source) SOURCES="$2"; shift 2 ;;
        *) shift ;;
    esac
done

IP="${1:?Usage: enrich-ip.sh [--no-cache] [--source vt,shodan,...] <IP>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

python3 - "$IP" "$SCRIPT_DIR" "$NO_CACHE" "$SOURCES" <<'PYEOF'
import sys, os

ip_arg = sys.argv[1]
script_dir = sys.argv[2]
no_cache = sys.argv[3] == '1'
sources_arg = sys.argv[4]

# Parse source filter
if sources_arg == 'all':
    run_sources = None  # run all
else:
    aliases = {'vt': 'virustotal', 'abuse': 'abuseipdb', 'otx': 'otx', 'shodan': 'shodan', 'urlhaus': 'urlhaus', 'threatfox': 'threatfox', 'censys': 'censys', 'dns': 'dns'}
    run_sources = set()
    for s in sources_arg.split(','):
        s = s.strip().lower()
        run_sources.add(aliases.get(s, s))

def should_run(name):
    return run_sources is None or name in run_sources

exec(open(os.path.join(script_dir, 'lib', 'common.py')).read())

SCRIPT = 'enrich-ip'

# Validate input
try:
    ip = validate_ip(ip_arg)
except ValueError as e:
    error_exit(SCRIPT, str(e), ip_arg[:80])

# Check cache first
if not no_cache:
    cached, hit = cache_get('ip', ip)
    if hit:
        log_info(SCRIPT, f'Cache hit for {ip}')
        output_json(cached)
        sys.exit(0)

log_info(SCRIPT, f'Starting enrichment for {ip}')
results = {'ioc': ip, 'type': 'ip', 'sources': {}}

# VirusTotal
vt_key = os.environ.get('VT_API_KEY', '')
if should_run('virustotal') and vt_key:
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
elif should_run('virustotal'):
    results['sources']['virustotal'] = {'error': 'no_api_key'}

# AbuseIPDB
abuse_key = os.environ.get('ABUSEIPDB_API_KEY', '')
if should_run('abuseipdb') and abuse_key:
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
elif should_run('abuseipdb'):
    results['sources']['abuseipdb'] = {'error': 'no_api_key'}

# Censys
censys_id = os.environ.get('CENSYS_API_ID', '')
censys_secret = os.environ.get('CENSYS_API_SECRET', '')
if should_run('censys') and censys_id and censys_secret:
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
elif should_run('censys'):
    results['sources']['censys'] = {'error': 'no_api_key'}

# AlienVault OTX
otx_key = os.environ.get('OTX_API_KEY', '')
if should_run('otx') and otx_key:
    rate_limit_wait('otx')
    otx = curl_json([
        'https://otx.alienvault.com/api/v1/indicators/IPv4/' + ip + '/general',
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
        # Check for MITRE ATT&CK references
        attack_ids = []
        for p in pulses.get('pulses', [])[:10]:
            for ind in p.get('attack_ids', []):
                if isinstance(ind, dict):
                    attack_ids.append(ind.get('id', ''))
                elif isinstance(ind, str):
                    attack_ids.append(ind)
        attack_ids = list(set(attack_ids))[:10]
        results['sources']['otx'] = {
            'pulse_count': pulse_count,
            'pulse_names': pulse_names,
            'tags': pulse_tags,
            'attack_ids': attack_ids,
            'reputation': otx.get('reputation', 0),
            'country': otx.get('country_name', 'unknown'),
        }
    else:
        results['sources']['otx'] = otx
        log_warn(SCRIPT, f'OTX lookup failed for {ip}', otx)
elif should_run('otx'):
    results['sources']['otx'] = {'error': 'no_api_key'}

# Shodan
shodan_key = os.environ.get('SHODAN_API_KEY', '')
if should_run('shodan') and shodan_key:
    rate_limit_wait('shodan')
    shodan = curl_json([
        'https://api.shodan.io/shodan/host/' + ip + '?key=' + shodan_key
    ], api_name='shodan')
    if 'error' not in shodan:
        ports = shodan.get('ports', [])
        vulns = shodan.get('vulns', [])
        services = []
        for svc in shodan.get('data', [])[:10]:
            services.append({
                'port': svc.get('port', 0),
                'transport': svc.get('transport', 'tcp'),
                'product': svc.get('product', ''),
                'version': svc.get('version', ''),
                'module': svc.get('_shodan', {}).get('module', ''),
            })
        results['sources']['shodan'] = {
            'ports': ports,
            'vulns': vulns[:10],
            'services': services,
            'os': shodan.get('os', 'unknown'),
            'org': shodan.get('org', 'unknown'),
            'isp': shodan.get('isp', 'unknown'),
            'hostnames': shodan.get('hostnames', []),
            'last_update': shodan.get('last_update', ''),
        }
    else:
        results['sources']['shodan'] = shodan
        log_warn(SCRIPT, f'Shodan lookup failed for {ip}', shodan)
elif should_run('shodan'):
    results['sources']['shodan'] = {'error': 'no_api_key'}

# URLhaus (no API key needed)
if should_run('urlhaus'):
    urlhaus = curl_json([
        '-X', 'POST', 'https://urlhaus-api.abuse.ch/v1/host/',
        '-d', 'host=' + ip
    ], api_name='urlhaus')
    if 'error' not in urlhaus and urlhaus.get('query_status') == 'is_listed':
        urls = urlhaus.get('urls', [])
        results['sources']['urlhaus'] = {
            'listed': True,
            'url_count': urlhaus.get('url_count', 0),
            'urls': [{'url': u.get('url', ''), 'status': u.get('url_status', ''), 'threat': u.get('threat', ''), 'tags': u.get('tags', [])} for u in urls[:5]],
        }
    else:
        results['sources']['urlhaus'] = {'listed': False, 'url_count': 0}

# ThreatFox (no API key needed)
if should_run('threatfox'):
    threatfox = curl_json([
        '-X', 'POST', 'https://threatfox-api.abuse.ch/api/v1/',
        '-H', 'Content-Type: application/json',
        '-d', '{"query": "search_ioc", "search_term": "' + ip + '"}'
    ], api_name='threatfox')
    if 'error' not in threatfox and threatfox.get('query_status') == 'ok':
        iocs = threatfox.get('data', [])
        results['sources']['threatfox'] = {
            'found': True,
            'ioc_count': len(iocs) if isinstance(iocs, list) else 0,
            'iocs': [{'malware': i.get('malware', ''), 'threat_type': i.get('threat_type', ''), 'confidence': i.get('confidence_level', 0), 'first_seen': i.get('first_seen_utc', '')} for i in (iocs if isinstance(iocs, list) else [])[:5]],
        }
    else:
        results['sources']['threatfox'] = {'found': False, 'ioc_count': 0}

# DNS (reverse)
if should_run('dns'):
    ptr = run_cmd(['dig', '-x', ip, '+short'])
    results['sources']['dns'] = {'ptr': ptr if ptr else 'none'}

# Risk assessment
vt_mal = results['sources'].get('virustotal', {}).get('malicious', 0)
abuse_score = results['sources'].get('abuseipdb', {}).get('abuse_confidence', 0)
otx_pulses = results['sources'].get('otx', {}).get('pulse_count', 0)
shodan_vulns = len(results['sources'].get('shodan', {}).get('vulns', []))
urlhaus_listed = results['sources'].get('urlhaus', {}).get('listed', False)
threatfox_found = results['sources'].get('threatfox', {}).get('found', False)
if vt_mal > 5 or abuse_score > 75 or otx_pulses > 10 or shodan_vulns > 3 or urlhaus_listed or threatfox_found:
    results['risk'] = 'HIGH'
elif vt_mal > 0 or abuse_score > 25 or otx_pulses > 3 or shodan_vulns > 0:
    results['risk'] = 'MEDIUM'
else:
    results['risk'] = 'LOW'

# Cache the result
cache_put('ip', ip, results)

log_info(SCRIPT, f'Enrichment complete for {ip}', {'risk': results['risk']})
output_json(results)
PYEOF
