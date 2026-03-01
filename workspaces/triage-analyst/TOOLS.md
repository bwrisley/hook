# HOOK Triage Analyst — TOOLS.md

## Quick IOC Extraction (Python)

When you receive raw alert data and need to extract IOCs programmatically:

```bash
python3 -c "
import re, sys

text = sys.stdin.read()

# IPv4
ips = set(re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', text))
# Domains
domains = set(re.findall(r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b', text))
# MD5
md5s = set(re.findall(r'\b[a-fA-F0-9]{32}\b', text))
# SHA256
sha256s = set(re.findall(r'\b[a-fA-F0-9]{64}\b', text))
# SHA1
sha1s = set(re.findall(r'\b[a-fA-F0-9]{40}\b', text))
# URLs
urls = set(re.findall(r'https?://[^\s\"<>]+', text))
# Email
emails = set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text))

if ips: print(f'IPs: {\", \".join(sorted(ips))}')
if domains: print(f'Domains: {\", \".join(sorted(domains))}')
if md5s: print(f'MD5: {\", \".join(sorted(md5s))}')
if sha1s: print(f'SHA1: {\", \".join(sorted(sha1s))}')
if sha256s: print(f'SHA256: {\", \".join(sorted(sha256s))}')
if urls: print(f'URLs: {\", \".join(sorted(urls))}')
if emails: print(f'Emails: {\", \".join(sorted(emails))}')
"
```

## Quick VirusTotal Check (Inline — Triage Only)

Use these ONLY when a quick reputation check directly affects your triage verdict (e.g., confirming a hash is known-malicious changes Suspicious → TP). Do NOT run full multi-source enrichment — that's the OSINT researcher's job. If enrichment is needed, say so in your recommendations.

### IP Reputation
```bash
curl -s "https://www.virustotal.com/api/v3/ip_addresses/{IP}" \
  -H "x-apikey: $VT_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
attrs = d.get('data', {}).get('attributes', {})
stats = attrs.get('last_analysis_stats', {})
print(f'Malicious: {stats.get(\"malicious\", 0)} | Suspicious: {stats.get(\"suspicious\", 0)} | Harmless: {stats.get(\"harmless\", 0)}')
print(f'Country: {attrs.get(\"country\", \"N/A\")} | AS: {attrs.get(\"as_owner\", \"N/A\")}')
"
```

### Hash Reputation
```bash
curl -s "https://www.virustotal.com/api/v3/files/{HASH}" \
  -H "x-apikey: $VT_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
attrs = d.get('data', {}).get('attributes', {})
stats = attrs.get('last_analysis_stats', {})
print(f'Malicious: {stats.get(\"malicious\", 0)} | Type: {attrs.get(\"type_description\", \"N/A\")}')
print(f'Names: {\", \".join(attrs.get(\"names\", [])[:])}')
"
```

## Base64 Decoding

```bash
echo "BASE64_STRING_HERE" | python3 -c "
import sys, base64
encoded = sys.stdin.read().strip()
try:
    decoded = base64.b64decode(encoded).decode('utf-8', errors='replace')
    print(decoded)
except Exception as e:
    print(f'Decode error: {e}')
"
```

## Shell Environment

API keys are available as environment variables:
- `$VT_API_KEY` — VirusTotal
- `$CENSYS_API_ID` — Censys API ID
- `$CENSYS_API_SECRET` — Censys API Secret
- `$ABUSEIPDB_API_KEY` — AbuseIPDB

Use `exec` tool with `curl` for all API calls. Do NOT use web_fetch.

## Container Tools

**Custom image (hook-openclaw):** `curl`, `python3`, `jq`, `dig`, `whois`, `nmap`, `ping`, `traceroute`
**Base image (openclaw):** `curl`, `python3` only

`jq` is available for quick JSON inspection during triage:
```bash
echo '$ALERT_JSON' | jq '.Entities[] | select(.Type == "ip")'
```

All API calls must use `exec` tool, NOT `web_fetch`.
