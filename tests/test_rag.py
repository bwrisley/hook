"""
tests/test_rag.py -- Unit tests for HOOK RAG engine and behavioral memory.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.mocks.mock_db import MockDBConnector
from tests.mocks.mock_llm import MockLLMProvider
from core.rag.engine import RAGEngine
from core.rag.memory import BehavioralMemory


def _make_rag(db=None, llm=None):
    db = db or MockDBConnector()
    llm = llm or MockLLMProvider(embedding_dims=64)
    return RAGEngine(llm=llm, db=db, index_name="test-vectors", top_k=5)


class TestRAGEngine:
    def test_store_and_retrieve(self):
        db = MockDBConnector()
        rag = _make_rag(db=db)
        doc_id = rag.store("Cobalt Strike beacon on 45.77.65.211", category="ioc_verdict", source="osint")
        assert doc_id
        assert db.document_count("test-vectors") == 1

        hits = rag.retrieve("45.77.65.211", k=3)
        assert len(hits) >= 1
        assert "Cobalt Strike" in hits[0].get("text", "")

    def test_store_empty_text_skipped(self):
        rag = _make_rag()
        doc_id = rag.store("", category="test")
        assert doc_id == ""

    def test_bulk_store(self):
        db = MockDBConnector()
        rag = _make_rag(db=db)
        ids = rag.bulk_store(
            ["chunk one", "chunk two", "chunk three"],
            category="test",
            source="unit-test",
        )
        assert len(ids) == 3
        assert db.document_count("test-vectors") == 3

    def test_retrieve_with_category_filter(self):
        db = MockDBConnector()
        rag = _make_rag(db=db)
        rag.store("IOC verdict for 1.2.3.4", category="ioc_verdict")
        rag.store("Baseline for sensor-01", category="network_baseline")

        ioc_hits = rag.retrieve("1.2.3.4", k=5, category="ioc_verdict")
        assert all(h.get("category") == "ioc_verdict" for h in ioc_hits)

    def test_build_context_string(self):
        db = MockDBConnector()
        rag = _make_rag(db=db)
        rag.store("Past verdict: 1.2.3.4 is HIGH risk C2", category="ioc_verdict")

        ctx = rag.build_context_string("1.2.3.4", k=3, category="ioc_verdict")
        assert "Past verdict" in ctx
        assert "ioc_verdict" in ctx

    def test_build_context_string_no_results(self):
        rag = _make_rag()
        ctx = rag.build_context_string("nonexistent-query")
        assert "No relevant context found" in ctx

    def test_keyword_fallback(self):
        db = MockDBConnector()
        rag = _make_rag(db=db)
        rag.store("Network traffic anomaly detected on sensor-dmz", category="alert")

        # Keyword search should work even with vectors
        hits = rag.retrieve("anomaly detected", k=3)
        assert len(hits) >= 1


class TestBehavioralMemory:
    def test_store_and_recall_verdict(self):
        rag = _make_rag()
        memory = BehavioralMemory(rag)

        doc_id = memory.store_verdict(
            ioc_value="45.77.65.211",
            ioc_type="ip",
            verdict="HIGH risk, Cobalt Strike C2",
            confidence="high",
        )
        assert doc_id

        ctx = memory.recall_ioc("45.77.65.211")
        assert "Past IOC Verdicts" in ctx

    def test_store_and_recall_baseline(self):
        rag = _make_rag()
        memory = BehavioralMemory(rag)

        memory.store_baseline("sensor-dmz-01", "Normal HTTP/HTTPS traffic 85%")
        ctx = memory.recall_baseline("sensor-dmz-01")
        assert "Behavioral Baseline Context" in ctx

    def test_store_and_recall_finding(self):
        rag = _make_rag()
        memory = BehavioralMemory(rag)

        memory.store_finding(
            investigation_id="INV-20260302-001",
            agent="osint-researcher",
            summary="C2 confirmed via VirusTotal",
        )
        ctx = memory.recall_findings("C2 confirmed")
        assert "Related Past Findings" in ctx

    def test_store_and_recall_ttp(self):
        rag = _make_rag()
        memory = BehavioralMemory(rag)

        memory.store_ttp(
            technique_id="T1059.001",
            description="PowerShell beacon loader",
            threat_actor="APT29",
        )
        ctx = memory.recall_ttps("T1059.001 PowerShell")
        assert "Historical TTP Context" in ctx


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
