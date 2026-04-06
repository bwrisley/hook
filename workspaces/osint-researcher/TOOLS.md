# HOOK OSINT Researcher — TOOLS.md

## API Call Instructions

**Preferred:** Use the enrichment scripts (see "Enrichment Scripts" section below). They handle validation, rate limiting, caching, and structured output automatically.

**Manual:** If you need a specific API call not covered by the scripts, use `exec` tool with `curl`. Do NOT use web_fetch — external APIs block browser requests via Cloudflare.

API keys are available as shell environment variables:
- `$VT_API_KEY` — VirusTotal
- `$CENSYS_API_ID` — Censys API ID
- `$CENSYS_API_SECRET` — Censys API Secret
- `$ABUSEIPDB_API_KEY` — AbuseIPDB
- `$OTX_API_KEY` — AlienVault OTX (community threat intel pulses, MITRE ATT&CK linkage)

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

## DNS & WHOIS Lookups

### Forward DNS (A Record)
```bash
dig {DOMAIN} A +short
```

### All DNS Records
```bash
dig {DOMAIN} ANY +noall +answer
```

### Reverse DNS
```bash
dig -x {IP} +short
```

### MX Records
```bash
dig {DOMAIN} MX +short
```

### NS Records
```bash
dig {DOMAIN} NS +short
```

### TXT Records (SPF, DKIM, DMARC)
```bash
dig {DOMAIN} TXT +short
dig _dmarc.{DOMAIN} TXT +short
```

### WHOIS — Domain
```bash
whois {DOMAIN} | grep -iE "registrar|creation|expir|updated|name server|registrant|status"
```

### WHOIS — IP (Network Owner)
```bash
whois {IP} | grep -iE "orgname|netname|country|cidr|descr|origin"
```

### Fallbacks (if running base image without dig/whois)
```bash
# Forward DNS
python3 -c "
import socket
try:
    results = socket.getaddrinfo('{DOMAIN}', None, socket.AF_INET)
    ips = set(r[4][0] for r in results)
    for ip in sorted(ips): print(f'A Record: {ip}')
except Exception as e: print(f'DNS Error: {e}')
"

# Reverse DNS
python3 -c "
import socket
try:
    result = socket.gethostbyaddr('{IP}')
    print(f'PTR: {result[0]}')
except Exception as e: print(f'Reverse DNS Error: {e}')
"
```

---

## Ad-Hoc JSON Inspection

For quick inspection of raw API responses, use `jq`:
```bash
curl -s "https://www.virustotal.com/api/v3/ip_addresses/{IP}" \
  -H "x-apikey: $VT_API_KEY" | jq '.data.attributes.last_analysis_stats'
```

The full API call scripts above use `python3` for structured extraction, which is still preferred for enrichment reports. Use `jq` when you need to quickly inspect a raw response or debug an API issue.

---

## Enrichment Scripts (Preferred Method)

The enrichment scripts handle validation, rate limiting, caching, and structured output. **Use these instead of raw curl calls whenever possible.**

### IP Enrichment (VT + AbuseIPDB + Censys + DNS)
```bash
exec: /Users/bww/projects/hook/scripts/enrich-ip.sh 45.77.65.211
```

### Domain Enrichment (VT + DNS + WHOIS)
```bash
exec: /Users/bww/projects/hook/scripts/enrich-domain.sh evil-update.com
```

### Hash Enrichment (VT)
```bash
exec: /Users/bww/projects/hook/scripts/enrich-hash.sh e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

### Force Fresh Enrichment (skip cache)
```bash
exec: /Users/bww/projects/hook/scripts/enrich-ip.sh --no-cache 45.77.65.211
exec: /Users/bww/projects/hook/scripts/enrich-domain.sh --no-cache evil-update.com
exec: /Users/bww/projects/hook/scripts/enrich-hash.sh --no-cache abc123def456
```

### Batch Enrichment
```bash
echo '{"ips":["45.77.65.211","8.8.8.8"],"domains":["evil.com"],"hashes":[]}' \
  | /Users/bww/projects/hook/scripts/enrich-batch.sh
```

All scripts return structured JSON with a `risk` field (HIGH/MEDIUM/LOW) and a `sources` object with per-API findings. Cached results include a `_cache` field with `hit: true`, `age_hours`, and `ttl_hours`.

---

## IOC Cache

Enrichment results are cached locally to avoid redundant API calls and conserve rate limits. The cache is checked automatically by the enrichment scripts.

### How it works
- **Location:** `data/cache/{ip,domain,hash}/` (one JSON file per IOC)
- **TTLs:** IPs = 24 hours, domains = 72 hours, hashes = 7 days
- **Cache hit:** Script returns cached result immediately (no API call)
- **Cache miss/stale:** Script performs live enrichment, caches the result
- **Force fresh:** Use `--no-cache` flag to bypass cache

### Cache Management
```bash
# View cache statistics
exec: /Users/bww/projects/hook/scripts/ioc-cache.sh stats

# Look up a specific cached IOC
exec: /Users/bww/projects/hook/scripts/ioc-cache.sh lookup 45.77.65.211

# List all cached IOCs
exec: /Users/bww/projects/hook/scripts/ioc-cache.sh list

# List cached IPs only
exec: /Users/bww/projects/hook/scripts/ioc-cache.sh list ip

# Clear expired entries (safe maintenance)
exec: /Users/bww/projects/hook/scripts/ioc-cache.sh clear --stale

# Clear everything
exec: /Users/bww/projects/hook/scripts/ioc-cache.sh clear
```

### When to use --no-cache
- IOC was previously LOW risk but new intel suggests it may be malicious
- Analyst specifically requests fresh data
- Investigating an active incident where currency matters
- Cache entry is stale but you want immediate results rather than waiting for next enrichment

### Pattern Recognition
When you see the same IOC appearing across multiple enrichment requests, note this in your findings. Repeated IOCs across different alerts may indicate a campaign or persistent threat. Check the cache to see if an IOC has been enriched before and when.

---

## Container Tools

**Custom image (hook-openclaw):** `curl`, `python3`, `jq`, `dig`, `whois`, `nmap`, `ping`, `traceroute`
**Base image (openclaw):** `curl`, `python3` only — use python3 fallbacks above

All API calls must use `exec` tool, NOT `web_fetch` (Cloudflare blocks browser requests).

---

## Behavioral Memory (RAG)

Before enriching an IOC, check two things:

### 1. Past verdicts (have we enriched this IOC before?)
```bash
exec: python3 /Users/bww/projects/hook/scripts/rag-inject.py query "45.77.65.211" --category ioc_verdict --k 3
```

If a recent verdict exists with high confidence, reference it in your analysis rather than re-enriching from scratch.

### 2. Threat feed matches (did this IOC appear in a feed?)
```bash
exec: python3 /Users/bww/projects/hook/scripts/rag-inject.py query "45.77.65.211" --category feed_ioc --k 3
```

If the IOC appeared in a threat feed (Feodo, URLhaus, ThreatFox), flag this prominently in your report — it means the IOC has been independently observed as malicious by external intelligence sources.

### After enrichment, store the verdict:
```bash
exec: python3 /Users/bww/projects/hook/scripts/rag-inject.py store-verdict --ioc "45.77.65.211" --type ip --verdict "HIGH risk, Cobalt Strike C2 beacon" --confidence high
```

This builds HOOK's institutional memory across investigations.
