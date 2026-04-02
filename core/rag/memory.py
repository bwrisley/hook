"""
core/rag/memory.py -- Behavioral memory for HOOK agents.

Provides high-level store/recall methods for IOC verdicts, baselines,
and investigation findings. Agents interact with this via the
scripts/rag-inject.py CLI wrapper.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from core.rag.engine import RAGEngine

logger = logging.getLogger(__name__)

# RAG categories
CAT_IOC_VERDICT = "ioc_verdict"
CAT_BASELINE = "network_baseline"
CAT_FINDING = "investigation_finding"
CAT_TTP = "ttp_history"


class BehavioralMemory:
    """High-level behavioral memory backed by RAGEngine.

    Provides domain-specific store/recall methods that agents use
    to build environmental context during investigations.
    """

    def __init__(self, rag: RAGEngine) -> None:
        self.rag = rag

    # -- Store methods --

    def store_verdict(
        self,
        ioc_value: str,
        ioc_type: str,
        verdict: str,
        source_agent: str = "osint-researcher",
        confidence: str = "medium",
    ) -> str:
        """Store an IOC enrichment verdict for future recall."""
        text = (
            f"IOC: {ioc_value} (type: {ioc_type})\n"
            f"Verdict: {verdict}\n"
            f"Confidence: {confidence}\n"
            f"Agent: {source_agent}\n"
            f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        )
        return self.rag.store(
            text,
            category=CAT_IOC_VERDICT,
            source=source_agent,
            metadata={"ioc_value": ioc_value, "ioc_type": ioc_type},
        )

    def store_baseline(
        self,
        identifier: str,
        summary: str,
        category: str = CAT_BASELINE,
    ) -> str:
        """Store a behavioral baseline summary."""
        text = f"Baseline for {identifier}:\n{summary}"
        return self.rag.store(
            text,
            category=category,
            source="baseliner",
            metadata={"identifier": identifier},
        )

    def store_finding(
        self,
        investigation_id: str,
        agent: str,
        summary: str,
        detail: str = "",
    ) -> str:
        """Store an investigation finding for cross-investigation recall."""
        text = (
            f"Investigation: {investigation_id}\n"
            f"Agent: {agent}\n"
            f"Finding: {summary}"
        )
        if detail:
            text += f"\nDetail: {detail[:500]}"
        return self.rag.store(
            text,
            category=CAT_FINDING,
            source=agent,
            metadata={"investigation_id": investigation_id},
        )

    def store_ttp(
        self,
        technique_id: str,
        description: str,
        threat_actor: str = "",
        source_agent: str = "threat-intel",
    ) -> str:
        """Store a TTP observation for historical recall."""
        text = f"TTP: {technique_id}\nDescription: {description}"
        if threat_actor:
            text += f"\nThreat Actor: {threat_actor}"
        return self.rag.store(
            text,
            category=CAT_TTP,
            source=source_agent,
            metadata={"technique_id": technique_id},
        )

    # -- Recall methods --

    def recall_ioc(self, ioc_value: str, k: int = 3) -> str:
        """Retrieve past verdicts for an IOC. Returns formatted markdown."""
        return self.rag.build_context_string(
            query=ioc_value,
            k=k,
            category=CAT_IOC_VERDICT,
            prefix="### Past IOC Verdicts\n",
        )

    def recall_baseline(self, query: str, k: int = 3) -> str:
        """Retrieve relevant baseline context. Returns formatted markdown."""
        return self.rag.build_context_string(
            query=query,
            k=k,
            category=CAT_BASELINE,
            prefix="### Behavioral Baseline Context\n",
        )

    def recall_findings(self, query: str, k: int = 5) -> str:
        """Retrieve past investigation findings. Returns formatted markdown."""
        return self.rag.build_context_string(
            query=query,
            k=k,
            category=CAT_FINDING,
            prefix="### Related Past Findings\n",
        )

    def recall_ttps(self, query: str, k: int = 3) -> str:
        """Retrieve historical TTPs for ACH analysis. Returns formatted markdown."""
        return self.rag.build_context_string(
            query=query,
            k=k,
            category=CAT_TTP,
            prefix="### Historical TTP Context\n",
        )
