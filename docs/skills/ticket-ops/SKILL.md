# Ticket Operations Skill — Reference Documentation

## Overview
Reference for security incident ticketing best practices. HOOK agents recommend ticket content — they do not create tickets directly.

## Incident Ticket Template

```
Title: [SEVERITY] [TYPE] — [Brief Description]
Example: [P2] Credential Compromise — jsmith@contoso.com

Priority: P1/P2/P3/P4
Category: [Malware / Phishing / Credential Compromise / Data Exfil / Ransomware / Insider / Policy Violation]
Status: [New / Investigating / Contained / Eradicated / Recovered / Closed]

Affected Systems: [hostnames, IPs, count]
Affected Users: [usernames, count]
IOCs: [list with types]

Timeline:
- [timestamp] [event]

Current Actions:
- [what's been done]

Next Steps:
- [what needs to happen]

Assigned To: [analyst / team]
Escalation Path: [who to contact if needed]
```

## Severity Mapping

| HOOK Verdict | Ticket Priority | SLA |
|-------------|----------------|-----|
| Critical (P1) | Sev-1 / P1 | 15 min response |
| High (P2) | Sev-2 / P2 | 1 hour response |
| Medium (P3) | Sev-3 / P3 | 4 hour response |
| Low (P4) | Sev-4 / P4 | Next business day |
