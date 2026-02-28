# HOOK OSINT Researcher — TOOLS.md

## API Call Instructions

Use `exec` tool with `curl` for ALL API calls. Do NOT use web_fetch — external APIs block browser requests via Cloudflare.

API keys are available as shell environment variables:
- `$VT_API_KEY` — VirusTotal
- `$CENSYS_API_ID` — Censys API ID
- `$CENSYS_API_SECRET` — Censys API Secret
- `$ABUSEIPDB_API_KEY` — AbuseIPDB

---

## VirusTotal (v3 API)

### IP Address Report
```bash
curl -s "https://www.virustotal.com/api/v3/ip_addresses/{IP}" \
  -H "x-apikey: $VT_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
attrs = d.get('data', {}).get('attributes', {})
stats = attrs.get('last_analysis_stats', {})
print('=== VirusTotal IP Report ===')
print(f'IP: {d[\"data\"][\"id\"]}')
print(f'Malicious: {stats.get(\"malicious\", 0)}')
print(f'Suspicious: {stats.get(\"suspicious\", 0)}')
print(f'Harmless: {stats.get(\"harmless\", 0)}')
print(f'Undetected: {stats.get(\"undetected\", 0)}')
print(f'Country: {attrs.get(\"country\", \"N/A\")}')
print(f'AS Owner: {attrs.get(\"as_owner\", \"N/A\")}')
print(f'ASN: {attrs.get(\"asn\", \"N/A\")}')
print(f'Network: {attrs.get(\"network\", \"N/A\")}')
print(f'Reputation: {attrs.get(\"reputation\", \"N/A\")}')
tags = attrs.get('tags', [])
if tags: print(f'Tags: {\", \".join(tags)}')
"
```

### Domain Report
```bash
curl -s "https://www.virustotal.com/api/v3/domains/{DOMAIN}" \
  -H "x-apikey: $VT_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
attrs = d.get('data', {}).get('attributes', {})
stats = attrs.get('last_analysis_stats', {})
print('=== VirusTotal Domain Report ===')
print(f'Domain: {d[\"data\"][\"id\"]}')
print(f'Malicious: {stats.get(\"malicious\", 0)}')
print(f'Suspicious: {stats.get(\"suspicious\", 0)}')
print(f'Harmless: {stats.get(\"harmless\", 0)}')
print(f'Registrar: {attrs.get(\"registrar\", \"N/A\")}')
print(f'Creation Date: {attrs.get(\"creation_date\", \"N/A\")}')
print(f'Last Update: {attrs.get(\"last_update_date\", \"N/A\")}')
print(f'Reputation: {attrs.get(\"reputation\", \"N/A\")}')
cats = attrs.get('categories', {})
if cats: print(f'Categories: {json.dumps(cats, indent=2)}')
"
```

### File Hash Report
```bash
curl -s "https://www.virustotal.com/api/v3/files/{HASH}" \
  -H "x-apikey: $VT_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'error' in d:
    print(f'Error: {d[\"error\"][\"message\"]}')
    sys.exit(0)
attrs = d.get('data', {}).get('attributes', {})
stats = attrs.get('last_analysis_stats', {})
print('=== VirusTotal File Report ===')
print(f'SHA256: {attrs.get(\"sha256\", \"N/A\")}')
print(f'MD5: {attrs.get(\"md5\", \"N/A\")}')
print(f'Malicious: {stats.get(\"malicious\", 0)}')
print(f'Suspicious: {stats.get(\"suspicious\", 0)}')
print(f'Undetected: {stats.get(\"undetected\", 0)}')
print(f'Type: {attrs.get(\"type_description\", \"N/A\")}')
print(f'Size: {attrs.get(\"size\", \"N/A\")} bytes')
names = attrs.get('names', [])
if names: print(f'Names: {\", \".join(names[:10])}')
tags = attrs.get('tags', [])
if tags: print(f'Tags: {\", \".join(tags)}')
sig = attrs.get('signature_info', {})
if sig: print(f'Signature: {json.dumps(sig, indent=2)}')
"
```

### URL Scan
```bash
# First, get the URL ID (base64url without padding)
URL_ID=$(python3 -c "import base64; print(base64.urlsafe_b64encode('{URL}'.encode()).decode().rstrip('='))")
curl -s "https://www.virustotal.com/api/v3/urls/$URL_ID" \
  -H "x-apikey: $VT_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'error' in d:
    print(f'Error: {d[\"error\"][\"message\"]}')
    sys.exit(0)
attrs = d.get('data', {}).get('attributes', {})
stats = attrs.get('last_analysis_stats', {})
print('=== VirusTotal URL Report ===')
print(f'URL: {attrs.get(\"url\", \"N/A\")}')
print(f'Malicious: {stats.get(\"malicious\", 0)}')
print(f'Suspicious: {stats.get(\"suspicious\", 0)}')
print(f'Final URL: {attrs.get(\"last_final_url\", \"N/A\")}')
print(f'Title: {attrs.get(\"title\", \"N/A\")}')
"
```

