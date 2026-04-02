"""
tests/test_mocks.py -- Tests for the mock DB and LLM providers.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.mocks.mock_db import MockDBConnector
from tests.mocks.mock_llm import MockLLMProvider
from tests.mocks.data_generator import (
    deterministic_embed,
    generate_alert,
    generate_ioc,
    generate_enrichment_result,
    generate_investigation_state,
    generate_log_entry,
)


class TestMockDB:
    def test_index_and_search(self):
        db = MockDBConnector()
        db.index_document("test", "doc1", {"text": "hello world", "category": "test"})
        results = db.search("test", {"query": {"match_all": {}}})
        assert len(results) == 1
        assert results[0]["text"] == "hello world"

    def test_term_filter(self):
        db = MockDBConnector()
        db.index_document("test", "d1", {"status": "active", "name": "alpha"})
        db.index_document("test", "d2", {"status": "closed", "name": "beta"})
        results = db.search("test", {"query": {"term": {"status": "active"}}})
        assert len(results) == 1
        assert results[0]["name"] == "alpha"

    def test_knn_search(self):
        db = MockDBConnector()
        vec1 = deterministic_embed("hello", 64)
        vec2 = deterministic_embed("world", 64)
        vec3 = deterministic_embed("hello friend", 64)
        db.index_document("idx", "d1", {"text": "hello", "embedding": vec1})
        db.index_document("idx", "d2", {"text": "world", "embedding": vec2})
        db.index_document("idx", "d3", {"text": "hello friend", "embedding": vec3})

        query_vec = deterministic_embed("hello", 64)
        hits = db.knn_search("idx", query_vec, k=2)
        assert len(hits) == 2
        assert hits[0]["text"] == "hello"  # exact match should be top

    def test_bulk_index(self):
        db = MockDBConnector()
        result = db.bulk_index("test", [
            {"_id": "a", "text": "one"},
            {"_id": "b", "text": "two"},
        ])
        assert result["success"] == 2
        assert db.document_count("test") == 2

    def test_delete_document(self):
        db = MockDBConnector()
        db.index_document("test", "doc1", {"text": "to delete"})
        assert db.document_count("test") == 1
        db.delete_document("test", "doc1")
        assert db.document_count("test") == 0

    def test_aggregation(self):
        db = MockDBConnector()
        db.index_document("test", "d1", {"status": "active"})
        db.index_document("test", "d2", {"status": "active"})
        db.index_document("test", "d3", {"status": "closed"})
        result = db.aggregate("test", {
            "query": {"match_all": {}},
            "aggs": {"status_counts": {"terms": {"field": "status"}}},
        })
        assert "status_counts" in result
        buckets = result["status_counts"]["buckets"]
        assert any(b["key"] == "active" and b["doc_count"] == 2 for b in buckets)


class TestMockLLM:
    def test_embed_deterministic(self):
        llm = MockLLMProvider(embedding_dims=64)
        v1 = llm.embed("hello")
        v2 = llm.embed("hello")
        assert v1 == v2
        assert len(v1) == 64

    def test_embed_different_texts(self):
        llm = MockLLMProvider()
        v1 = llm.embed("hello")
        v2 = llm.embed("world")
        assert v1 != v2

    def test_chat_dispatch_triage(self):
        llm = MockLLMProvider()
        resp = llm.chat([{"role": "user", "content": "Triage this alert"}])
        assert "Verdict" in resp

    def test_chat_dispatch_enrichment(self):
        llm = MockLLMProvider()
        resp = llm.chat([{"role": "user", "content": "Enrich this IOC via VirusTotal"}])
        assert "risk" in resp or "ioc" in resp

    def test_call_log(self):
        llm = MockLLMProvider()
        llm.embed("test")
        llm.chat([{"role": "user", "content": "hello"}])
        assert len(llm.call_log) == 2
        assert llm.call_log[0]["method"] == "embed"
        assert llm.call_log[1]["method"] == "chat"


class TestDataGenerator:
    def test_deterministic_embed(self):
        v1 = deterministic_embed("test", 64)
        v2 = deterministic_embed("test", 64)
        assert v1 == v2
        assert len(v1) == 64

    def test_generate_alert(self):
        alert = generate_alert(severity="High", alert_type="C2", seed=42)
        assert alert["severity"] == "High"
        assert "alert_id" in alert
        assert "source_ip" in alert

    def test_generate_ioc(self):
        ioc = generate_ioc("ip", seed=1)
        assert ioc["type"] == "ip"
        assert "." in ioc["value"]

        ioc = generate_ioc("domain", seed=1)
        assert ioc["type"] == "domain"

        ioc = generate_ioc("hash", seed=1)
        assert ioc["type"] == "hash"
        assert len(ioc["value"]) == 64

    def test_generate_enrichment_result(self):
        result = generate_enrichment_result("ip", "1.2.3.4")
        assert result["risk"] == "HIGH"
        assert "virustotal" in result["sources"]

    def test_generate_investigation_state(self):
        state = generate_investigation_state(num_iocs=3, num_findings=2)
        assert state["id"].startswith("INV-")
        assert len(state["iocs"]) == 3
        assert len(state["findings"]) == 2

    def test_generate_log_entry(self):
        entry = generate_log_entry("network", seed=0)
        assert "@timestamp" in entry
        assert "source.ip" in entry

        entry = generate_log_entry("dns", seed=0)
        assert "dns.question.name" in entry


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
