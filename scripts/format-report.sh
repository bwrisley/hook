#!/bin/bash
# format-report.sh — Format enrichment results into a Slack-friendly markdown report
# Usage: echo '{"enrichments":[...]}' | ./scripts/format-report.sh
# Output: JSON with formatted report text

python3 <<'PYEOF'
import json, sys
from datetime import datetime, timezone

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(json.dumps({'error': f'Invalid JSON input: {str(e)}'}))
    sys.exit(1)

enrichments = data.get('enrichments', [])
summary = data.get('summary', {})

lines = []
lines.append('# IOC Enrichment Report')
lines.append(f'**Generated:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}')
lines.append(f'**IOCs Analyzed:** {summary.get("total", len(enrichments))}')
lines.append(f'**Risk Summary:** 🔴 {summary.get("high", 0)} High | 🟡 {summary.get("medium", 0)} Medium | 🟢 {summary.get("low", 0)} Low | ⚪ {summary.get("unknown", 0)} Unknown')
if summary.get('errors', 0) > 0:
    lines.append(f'**⚠️ Errors:** {summary["errors"]} enrichment(s) failed')
lines.append('')

for e in enrichments:
    ioc = e.get('ioc', '?')
    ioc_type = e.get('type', '?')
    risk = e.get('risk', 'UNKNOWN')
    icon = {'HIGH': '🔴', 'MEDIUM': '🟡', 'LOW': '🟢'}.get(risk, '⚪')

    if 'error' in e and ioc_type == '?':
        lines.append(f'## ⚠️ {ioc} — Error: {e["error"]}')
        lines.append('')
        continue

    lines.append(f'## {icon} {ioc} ({ioc_type}) — {risk}')

    sources = e.get('sources', {})

    # VirusTotal
    vt = sources.get('virustotal', {})
    if 'error' not in vt:
        lines.append(f'**VirusTotal:** {vt.get("malicious", 0)} malicious / {vt.get("suspicious", 0)} suspicious')
        if ioc_type == 'ip':
            lines.append(f'  AS: {vt.get("as_owner", "?")} | Country: {vt.get("country", "?")} | Network: {vt.get("network", "?")}')
        elif ioc_type == 'domain':
            lines.append(f'  Registrar: {vt.get("registrar", "?")} | Reputation: {vt.get("reputation", 0)}')
        elif ioc_type == 'hash':
            if vt.get('found'):
                lines.append(f'  Type: {vt.get("type_description", "?")} | Threat: {vt.get("popular_threat_name", "?")}')
                if vt.get('names'):
                    lines.append(f'  Names: {", ".join(vt["names"][:5])}')
    elif vt.get('error') != 'no_api_key':
        lines.append(f'**VirusTotal:** ⚠️ {vt.get("error", "failed")}')

    # AbuseIPDB
    abuse = sources.get('abuseipdb', {})
    if 'error' not in abuse:
        lines.append(f'**AbuseIPDB:** {abuse.get("abuse_confidence", 0)}% confidence | {abuse.get("total_reports", 0)} reports | ISP: {abuse.get("isp", "?")}')

    # Censys
    censys = sources.get('censys', {})
    if 'error' not in censys:
        ports = censys.get('ports', [])
        lines.append(f'**Censys:** {censys.get("services_count", 0)} services | Ports: {", ".join(str(p) for p in ports[:10])}')

    # DNS
    dns = sources.get('dns', {})
    if isinstance(dns, dict):
        if 'ptr' in dns:
            lines.append(f'**DNS PTR:** {dns["ptr"]}')
        if 'a' in dns and dns['a']:
            lines.append(f'**DNS A:** {", ".join(dns["a"][:5])}')
        if 'mx' in dns and dns['mx']:
            lines.append(f'**DNS MX:** {", ".join(dns["mx"][:3])}')

    # WHOIS
    whois = sources.get('whois', {})
    if 'error' not in whois and whois:
        parts = []
        if whois.get('registrar'): parts.append(f'Registrar: {whois["registrar"]}')
        if whois.get('created'): parts.append(f'Created: {whois["created"]}')
        if whois.get('country'): parts.append(f'Country: {whois["country"]}')
        if parts:
            lines.append(f'**WHOIS:** {" | ".join(parts)}')

    lines.append('')

report_text = '\n'.join(lines)
output = {'report': report_text, 'summary': summary, 'ioc_count': len(enrichments)}
print(json.dumps(output, indent=2))
PYEOF
