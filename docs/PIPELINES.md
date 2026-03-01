# HOOK Lobster Pipelines

Deterministic enrichment pipelines that run without LLM tokens. These complement the agent-based chains — use pipelines for structured data retrieval, agents for judgment and analysis.

## Prerequisites

1. Install Lobster CLI: `npm install -g @openclaw/lobster` (or see [Lobster repo](https://github.com/openclaw/lobster))
2. Ensure `lobster` is on PATH (`which lobster` should return a path)
3. Restart gateway: `openclaw gateway stop && openclaw gateway start`
4. Lobster is auto-detected when the CLI is on PATH — no config changes needed

## Available Pipelines

### `ioc-enrich-ip.yaml` — Single IP Enrichment
Sources: VirusTotal + AbuseIPDB + Censys + DNS (reverse)

```
@HOOK run lobster pipeline pipelines/ioc-enrich-ip.yaml with ip=45.77.65.211
```

Output: JSON with per-source findings + risk level (HIGH/MEDIUM/LOW)

### `ioc-enrich-domain.yaml` — Single Domain Enrichment
Sources: VirusTotal + DNS (A/MX/NS/TXT/DMARC) + WHOIS

```
@HOOK run lobster pipeline pipelines/ioc-enrich-domain.yaml with domain=evil-update.com
```

### `alert-to-report.yaml` — Full Alert Pipeline
Steps: Ingest alert → Extract IOCs → Enrich all (batch) → Format report

```
@HOOK run lobster pipeline pipelines/alert-to-report.yaml with alert_text="Suspicious connection..."
```

This is the deterministic equivalent of triage → OSINT → report, minus the LLM judgment. It extracts and enriches IOCs but does not provide a verdict — for that, chain the output to `triage-analyst`.

### `batch-ioc-check.yaml` — Batch IOC File Check
Process a file of IOCs (one per line, auto-detects type).

```
@HOOK run lobster pipeline pipelines/batch-ioc-check.yaml with ioc_file=feeds/daily-iocs.txt
```

Good for scheduled threat feed processing via cron.

## Scripts

The pipelines use helper scripts in `scripts/`:

| Script | Input | Output | What it does |
|---|---|---|---|
| `enrich-ip.sh` | IP address (arg) | JSON | VT + AbuseIPDB + Censys + DNS |
| `enrich-domain.sh` | Domain (arg) | JSON | VT + DNS + WHOIS |
| `enrich-hash.sh` | Hash (arg) | JSON | VT file lookup |
| `extract-iocs.sh` | Text (stdin) | JSON | Regex extraction of IPs, domains, hashes |
| `enrich-batch.sh` | IOC JSON (stdin) | JSON | Calls enrich scripts for each IOC |
| `format-report.sh` | Enrichment JSON (stdin) | JSON + Markdown | Formats enrichment into readable report |

All scripts can also be run standalone:
```bash
./scripts/enrich-ip.sh 8.8.8.8
echo "Check 45.77.65.211 and evil.com" | ./scripts/extract-iocs.sh
```

## Hybrid Patterns

### Lobster enrich → Agent analyze
1. Run `alert-to-report` pipeline for fast, structured enrichment
2. Coordinator reads the pipeline output
3. Coordinator spawns `threat-intel` with enrichment data for attribution analysis
4. Coordinator spawns `report-writer` with combined findings

### Scheduled cron → Lobster → Agent alert
Set up a cron job to run `batch-ioc-check` hourly against a threat feed. If any HIGH risk IOCs are found, the cron job triggers an agent turn for investigation.

## Environment Variables

All scripts require these (set in `openclaw.json` `env` section):
- `$VT_API_KEY` — VirusTotal API key
- `$ABUSEIPDB_API_KEY` — AbuseIPDB API key
- `$CENSYS_API_ID` — Censys API ID
- `$CENSYS_API_SECRET` — Censys API secret
