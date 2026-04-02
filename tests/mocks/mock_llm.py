"""
tests/mocks/mock_llm.py -- Deterministic LLM provider for HOOK tests.

Provides hash-based embeddings and keyword-dispatched chat responses.
All calls are logged for test assertions.
"""
from __future__ import annotations

from tests.mocks.data_generator import deterministic_embed


class MockLLMProvider:
    """Deterministic LLM for testing. No network I/O."""

    def __init__(self, embedding_dims: int = 64) -> None:
        self._embedding_dims = embedding_dims
        self.call_log: list[dict] = []

    @property
    def embedding_dimension(self) -> int:
        return self._embedding_dims

    def embed(self, text: str) -> list[float]:
        """Generate a deterministic embedding vector from text."""
        self.call_log.append({"method": "embed", "text": text[:200]})
        return deterministic_embed(text, self._embedding_dims)

    def chat(self, messages: list[dict]) -> str:
        """Return a keyword-dispatched response based on the last user message."""
        last_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_msg = msg.get("content", "")
                break

        self.call_log.append({"method": "chat", "message": last_msg[:200]})
        return self._dispatch(last_msg)

    def _dispatch(self, text: str) -> str:
        """Match keywords in the input to select a canned response."""
        lower = text.lower()

        if "triage" in lower or "verdict" in lower or "alert" in lower:
            return TRIAGE_RESPONSE

        if "enrich" in lower or "virustotal" in lower or "ioc" in lower:
            return ENRICHMENT_RESPONSE

        if "incident" in lower or "nist" in lower or "containment" in lower:
            return IR_RESPONSE

        if "baseline" in lower or "network" in lower or "traffic" in lower:
            return BASELINE_RESPONSE

        if "threat" in lower or "ach" in lower or "attribution" in lower:
            return THREAT_INTEL_RESPONSE

        if "report" in lower or "executive" in lower or "summary" in lower:
            return REPORT_RESPONSE

        if "opensearch" in lower or "query" in lower or "search" in lower:
            return QUERY_DSL_RESPONSE

        return DEFAULT_RESPONSE


TRIAGE_RESPONSE = """## Triage Verdict

**Verdict:** TRUE_POSITIVE
**Confidence:** High (92%)
**Severity:** High

### Evidence
- Suspicious process execution matches known Cobalt Strike beacon pattern
- C2 callback to known malicious infrastructure
- Lateral movement indicators present

### MITRE ATT&CK Mapping
| Tactic | Technique | ID |
|--------|-----------|-----|
| Execution | PowerShell | T1059.001 |
| Command and Control | Application Layer Protocol | T1071.001 |

### Recommendation
Escalate to incident response. Contain affected host immediately."""

ENRICHMENT_RESPONSE = """{
  "ioc": "45.77.65.211",
  "type": "ip",
  "risk": "HIGH",
  "sources": {
    "virustotal": {"detections": 12, "total": 90, "country": "NL"},
    "abuseipdb": {"confidence": 87, "reports": 34}
  }
}"""

IR_RESPONSE = """## Incident Response Guidance (NIST 800-61)

### Phase: Containment
1. Isolate affected host from network
2. Preserve volatile memory and disk image
3. Block C2 IP at perimeter firewall
4. Reset compromised credentials

### Phase: Eradication
1. Remove malicious artifacts
2. Patch exploited vulnerability
3. Update detection signatures

### Phase: Recovery
1. Restore from known-good backup
2. Monitor for re-infection indicators
3. Gradually restore network access"""

BASELINE_RESPONSE = """### Network Baseline Summary

**Identifier:** sensor-dmz-01
**Period:** Last 6 hours

Traffic patterns:
- HTTP/HTTPS: 85% of traffic (normal)
- DNS queries: 12,400 (within baseline)
- Top destinations: internal CDN, cloud APIs
- Anomalies: None detected

Protocol distribution is consistent with historical baseline."""

THREAT_INTEL_RESPONSE = """## Threat Intelligence Assessment

### Analysis of Competing Hypotheses (ACH)
| Hypothesis | Evidence For | Evidence Against | Confidence |
|------------|-------------|-----------------|------------|
| APT29 (Cozy Bear) | TTP overlap, target profile | Infrastructure mismatch | Medium |
| Cybercriminal (FIN7) | Tooling similarity | No financial motive indicators | Low |

### Key Assumptions Check
- Assumption: C2 infrastructure is dedicated to single actor
- Assessment: MODERATE confidence, shared hosting possible"""

REPORT_RESPONSE = """## Executive Summary

A targeted intrusion was detected affecting one workstation in the Finance department.
The attack chain involved phishing, malware execution, and command-and-control activity.
Immediate containment actions have been taken. No evidence of data exfiltration at this time.

**Risk Level:** High
**Business Impact:** Moderate
**Recommended Actions:** Complete remediation within 24 hours."""

QUERY_DSL_RESPONSE = """{
  "query": {
    "bool": {
      "must": [
        {"match": {"event.action": "denied"}},
        {"range": {"@timestamp": {"gte": "now-24h"}}}
      ]
    }
  },
  "size": 50
}"""

DEFAULT_RESPONSE = "I can help with security analysis. Please provide more context about your query."
