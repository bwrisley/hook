"""
tests/mocks/mock_db.py -- In-memory database connector for HOOK tests.

Implements BaseDBConnector with in-memory storage and cosine-similarity
k-NN search. No external dependencies beyond numpy.
"""
from __future__ import annotations

import math
import uuid
from collections import defaultdict
from typing import Any, Optional

from core.db.connector import BaseDBConnector


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (norm_a * norm_b)


def _get_nested(doc: dict, path: str) -> Any:
    """Get a nested value from a dict using dotted path notation."""
    parts = path.split(".")
    current = doc
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


class MockDBConnector(BaseDBConnector):
    """In-memory database connector for testing. Supports basic OpenSearch DSL."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, dict]] = defaultdict(dict)

    def search(self, index: str, query: dict, size: int = 100) -> list[dict]:
        result = self.search_with_metadata(index, query, size)
        return result["hits"]

    def search_with_metadata(self, index: str, query: dict, size: int = 100) -> dict:
        docs = list(self._store.get(index, {}).values())
        q = query.get("query", {})
        effective_size = query.get("size", size)

        filtered = self._apply_query(docs, q)

        sort_spec = query.get("sort")
        if sort_spec and isinstance(sort_spec, list):
            for sort_item in reversed(sort_spec):
                if isinstance(sort_item, dict):
                    for field, order_spec in sort_item.items():
                        reverse = False
                        if isinstance(order_spec, dict):
                            reverse = order_spec.get("order", "asc") == "desc"
                        elif isinstance(order_spec, str):
                            reverse = order_spec == "desc"
                        filtered.sort(
                            key=lambda d: _get_nested(d, field) or "",
                            reverse=reverse,
                        )

        hits = filtered[:effective_size]
        return {"hits": hits, "total": len(filtered)}

    def aggregate(self, index: str, query: dict) -> dict[str, Any]:
        docs = list(self._store.get(index, {}).values())
        q = query.get("query", {})
        filtered = self._apply_query(docs, q)

        aggs = query.get("aggs", query.get("aggregations", {}))
        result = {}
        for agg_name, agg_spec in aggs.items():
            if "terms" in agg_spec:
                field = agg_spec["terms"]["field"]
                counts: dict[str, int] = defaultdict(int)
                for doc in filtered:
                    val = _get_nested(doc, field)
                    if val is not None:
                        counts[str(val)] += 1
                buckets = [
                    {"key": k, "doc_count": v}
                    for k, v in sorted(counts.items(), key=lambda x: -x[1])
                ]
                result[agg_name] = {"buckets": buckets}
        return result

    def index_document(self, index: str, doc_id: str, body: dict) -> dict:
        self._store[index][doc_id] = dict(body)
        return {"_id": doc_id, "result": "created"}

    def bulk_index(self, index: str, documents: list[dict]) -> dict:
        count = 0
        for doc in documents:
            doc_id = doc.pop("_id", None) or str(uuid.uuid4())[:12]
            self._store[index][doc_id] = doc
            count += 1
        return {"success": count, "errors": 0}

    def knn_search(
        self,
        index: str,
        vector: list[float],
        k: int = 5,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        docs = list(self._store.get(index, {}).values())
        if filters:
            docs = self._apply_query(docs, filters)

        scored = []
        for doc in docs:
            embedding = doc.get("embedding")
            if not embedding:
                continue
            score = _cosine_sim(vector, embedding)
            scored.append((score, doc))

        scored.sort(key=lambda x: -x[0])
        return [
            {**doc, "_score": score}
            for score, doc in scored[:k]
        ]

    def ensure_index(self, index: str, mappings: dict, settings: Optional[dict] = None) -> None:
        if index not in self._store:
            self._store[index] = {}

    def delete_document(self, index: str, doc_id: str) -> None:
        self._store.get(index, {}).pop(doc_id, None)

    # -- Test helpers --

    def seed_documents(self, index: str, documents: list[dict]) -> list[str]:
        """Bulk load documents with generated IDs. Returns list of IDs."""
        ids = []
        for doc in documents:
            doc_id = doc.get("id") or str(uuid.uuid4())[:12]
            self._store[index][doc_id] = doc
            ids.append(doc_id)
        return ids

    def all_documents(self, index: str) -> list[dict]:
        """Return all documents in an index."""
        return list(self._store.get(index, {}).values())

    def document_count(self, index: str) -> int:
        """Return number of documents in an index."""
        return len(self._store.get(index, {}))

    # -- Query engine --

    def _apply_query(self, docs: list[dict], q: dict) -> list[dict]:
        """Apply a simplified OpenSearch query filter to a list of documents."""
        if not q or "match_all" in q:
            return list(docs)

        if "bool" in q:
            return self._apply_bool(docs, q["bool"])
        if "term" in q:
            return self._apply_term(docs, q["term"])
        if "terms" in q:
            return self._apply_terms(docs, q["terms"])
        if "range" in q:
            return self._apply_range(docs, q["range"])
        if "match" in q:
            return self._apply_match(docs, q["match"])
        if "multi_match" in q:
            return self._apply_multi_match(docs, q["multi_match"])

        return list(docs)

    def _apply_bool(self, docs: list[dict], bool_q: dict) -> list[dict]:
        result = list(docs)
        for clause in bool_q.get("must", []):
            result = self._apply_query(result, clause)
        for clause in bool_q.get("filter", []):
            result = self._apply_query(result, clause)
        if "should" in bool_q:
            should_results = set()
            for clause in bool_q["should"]:
                for doc in self._apply_query(result, clause):
                    should_results.add(id(doc))
            if bool_q.get("minimum_should_match", 0):
                result = [d for d in result if id(d) in should_results]
        for clause in bool_q.get("must_not", []):
            excluded = {id(d) for d in self._apply_query(result, clause)}
            result = [d for d in result if id(d) not in excluded]
        return result

    def _apply_term(self, docs: list[dict], term_q: dict) -> list[dict]:
        result = []
        for field, value in term_q.items():
            if isinstance(value, dict):
                value = value.get("value", value)
            for doc in docs:
                if _get_nested(doc, field) == value:
                    result.append(doc)
        return result

    def _apply_terms(self, docs: list[dict], terms_q: dict) -> list[dict]:
        result = []
        for field, values in terms_q.items():
            for doc in docs:
                if _get_nested(doc, field) in values:
                    result.append(doc)
        return result

    def _apply_range(self, docs: list[dict], range_q: dict) -> list[dict]:
        result = list(docs)
        for field, constraints in range_q.items():
            filtered = []
            for doc in result:
                val = _get_nested(doc, field)
                if val is None:
                    continue
                ok = True
                for op, bound in constraints.items():
                    if op == "gte" and val < bound:
                        ok = False
                    elif op == "gt" and val <= bound:
                        ok = False
                    elif op == "lte" and val > bound:
                        ok = False
                    elif op == "lt" and val >= bound:
                        ok = False
                if ok:
                    filtered.append(doc)
            result = filtered
        return result

    def _apply_match(self, docs: list[dict], match_q: dict) -> list[dict]:
        result = []
        for field, query_val in match_q.items():
            if isinstance(query_val, dict):
                query_val = query_val.get("query", "")
            query_lower = str(query_val).lower()
            for doc in docs:
                val = _get_nested(doc, field)
                if val is not None and query_lower in str(val).lower():
                    result.append(doc)
        return result

    def _apply_multi_match(self, docs: list[dict], mm_q: dict) -> list[dict]:
        query_lower = str(mm_q.get("query", "")).lower()
        fields = mm_q.get("fields", [])
        result = []
        for doc in docs:
            for field in fields:
                val = _get_nested(doc, field)
                if val is not None and query_lower in str(val).lower():
                    result.append(doc)
                    break
        return result
