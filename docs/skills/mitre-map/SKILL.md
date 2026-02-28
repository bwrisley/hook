# MITRE ATT&CK Mapping Skill — Reference Documentation

## Overview
Reference for mapping observed adversary behaviors to MITRE ATT&CK framework tactics and techniques.

## Common Mappings for SOC Alerts

| Observable | Tactic | Technique | ID |
|-----------|--------|-----------|-----|
| Phishing email with attachment | Initial Access | Phishing: Spearphishing Attachment | T1566.001 |
| Phishing email with link | Initial Access | Phishing: Spearphishing Link | T1566.002 |
| Macro execution in Office doc | Execution | User Execution: Malicious File | T1204.002 |
| PowerShell encoded command | Execution | Command and Scripting: PowerShell | T1059.001 |
| Rundll32 execution | Defense Evasion | System Binary Proxy Execution: Rundll32 | T1218.011 |
| Registry Run key added | Persistence | Boot or Logon Autostart: Registry Run Keys | T1547.001 |
| Scheduled task created | Persistence | Scheduled Task/Job: Scheduled Task | T1053.005 |
| LSASS memory access | Credential Access | OS Credential Dumping: LSASS Memory | T1003.001 |
| Kerberoasting | Credential Access | Steal or Forge Kerberos Tickets: Kerberoasting | T1558.003 |
| RDP lateral movement | Lateral Movement | Remote Services: Remote Desktop Protocol | T1021.001 |
| PsExec usage | Lateral Movement | Remote Services: SMB/Windows Admin Shares | T1021.002 |
| Data staged for exfil | Collection | Data Staged: Local Data Staging | T1074.001 |
| HTTPS C2 beaconing | Command and Control | Application Layer Protocol: Web Protocols | T1071.001 |
| DNS tunneling | Command and Control | Application Layer Protocol: DNS | T1071.004 |
| Data exfiltration over C2 | Exfiltration | Exfiltration Over C2 Channel | T1041 |
| File encryption (ransomware) | Impact | Data Encrypted for Impact | T1486 |

## ATT&CK Navigator
For visual attack chain mapping, use: https://mitre-attack.github.io/attack-navigator/
