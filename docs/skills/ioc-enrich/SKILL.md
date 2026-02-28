# IOC Enrichment Skill — Reference Documentation

## Overview
This skill enables automated enrichment of Indicators of Compromise (IOCs) using multiple threat intelligence sources.

## Supported IOC Types
- IPv4 addresses
- Domains / FQDNs
- File hashes (MD5, SHA1, SHA256)
- URLs

## Data Sources
| Source | Endpoint | Rate Limit (Free) | Auth |
|--------|----------|-------------------|------|
| VirusTotal v3 | `/api/v3/ip_addresses/{ip}`, `/api/v3/domains/{domain}`, `/api/v3/files/{hash}` | 4 req/min | API key header |
| Censys v2 | `/api/v2/hosts/{ip}` | 250 req/month | HTTP Basic Auth |
| AbuseIPDB v2 | `/api/v2/check?ipAddress={ip}` | 1000 req/day | API key header |

## Implementation Notes
- All API calls MUST use `exec` + `curl`, NOT `web_fetch`
- JSON parsing MUST use `python3 -c "..."` (no `jq` in container)
- DNS lookups MUST use `python3` socket module (no `dig` in container)
- API keys are injected via `shellEnv` in openclaw.json `env` block
- Refer to each agent's TOOLS.md for working curl patterns

## Enrichment Priority
For time-sensitive triage:
1. VirusTotal (fastest, broadest coverage)
2. AbuseIPDB (quick abuse score for IPs)
3. Censys (infrastructure context, slower)
