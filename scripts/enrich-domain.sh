#!/bin/bash
# enrich-domain.sh — Multi-source domain enrichment
# Usage: ./scripts/enrich-domain.sh [options] <DOMAIN>
#   --no-cache           Skip cache, force live queries
#   --source <sources>   Comma-separated: virustotal,dns,whois,otx,urlhaus,threatfox
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

DOMAIN="${1:?Usage: enrich-domain.sh [--no-cache] [--source vt,otx,...] <DOMAIN>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

python3 - "$DOMAIN" "$SCRIPT_DIR" "$NO_CACHE" "$SOURCES" <<'PYEOF'
import sys, os

domain_arg = sys.argv[1]
script_dir = sys.argv[2]
no_cache = sys.argv[3] == '1'
sources_arg = sys.argv[4]

if sources_arg == 'all':
    run_sources = None
else:
    aliases = {'vt': 'virustotal', 'otx': 'otx', 'urlhaus': 'urlhaus', 'threatfox': 'threatfox', 'dns': 'dns', 'whois': 'whois'}
    run_sources = set()
    for s in sources_arg.split(','):
        s = s.strip().lower()
        run_sources.add(aliases.get(s, s))

def should_run(name):
    return run_sources is None or name in run_sources

exec(open(os.path.join(script_dir, 'lib', 'common.py')).read())

SCRIPT = 'enrich-domain'

try:
    domain = validate_domain(domain_arg)
except ValueError as e:
    error_exit(SCRIPT, str(e), domain_arg[:80])

# Check cache first
if not no_cache:
    cached, hit = cache_get('domain', domain)
    if hit:
        log_info(SCRIPT, f'Cache hit for {domain}')
        output_json(cached)
        sys.exit(0)

log_info(SCRIPT, f'Starting enrichment for {domain}')
results = {'ioc': domain, 'type': 'domain', 'sources': {}}

# VirusTotal
vt_key = os.environ.get('VT_API_KEY', '')
if should_run('virustotal') and vt_key:
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
elif should_run('virustotal'):
    results['sources']['virustotal'] = {'error': 'no_api_key'}

# DNS records
if should_run('dns'):
    dns = {}
    for rtype in ['A', 'MX', 'NS', 'TXT']:
        out = run_cmd(['dig', domain, rtype, '+short'])
        dns[rtype.lower()] = out.splitlines() if out else []
    dns['dmarc'] = run_cmd(['dig', '_dmarc.' + domain, 'TXT', '+short']).splitlines()
    results['sources']['dns'] = dns

# WHOIS
if should_run('whois'):
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

# AlienVault OTX
otx_key = os.environ.get('OTX_API_KEY', '')
if should_run('otx') and otx_key:
    rate_limit_wait('otx')
    otx = curl_json([
        'https://otx.alienvault.com/api/v1/indicators/domain/' + domain + '/general',
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
        }
    else:
        results['sources']['otx'] = otx
        log_warn(SCRIPT, f'OTX lookup failed for {domain}', otx)
elif should_run('otx'):
    results['sources']['otx'] = {'error': 'no_api_key'}

# URLhaus (no API key needed)
if should_run('urlhaus'):
    urlhaus = curl_json([
        '-X', 'POST', 'https://urlhaus-api.abuse.ch/v1/host/',
        '-d', 'host=' + domain
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
        '-d', '{"query": "search_ioc", "search_term": "' + domain + '"}'
    ], api_name='threatfox')
    if 'error' not in threatfox and threatfox.get('query_status') == 'ok':
        iocs = threatfox.get('data', [])
        results['sources']['threatfox'] = {
            'found': True,
            'ioc_count': len(iocs) if isinstance(iocs, list) else 0,
            'iocs': [{'malware': i.get('malware', ''), 'threat_type': i.get('threat_type', ''), 'confidence': i.get('confidence_level', 0)} for i in (iocs if isinstance(iocs, list) else [])[:5]],
        }
    else:
        results['sources']['threatfox'] = {'found': False, 'ioc_count': 0}

# Risk assessment
vt_mal = results['sources'].get('virustotal', {}).get('malicious', 0)
otx_pulses = results['sources'].get('otx', {}).get('pulse_count', 0)
urlhaus_listed = results['sources'].get('urlhaus', {}).get('listed', False)
threatfox_found = results['sources'].get('threatfox', {}).get('found', False)
if vt_mal > 5 or otx_pulses > 10 or urlhaus_listed or threatfox_found:
    results['risk'] = 'HIGH'
elif vt_mal > 0 or otx_pulses > 3:
    results['risk'] = 'MEDIUM'
else:
    results['risk'] = 'LOW'

# Cache the result
cache_put('domain', domain, results)

log_info(SCRIPT, f'Enrichment complete for {domain}', {'risk': results['risk']})
output_json(results)
PYEOF
