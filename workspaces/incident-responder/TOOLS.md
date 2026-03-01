# HOOK Incident Responder — TOOLS.md

## IOC Enrichment (Quick Checks During IR)

When you need fast reputation data during an active incident:

### VirusTotal IP Quick Check
```bash
curl -s "https://www.virustotal.com/api/v3/ip_addresses/{IP}" \
  -H "x-apikey: $VT_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
attrs = d.get('data', {}).get('attributes', {})
stats = attrs.get('last_analysis_stats', {})
mal = stats.get('malicious', 0)
print(f'IP: {d[\"data\"][\"id\"]} | Malicious: {mal} | Country: {attrs.get(\"country\", \"?\")} | AS: {attrs.get(\"as_owner\", \"?\")}')
if mal > 5: print('⚠️ HIGH RISK — Block immediately')
elif mal > 0: print('⚡ SUSPICIOUS — Investigate further')
else: print('ℹ️ LOW RISK — Continue monitoring')
"
```

### VirusTotal Hash Quick Check
```bash
curl -s "https://www.virustotal.com/api/v3/files/{HASH}" \
  -H "x-apikey: $VT_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'error' in d:
    print(f'Not found: {d[\"error\"][\"message\"]}')
else:
    attrs = d.get('data', {}).get('attributes', {})
    stats = attrs.get('last_analysis_stats', {})
    print(f'Malicious: {stats.get(\"malicious\", 0)} | Type: {attrs.get(\"type_description\", \"?\")} | Names: {\", \".join(attrs.get(\"names\", [])[:5])}')
"
```

### AbuseIPDB Quick Check
```bash
curl -s -G "https://api.abuseipdb.com/api/v2/check" \
  -d "ipAddress={IP}" \
  -d "maxAgeInDays=90" \
  -H "Key: $ABUSEIPDB_API_KEY" \
  -H "Accept: application/json" | python3 -c "
import sys, json
d = json.load(sys.stdin).get('data', {})
score = d.get('abuseConfidenceScore', 0)
print(f'IP: {d.get(\"ipAddress\", \"?\")} | Abuse Score: {score}% | Reports: {d.get(\"totalReports\", 0)} | ISP: {d.get(\"isp\", \"?\")}')
if score > 75: print('⚠️ HIGH ABUSE CONFIDENCE — Known malicious infrastructure')
elif score > 25: print('⚡ MODERATE ABUSE — Investigate')
else: print('ℹ️ LOW ABUSE — Likely clean')
"
```

## Timestamp Conversion

### Epoch to Human-Readable
```bash
python3 -c "
from datetime import datetime, timezone
ts = {EPOCH_TIMESTAMP}
dt = datetime.fromtimestamp(ts, tz=timezone.utc)
print(f'UTC: {dt.strftime(\"%Y-%m-%d %H:%M:%S UTC\")}')
print(f'ISO: {dt.isoformat()}')
"
```

### Timeline Builder
```bash
python3 -c "
events = [
    # Add events as (timestamp_epoch, description) tuples
    (1709136000, 'Initial phishing email received'),
    (1709137800, 'User clicked malicious link'),
    (1709138400, 'Malware executed on workstation'),
]
from datetime import datetime, timezone
events.sort(key=lambda x: x[0])
print('=== Incident Timeline ===')
for ts, desc in events:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    print(f'{dt.strftime(\"%Y-%m-%d %H:%M UTC\")} | {desc}')
"
```

## Shell Environment

API keys available as environment variables:
- `$VT_API_KEY` — VirusTotal
- `$CENSYS_API_ID` — Censys API ID
- `$CENSYS_API_SECRET` — Censys API Secret
- `$ABUSEIPDB_API_KEY` — AbuseIPDB

## Network Reconnaissance

### Port Scan — Quick (Top 100 ports)
```bash
nmap -T4 --top-ports 100 {IP}
```

### Port Scan — Specific Ports
```bash
nmap -p 22,80,443,445,3389,8080,8443 {IP}
```

### Service Version Detection
```bash
nmap -sV -p {PORT} {IP}
```

### Connectivity Check
```bash
ping -c 3 -W 2 {IP}
```

### Route Trace (identify network hops to C2)
```bash
traceroute -m 20 -w 2 {IP}
```

### DNS Lookups
```bash
# Reverse DNS for IP
dig -x {IP} +short

# Forward DNS for domain
dig {DOMAIN} A +short

# Check for DNS tunneling indicators (high TXT record volume)
dig {DOMAIN} TXT +short
```

### WHOIS (IP ownership during IR)
```bash
whois {IP} | grep -iE "orgname|netname|country|cidr|descr|abuse"
```

**Note:** Use nmap judiciously during active IR — scanning attacker infrastructure may alert the threat actor. Prefer passive methods (VT, Censys, AbuseIPDB) when stealth matters.

## Container Tools

**Custom image (hook-openclaw):** `curl`, `python3`, `jq`, `dig`, `whois`, `nmap`, `ping`, `traceroute`
**Base image (openclaw):** `curl`, `python3` only — network recon tools unavailable

All API calls must use `exec` tool, NOT `web_fetch`.
