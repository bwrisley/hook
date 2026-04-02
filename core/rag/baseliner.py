"""
core/rag/baseliner.py -- Behavioral baseliner for HOOK.

Queries log sources for recent activity, groups by identifier,
summarizes via LLM, and stores behavioral baselines in the RAG engine.
Runs every 6 hours via LaunchAgent.

Adapted from SecurityClaw's skills/network_baseliner/ pattern.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from core.db.connector import BaseDBConnector
from core.rag.engine import RAGEngine

logger = logging.getLogger(__name__)

BASELINE_PROMPT = """Summarize the following network/log activity into a concise behavioral baseline. Focus on:
- Traffic volume and protocol distribution
- Top source/destination IPs and ports
- DNS query patterns (if present)
- Any anomalous or unusual patterns

Data from identifier "{identifier}" over the last {hours} hours:

{data}

Provide a 3-5 sentence summary of normal/expected behavior patterns:"""

MAX_BASELINE_DOCS = 100


class Baseliner:
    """Builds behavioral baseline embeddings from log data.

    Queries the log source for recent activity, groups by sensor/network
    identifier, summarizes each group via LLM, and stores the result
    in the RAG engine for agent context injection.
    """

    def __init__(
        self,
        db: BaseDBConnector,
        llm: Any,
        rag: RAGEngine,
    ) -> None:
        self.db = db
        self.llm = llm
        self.rag = rag

    def run(self, hours: int = 6, index: str = "logs-*") -> dict[str, Any]:
        """Execute the baseliner workflow.

        Args:
            hours: How many hours of recent logs to analyze
            index: OpenSearch index pattern to query

        Returns:
            dict with status, documents_stored count, and details
        """
        logger.info("Baseliner starting: querying last %d hours from '%s'", hours, index)

        # 1. Query recent logs
        docs = self._query_recent_logs(hours, index)
        if not docs:
            logger.info("No log data found for baselining")
            return {"status": "no_data", "documents_stored": 0}

        # 2. Group by identifier
        groups = self._group_by_identifier(docs)
        logger.info("Found %d identifier groups in %d documents", len(groups), len(docs))

        # 3. Summarize each group and store
        stored = []
        for identifier, group_docs in groups.items():
            try:
                summary = self._summarize_group(identifier, group_docs, hours)
                doc_id = self.rag.store(
                    text=f"Baseline for {identifier}:\n{summary}",
                    category="network_baseline",
                    source="baseliner",
                    metadata={"identifier": identifier, "hours": hours},
                )
                stored.append({
                    "identifier": identifier,
                    "doc_id": doc_id,
                    "doc_count": len(group_docs),
                })
                logger.info("Stored baseline for %s (%d docs)", identifier, len(group_docs))
            except Exception as exc:
                logger.error("Failed to baseline %s: %s", identifier, exc)

        # 4. Evict oldest if over capacity
        self._evict_oldest()

        return {
            "status": "ok",
            "documents_stored": len(stored),
            "details": stored,
        }

    def _query_recent_logs(self, hours: int, index: str) -> list[dict]:
        """Query the log source for documents within the last N hours."""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        query = {
            "query": {
                "range": {
                    "@timestamp": {"gte": since}
                }
            },
            "size": 5000,
            "sort": [{"@timestamp": {"order": "desc"}}],
        }
        try:
            return self.db.search(index=index, query=query, size=5000)
        except Exception as exc:
            logger.error("Log query failed: %s", exc)
            return []

    def _group_by_identifier(self, docs: list[dict]) -> dict[str, list[dict]]:
        """Group documents by a detected identifier field.

        Looks for common identifier fields: observer.name, agent.name,
        sensor_id, network.name. Falls back to 'default' group.
        """
        id_fields = ["observer.name", "agent.name", "sensor_id", "network.name"]
        groups: dict[str, list[dict]] = {}

        for doc in docs:
            identifier = "default"
            for field in id_fields:
                val = self._get_nested(doc, field)
                if val:
                    identifier = str(val)
                    break
            groups.setdefault(identifier, []).append(doc)

        return groups

    def _summarize_group(
        self, identifier: str, docs: list[dict], hours: int
    ) -> str:
        """Use LLM to summarize a group of log documents into a baseline."""
        # Build a compact data summary for the LLM
        data_lines = []
        for doc in docs[:200]:  # cap input to LLM
            line_parts = []
            for key in ["@timestamp", "source.ip", "destination.ip",
                        "destination.port", "network.protocol", "event.action",
                        "dns.question.name", "dns.response_code"]:
                val = self._get_nested(doc, key)
                if val is not None:
                    line_parts.append(f"{key}={val}")
            if line_parts:
                data_lines.append(" | ".join(line_parts))

        data_text = "\n".join(data_lines) if data_lines else "(no structured fields found)"

        prompt = BASELINE_PROMPT.format(
            identifier=identifier,
            hours=hours,
            data=data_text,
        )

        response = self.llm.chat([{"role": "user", "content": prompt}])
        return response.strip()

    def _evict_oldest(self) -> None:
        """Remove oldest baseline documents if over MAX_BASELINE_DOCS capacity."""
        try:
            hits = self.rag.retrieve(
                query="baseline",
                k=MAX_BASELINE_DOCS + 50,
                category="network_baseline",
            )
            if len(hits) > MAX_BASELINE_DOCS:
                # Sort by timestamp ascending, remove oldest
                hits.sort(key=lambda h: h.get("timestamp", ""))
                to_remove = hits[: len(hits) - MAX_BASELINE_DOCS]
                for hit in to_remove:
                    doc_id = hit.get("id", "")
                    if doc_id:
                        if self.rag.db is not None:
                            self.rag.db.delete_document(self.rag.index_name, doc_id)
                        elif self.rag._faiss is not None:
                            self.rag._faiss.delete(doc_id)
                logger.info("Evicted %d oldest baseline documents", len(to_remove))
        except Exception as exc:
            logger.warning("Baseline eviction failed: %s", exc)

    @staticmethod
    def _get_nested(doc: dict, path: str) -> Any:
        """Get a nested value using dotted path notation."""
        parts = path.split(".")
        current = doc
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current