**Rate Limit:** VirusTotal free tier = 4 requests/minute. Add `sleep 15` between calls if enriching multiple IOCs.

---

## Censys (v2 API — hosts endpoint ONLY)

⚠️ Use ONLY the `/v2/hosts/{IP}` endpoint. Do NOT use `/v1/` or `/v2/hosts/search`.

### Host Lookup
```bash
curl -s -u "$CENSYS_API_ID:$CENSYS_API_SECRET" \
  "https://search.censys.io/api/v2/hosts/{IP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
r = d.get('result', {})
print('=== Censys Host Report ===')
print(f'IP: {r.get(\"ip\", \"N/A\")}')
print(f'AS Name: {r.get(\"autonomous_system\", {}).get(\"name\", \"N/A\")}')
print(f'ASN: {r.get(\"autonomous_system\", {}).get(\"asn\", \"N/A\")}')
print(f'Country: {r.get(\"location\", {}).get(\"country\", \"N/A\")}')
print(f'City: {r.get(\"location\", {}).get(\"city\", \"N/A\")}')
print(f'OS: {r.get(\"operating_system\", {}).get(\"product\", \"N/A\")}')
services = r.get('services', [])
print(f'Services ({len(services)}):')
for svc in services:
    port = svc.get('port', '?')
    proto = svc.get('transport_protocol', '?')
    name = svc.get('service_name', '?')
    print(f'  - {port}/{proto} ({name})')
    if 'tls' in svc:
        cn = svc['tls'].get('certificates', {}).get('leaf', {}).get('parsed', {}).get('subject', {}).get('common_name', ['N/A'])
        if cn: print(f'    TLS CN: {cn}')
"
```

---

## AbuseIPDB (v2 API)

### IP Check
```bash
curl -s -G "https://api.abuseipdb.com/api/v2/check" \
  -d "ipAddress={IP}" \
  -d "maxAgeInDays=90" \
  -d "verbose" \
  -H "Key: $ABUSEIPDB_API_KEY" \
  -H "Accept: application/json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
data = d.get('data', {})
print('=== AbuseIPDB Report ===')
print(f'IP: {data.get(\"ipAddress\", \"N/A\")}')
print(f'Abuse Confidence: {data.get(\"abuseConfidenceScore\", \"N/A\")}%')
print(f'Total Reports: {data.get(\"totalReports\", 0)}')
print(f'ISP: {data.get(\"isp\", \"N/A\")}')
print(f'Usage Type: {data.get(\"usageType\", \"N/A\")}')
print(f'Domain: {data.get(\"domain\", \"N/A\")}')
print(f'Country: {data.get(\"countryCode\", \"N/A\")}')
print(f'Is Tor: {data.get(\"isTor\", False)}')
print(f'Is Whitelisted: {data.get(\"isWhitelisted\", False)}')
reports = data.get('reports', [])
if reports:
    print(f'Recent Reports ({len(reports)}):')
    for r in reports[:5]:
        cats = r.get('categories', [])
        print(f'  - {r.get(\"reportedAt\", \"?\")} | Categories: {cats} | {r.get(\"comment\", \"\")}')
"
```

---

## DNS Lookups (Python — no dig/whois in container)

### Forward DNS (A Record)
```bash
python3 -c "
import socket
try:
    results = socket.getaddrinfo('{DOMAIN}', None, socket.AF_INET)
    ips = set(r[4][0] for r in results)
    for ip in sorted(ips):
        print(f'A Record: {ip}')
except Exception as e:
    print(f'DNS Error: {e}')
"
```

### Reverse DNS
```bash
python3 -c "
import socket
try:
    result = socket.gethostbyaddr('{IP}')
    print(f'PTR: {result[0]}')
    if result[1]: print(f'Aliases: {\", \".join(result[1])}')
except Exception as e:
    print(f'Reverse DNS Error: {e}')
"
```

### MX Records
```bash
python3 -c "
import subprocess, re
result = subprocess.run(['python3', '-c', '''
import dns.resolver
try:
    answers = dns.resolver.resolve(\"{DOMAIN}\", \"MX\")
    for r in answers:
        print(f\"MX: {r.preference} {r.exchange}\")
except Exception as e:
    print(f\"MX lookup failed (dnspython not installed): {e}\")
'''], capture_output=True, text=True)
if result.stdout: print(result.stdout)
else: print('MX lookup requires dnspython — not available in base container. Use custom Docker image.')
"
```

---

## Container Constraints

- No `jq` — always use `python3 -c "..."` for JSON parsing
- No `dig`, `nslookup`, `whois` — use python3 socket module for basic DNS
- No `nmap` — use curl or python3 for connectivity tests
- `curl` and `python3` are available
- All API calls must use `exec` tool, NOT `web_fetch`
