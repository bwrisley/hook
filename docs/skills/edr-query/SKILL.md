# EDR Query Skill — Reference Documentation

## Overview
Reference patterns for querying common EDR platforms during investigations. HOOK agents analyze EDR output provided by the user — they cannot query EDRs directly.

## CrowdStrike Falcon
- **Host containment:** Falcon Console → Host Management → Network Contain
- **RTR (Real-Time Response):** Live forensic shell on endpoint
- **Detection details:** Detection ID → Full process tree + command lines
- **Key fields:** `aid` (sensor ID), `ComputerName`, `CommandLine`, `ParentBaseFileName`

## Microsoft Defender for Endpoint
- **Isolate device:** Security Center → Device page → Isolate device
- **Live response:** Initiate live response session for forensics
- **Advanced hunting (KQL):** `DeviceProcessEvents`, `DeviceNetworkEvents`, `DeviceFileEvents`
- **Key fields:** `DeviceName`, `InitiatingProcessCommandLine`, `RemoteIP`

## Carbon Black (VMware)
- **Isolate sensor:** Console → Endpoints → Quarantine
- **Live Query:** Real-time OSQL queries on endpoints
- **Process tree:** Alert → Process Analysis → Full tree
- **Key fields:** `device_name`, `process_name`, `process_cmdline`

## SentinelOne
- **Network quarantine:** Console → Sentinels → Actions → Disconnect from network
- **Remote shell:** Deep Visibility → Remote Shell
- **Key fields:** `agentComputerName`, `processName`, `processCommandLine`

## Elastic Defend
- **Host isolation:** Security → Endpoints → Isolate host
- **Osquery:** Live queries via Fleet
- **Event search:** EQL or KQL in Security app
- **Key fields:** `host.name`, `process.name`, `process.command_line`
