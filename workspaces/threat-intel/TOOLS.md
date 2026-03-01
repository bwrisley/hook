# HOOK Threat Intel — TOOLS.md

## IOC Enrichment for Attribution

When performing attribution analysis, use these tools to gather technical intelligence:

### VirusTotal — Relationships (Communicating Files, Downloaded Files)
```bash
curl -s "https://www.virustotal.com/api/v3/ip_addresses/{IP}/communicating_files?limit=10" \
  -H "x-apikey: $VT_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
files = d.get('data', [])
print(f'=== Files communicating with IP ({len(files)} results) ===')
for f in files:
    attrs = f.get('attributes', {})
    stats = attrs.get('last_analysis_stats', {})
    print(f'  SHA256: {attrs.get(\"sha256\", \"?\")[:16]}...')
    print(f'  Type: {attrs.get(\"type_description\", \"?\")} | Malicious: {stats.get(\"malicious\", 0)}')
    print(f'  Names: {\", \".join(attrs.get(\"names\", [])[:3])}')
    print()
"
```

### VirusTotal — Domain Subdomains
```bash
curl -s "https://www.virustotal.com/api/v3/domains/{DOMAIN}/subdomains?limit=20" \
  -H "x-apikey: $VT_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
subs = d.get('data', [])
print(f'=== Subdomains ({len(subs)} results) ===')
for s in subs:
    print(f'  {s.get(\"id\", \"?\")}')
"
```

### VirusTotal — Domain Resolutions (Passive DNS)
```bash
curl -s "https://www.virustotal.com/api/v3/domains/{DOMAIN}/resolutions?limit=20" \
  -H "x-apikey: $VT_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
resolutions = d.get('data', [])
print(f'=== DNS Resolutions ({len(resolutions)}) ===')
for r in resolutions:
    attrs = r.get('attributes', {})
    print(f'  {attrs.get(\"date\", \"?\")} → {attrs.get(\"ip_address\", \"?\")}')
"
```

### Censys — Infrastructure Mapping
```bash
curl -s -u "$CENSYS_API_ID:$CENSYS_API_SECRET" \
  "https://search.censys.io/api/v2/hosts/{IP}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
r = d.get('result', {})
print('=== Infrastructure Profile ===')
print(f'IP: {r.get(\"ip\", \"?\")}')
print(f'ASN: {r.get(\"autonomous_system\", {}).get(\"asn\", \"?\")} ({r.get(\"autonomous_system\", {}).get(\"name\", \"?\")})')
print(f'Location: {r.get(\"location\", {}).get(\"city\", \"?\")}, {r.get(\"location\", {}).get(\"country\", \"?\")}')
services = r.get('services', [])
for svc in services:
    port = svc.get('port', '?')
    name = svc.get('service_name', '?')
    software = svc.get('software', [])
    sw_str = ', '.join([s.get('product', '?') for s in software]) if software else 'N/A'
    print(f'  Port {port}: {name} (Software: {sw_str})')
    tls = svc.get('tls', {})
    if tls:
        cert = tls.get('certificates', {}).get('leaf', {}).get('parsed', {})
        issuer = cert.get('issuer', {}).get('organization', ['?'])
        subject_cn = cert.get('subject', {}).get('common_name', ['?'])
        print(f'    TLS Subject: {subject_cn} | Issuer: {issuer}')
"
```

## ACH Matrix Builder (Python)

```bash
python3 -c "
hypotheses = ['APT29', 'APT28', 'Lazarus', 'Cybercrime']
evidence = [
    ('Cobalt Strike C2', ['C', 'C', 'I', 'C']),
    ('Russian-language artifacts', ['C', 'C', 'I', 'N']),
    ('Financial sector targeting', ['I', 'C', 'C', 'C']),
    ('Custom loader via DLL sideload', ['C', 'I', 'C', 'I']),
]
# C=Consistent, I=Inconsistent, N=N/A
print('=== Analysis of Competing Hypotheses ===')
print(f'{\"Evidence\":<35} | {\" | \".join(f\"{h:<10}\" for h in hypotheses)}')
print('-' * 80)
for ev, ratings in evidence:
    print(f'{ev:<35} | {\" | \".join(f\"{r:<10}\" for r in ratings)}')
print()
scores = {h: 0 for h in hypotheses}
for _, ratings in evidence:
    for i, r in enumerate(ratings):
        if r == 'I': scores[hypotheses[i]] -= 1
        elif r == 'C': scores[hypotheses[i]] += 1
print('Scores (higher = more consistent):')
for h in sorted(scores, key=scores.get, reverse=True):
    print(f'  {h}: {scores[h]}')
"
```

## Shell Environment

API keys available as environment variables:
- `$VT_API_KEY` — VirusTotal
- `$CENSYS_API_ID` / `$CENSYS_API_SECRET` — Censys
- `$ABUSEIPDB_API_KEY` — AbuseIPDB

## Infrastructure Analysis

### WHOIS — Domain (registrant, dates, registrar)
```bash
whois {DOMAIN} | grep -iE "registrar|creation|expir|updated|name server|registrant|status|country"
```

### WHOIS — IP (network ownership, hosting provider)
```bash
whois {IP} | grep -iE "orgname|netname|country|cidr|descr|origin|abuse"
```

### DNS Infrastructure Mapping
```bash
# Full DNS record set
dig {DOMAIN} ANY +noall +answer

# Name servers (hosting infrastructure)
dig {DOMAIN} NS +short

# Mail infrastructure
dig {DOMAIN} MX +short

# Check for fast-flux (multiple A records rotating)
dig {DOMAIN} A +short
```

### Passive Infrastructure Pivoting
```bash
# Reverse DNS — what else is hosted on this IP?
dig -x {IP} +short

# TLS certificate subject from Censys (reveals related domains)
curl -s -u "$CENSYS_API_ID:$CENSYS_API_SECRET" \
  "https://search.censys.io/api/v2/hosts/{IP}" | jq '.result.services[].tls.certificates.leaf.parsed.subject'
```

Use these tools to identify infrastructure overlaps between campaigns — shared registrars, hosting providers, name servers, and certificate patterns are strong attribution signals.

## Container Tools

**Custom image (hook-openclaw):** `curl`, `python3`, `jq`, `dig`, `whois`, `nmap`, `ping`, `traceroute`
**Base image (openclaw):** `curl`, `python3` only

All API calls must use `exec` tool, NOT `web_fetch`.
