# HOOK Coordinator — TOOLS.md

## Agent Routing Tools

### Discover Available Agents
Use the `agents_list` tool to see which specialist agents are available and their IDs.

### Spawn a Specialist Agent
Use `sessions_spawn` to delegate work to a specialist:

```
sessions_spawn(
  task: "Your detailed task description here",
  agentId: "target-agent-id",
  runTimeoutSeconds: 120
)
```

Available agent IDs:
- `triage-analyst` — Alert triage and verdict
- `osint-researcher` — IOC enrichment (VT, Censys, AbuseIPDB)
- `incident-responder` — NIST 800-61 incident response
- `threat-intel` — Finished intelligence and analytic techniques
- `report-writer` — Reports for any audience

### Important Notes
- `sessions_spawn` is non-blocking — it returns immediately with `{ status: "accepted" }`
- The specialist will announce results back to the Slack channel when complete
- You can spawn multiple specialists in parallel if tasks are independent
- For sequential chains (triage → enrich → report), wait for results before spawning next

## Quick Enrichment (Direct — No Specialist Needed)

For simple, single-IOC lookups you can run directly without spawning an agent:

### VirusTotal IP Lookup
```bash
curl -s "https://www.virustotal.com/api/v3/ip_addresses/{IP}" \
  -H "x-apikey: $VT_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
attrs = d.get('data', {}).get('attributes', {})
stats = attrs.get('last_analysis_stats', {})
print(f'IP: {d[\"data\"][\"id\"]}')
print(f'Malicious: {stats.get(\"malicious\", 0)}')
print(f'Suspicious: {stats.get(\"suspicious\", 0)}')
print(f'Harmless: {stats.get(\"harmless\", 0)}')
print(f'Country: {attrs.get(\"country\", \"N/A\")}')
print(f'AS Owner: {attrs.get(\"as_owner\", \"N/A\")}')
"
```

### VirusTotal Domain Lookup
```bash
curl -s "https://www.virustotal.com/api/v3/domains/{DOMAIN}" \
  -H "x-apikey: $VT_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
attrs = d.get('data', {}).get('attributes', {})
stats = attrs.get('last_analysis_stats', {})
print(f'Domain: {d[\"data\"][\"id\"]}')
print(f'Malicious: {stats.get(\"malicious\", 0)}')
print(f'Registrar: {attrs.get(\"registrar\", \"N/A\")}')
print(f'Creation: {attrs.get(\"creation_date\", \"N/A\")}')
"
```

### VirusTotal Hash Lookup
```bash
curl -s "https://www.virustotal.com/api/v3/files/{HASH}" \
  -H "x-apikey: $VT_API_KEY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
attrs = d.get('data', {}).get('attributes', {})
stats = attrs.get('last_analysis_stats', {})
print(f'Hash: {d[\"data\"][\"id\"]}')
print(f'Malicious: {stats.get(\"malicious\", 0)}')
print(f'File Type: {attrs.get(\"type_description\", \"N/A\")}')
print(f'Names: {\", \".join(attrs.get(\"names\", [])[:])}')
"
```

## Shell Environment

API keys are available as environment variables:
- `$VT_API_KEY` — VirusTotal
- `$CENSYS_API_ID` — Censys API ID
- `$CENSYS_API_SECRET` — Censys API Secret
- `$ABUSEIPDB_API_KEY` — AbuseIPDB

Use `exec` tool with `curl` for all API calls. Do NOT use web_fetch — external APIs block browser-style requests.

## JSON Parsing

The container does NOT have `jq`. Always pipe curl output to `python3 -c "..."` for JSON parsing.

## DNS Lookups

The container does NOT have `dig` or `whois`. Use python3:
```bash
python3 -c "
import socket
try:
    result = socket.gethostbyname('example.com')
    print(f'A Record: {result}')
except Exception as e:
    print(f'Error: {e}')
"
```

For reverse DNS:
```bash
python3 -c "
import socket
try:
    result = socket.gethostbyaddr('8.8.8.8')
    print(f'Hostname: {result[0]}')
except Exception as e:
    print(f'Error: {e}')
"
```
