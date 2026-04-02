"""
tests/mocks/data_generator.py -- Synthetic data generators for HOOK tests.

Provides deterministic test data: alerts, IOCs, enrichment results,
investigation state, and reproducible embeddings.
"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timezone, timedelta
from typing import Optional


def deterministic_embed(text: str, dims: int = 64) -> list[float]:
    """Generate a deterministic embedding vector from text via SHA-256 hashing.

    Produces a unit-normalized vector of the specified dimensionality.
    Same text always yields the same vector.
    """
    digest = hashlib.sha256(text.encode()).digest()
    raw = []
    for i in range(dims):
        byte_idx = i % len(digest)
        raw.append((digest[byte_idx] + i * 31) % 256 / 255.0 * 2 - 1)
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


def generate_alert(
    severity: str = "High",
    alert_type: str = "Malware",
    seed: int = 0,
) -> dict:
    """Generate a realistic Sentinel-style alert dict."""
    rng = random.Random(seed)
    src_ip = f"10.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}"
    dst_ip = f"{rng.randint(1,223)}.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}"
    ts = datetime.now(timezone.utc) - timedelta(hours=rng.randint(1, 48))

    alert_types = {
        "Malware": {
            "name": f"Suspicious Process Execution on WKSTN-{rng.randint(100,999)}",
            "tactics": ["Execution", "Defense Evasion"],
            "technique": "T1059.001",
        },
        "C2": {
            "name": f"Beacon Activity to Known C2 Infrastructure",
            "tactics": ["Command and Control"],
            "technique": "T1071.001",
        },
        "Phishing": {
            "name": f"Suspicious Email Attachment Opened",
            "tactics": ["Initial Access"],
            "technique": "T1566.001",
        },
        "LateralMovement": {
            "name": f"Unusual SMB Activity from {src_ip}",
            "tactics": ["Lateral Movement"],
            "technique": "T1021.002",
        },
    }

    info = alert_types.get(alert_type, alert_types["Malware"])
    return {
        "alert_id": f"AL-{rng.randint(10000,99999)}",
        "alert_name": info["name"],
        "severity": severity,
        "timestamp": ts.isoformat(),
        "source_ip": src_ip,
        "destination_ip": dst_ip,
        "tactics": info["tactics"],
        "technique_id": info["technique"],
        "hostname": f"WKSTN-{rng.choice(['FIN','ENG','MKT','HR'])}-{rng.randint(1,99):03d}",
        "username": rng.choice(["jsmith", "agarcia", "bwilson", "clee", "dmartinez"]),
        "status": "New",
    }


def generate_ioc(ioc_type: str = "ip", seed: int = 0) -> dict:
    """Generate a random IOC of the given type."""
    rng = random.Random(seed)
    if ioc_type == "ip":
        value = f"{rng.randint(1,223)}.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}"
    elif ioc_type == "domain":
        words = ["evil", "dark", "shadow", "storm", "phantom", "cyber", "update", "cdn"]
        tlds = ["com", "net", "xyz", "top", "info"]
        value = f"{rng.choice(words)}-{rng.choice(words)}.{rng.choice(tlds)}"
    elif ioc_type == "hash":
        value = hashlib.sha256(f"test-hash-{seed}".encode()).hexdigest()
    else:
        value = f"unknown-{seed}"
    return {"type": ioc_type, "value": value, "context": f"Test IOC (seed={seed})"}


def generate_enrichment_result(ioc_type: str, ioc_value: str, risk: str = "HIGH") -> dict:
    """Generate a mock enrichment result for any IOC type."""
    base = {
        "ioc": ioc_value,
        "type": ioc_type,
        "risk": risk,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if ioc_type == "ip":
        base["sources"] = {
            "virustotal": {"detections": 12, "total": 90, "country": "NL", "asn": "AS20473 Vultr"},
            "censys": {"ports": [22, 80, 443, 8080], "services": ["SSH", "HTTP", "HTTPS"]},
            "abuseipdb": {"confidence": 87, "reports": 34, "isp": "Vultr Holdings", "usage": "Data Center"},
        }
    elif ioc_type == "domain":
        base["sources"] = {
            "virustotal": {"detections": 8, "total": 90, "registrar": "Namecheap"},
            "dns": {"a_records": ["45.77.65.211"], "mx": [], "ns": ["ns1.example.com"]},
            "whois": {"registrar": "Namecheap", "created": "2025-11-01", "expires": "2026-11-01"},
        }
    elif ioc_type == "hash":
        base["sources"] = {
            "virustotal": {
                "detections": 45,
                "total": 72,
                "type": "PE32",
                "names": ["trojan.gen", "malware.generic"],
                "tags": ["signed", "packed"],
            },
        }
    return base


def generate_investigation_state(
    num_iocs: int = 3,
    num_findings: int = 2,
    seed: int = 0,
) -> dict:
    """Generate a mock investigation state dict matching investigation.sh format."""
    rng = random.Random(seed)
    ts = datetime.now(timezone.utc)
    inv_id = f"INV-{ts.strftime('%Y%m%d')}-{rng.randint(1,99):03d}"

    iocs = []
    for i in range(num_iocs):
        ioc = generate_ioc(rng.choice(["ip", "domain", "hash"]), seed=seed + i)
        ioc["risk"] = rng.choice(["HIGH", "MEDIUM", "LOW"])
        iocs.append(ioc)

    agents = ["triage-analyst", "osint-researcher", "incident-responder", "threat-intel", "report-writer"]
    findings = []
    for i in range(num_findings):
        findings.append({
            "agent": agents[i % len(agents)],
            "summary": f"Test finding {i+1} for investigation {inv_id}",
            "timestamp": (ts - timedelta(minutes=30 - i * 10)).isoformat(),
        })

    return {
        "id": inv_id,
        "title": f"Test Investigation (seed={seed})",
        "status": "active",
        "disposition": None,
        "created_at": ts.isoformat(),
        "iocs": iocs,
        "findings": findings,
        "timeline": [
            {"timestamp": ts.isoformat(), "event": "Investigation created", "agent": "coordinator"},
        ],
    }


def generate_log_entry(log_type: str = "network", seed: int = 0) -> dict:
    """Generate a synthetic log entry for testing log-querier."""
    rng = random.Random(seed)
    ts = datetime.now(timezone.utc) - timedelta(minutes=rng.randint(1, 360))

    if log_type == "network":
        return {
            "@timestamp": ts.isoformat(),
            "source.ip": f"10.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}",
            "destination.ip": f"{rng.randint(1,223)}.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}",
            "destination.port": rng.choice([22, 80, 443, 8080, 3389, 445]),
            "network.protocol": rng.choice(["tcp", "udp"]),
            "network.bytes": rng.randint(64, 65535),
            "event.action": rng.choice(["allowed", "denied", "dropped"]),
        }
    elif log_type == "dns":
        return {
            "@timestamp": ts.isoformat(),
            "source.ip": f"10.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}",
            "dns.question.name": rng.choice(["google.com", "evil-update.xyz", "cdn-static.net", "api.internal.corp"]),
            "dns.question.type": rng.choice(["A", "AAAA", "MX", "TXT"]),
            "dns.response_code": rng.choice(["NOERROR", "NXDOMAIN", "SERVFAIL"]),
        }
    return {"@timestamp": ts.isoformat(), "message": f"Generic log entry (seed={seed})"}
