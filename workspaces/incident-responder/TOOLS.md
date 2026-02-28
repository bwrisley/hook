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

## Container Constraints

- No `jq` — use `python3 -c "..."` for JSON parsing
- No `dig` or `whois` — use python3 socket module
- `curl` and `python3` are available
- All API calls must use `exec` tool, NOT `web_fetch`
