# HOOK Report Writer — TOOLS.md

## Report Generation

The report-writer agent primarily works with text analysis and formatting. Tool usage is minimal but available for:

### Timestamp Formatting
```bash
python3 -c "
from datetime import datetime, timezone
ts = {EPOCH_TIMESTAMP}
dt = datetime.fromtimestamp(ts, tz=timezone.utc)
print(dt.strftime('%Y-%m-%d %H:%M:%S UTC'))
"
```

### IOC Table Formatting
```bash
python3 -c "
iocs = [
    ('IP', '45.77.65.211', 'C2 Server'),
    ('Domain', 'evil-update.com', 'Phishing domain'),
    ('SHA256', 'abc123...', 'Malicious payload'),
]
print('| Type | Value | Context |')
print('|------|-------|---------|')
for ioc_type, value, context in iocs:
    print(f'| {ioc_type} | {value} | {context} |')
"
```

### MITRE ATT&CK Table Formatting
```bash
python3 -c "
ttps = [
    ('Initial Access', 'Phishing', 'Spearphishing Attachment', 'T1566.001'),
    ('Execution', 'Command and Scripting', 'PowerShell', 'T1059.001'),
    ('Persistence', 'Boot or Logon Autostart', 'Registry Run Keys', 'T1547.001'),
]
print('| Tactic | Technique | Sub-Technique | ID |')
print('|--------|-----------|---------------|-----|')
for tactic, tech, sub, tid in ttps:
    print(f'| {tactic} | {tech} | {sub} | {tid} |')
"
```

## Shell Environment

API keys available if enrichment verification is needed:
- `$VT_API_KEY` — VirusTotal
- `$CENSYS_API_ID` / `$CENSYS_API_SECRET` — Censys
- `$ABUSEIPDB_API_KEY` — AbuseIPDB

## Container Tools

**Custom image (hook-openclaw):** `curl`, `python3`, `jq`, `dig`, `whois`, `nmap`, `ping`, `traceroute`
**Base image (openclaw):** `curl`, `python3` only

The report-writer primarily reshapes content from other agents. You rarely need to run tools directly, but `jq` is available if you need to parse structured data passed in your task description.

All API calls must use `exec` tool, NOT `web_fetch`.
