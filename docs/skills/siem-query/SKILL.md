# SIEM Query Skill — Reference Documentation

## Overview
Reference for common SIEM query patterns used by HOOK agents during alert triage and investigation.

## Microsoft Sentinel (KQL)

### Find related alerts for an entity
```kql
SecurityAlert
| where TimeGenerated > ago(7d)
| where Entities contains "10.20.30.42"
| project TimeGenerated, AlertName, AlertSeverity, Entities
| sort by TimeGenerated desc
```

### Logon activity for compromised account
```kql
SigninLogs
| where TimeGenerated > ago(7d)
| where UserPrincipalName == "jsmith@contoso.com"
| project TimeGenerated, Location, IPAddress, ResultType, AppDisplayName
| sort by TimeGenerated desc
```

## Splunk (SPL)

### Search for C2 traffic
```spl
index=network sourcetype=firewall dest_ip="45.77.65.211"
| stats count by src_ip, dest_port, action
| sort -count
```

### Process execution timeline
```spl
index=endpoint sourcetype=sysmon EventCode=1 host="WKSTN-FIN-042"
| table _time, ParentImage, Image, CommandLine, User
| sort _time
```

## CrowdStrike Falcon (Event Search)

### Detection query
```
event_simpleName:ProcessRollup2 AND ComputerName:"WKSTN-FIN-042"
| select timestamp, FileName, CommandLine, ParentBaseFileName, UserName
```

## Elastic Security (EQL)

### Process tree
```eql
process where host.name == "WKSTN-FIN-042" and
  process.name in ("powershell.exe", "cmd.exe", "rundll32.exe")
| sort @timestamp
```

## Note
These are reference patterns only. HOOK agents cannot directly query SIEMs — they analyze alert data provided by the user. These templates help agents suggest investigation queries the analyst can run.
