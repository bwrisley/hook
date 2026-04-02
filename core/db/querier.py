"""
core/db/querier.py -- Natural language to OpenSearch DSL translator.

Used by the log-querier agent to translate analyst questions into
structured OpenSearch queries and return results.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.db.connector import BaseDBConnector

logger = logging.getLogger(__name__)

QUERY_PROMPT_TEMPLATE = """You are an OpenSearch query translator. Convert the analyst's natural language question into an OpenSearch DSL query body (JSON).

Available index: {index}

Available fields and their types:
{field_mappings}

Analyst question: {question}

Rules:
- Output ONLY valid JSON, no explanation
- Use appropriate query types: match, term, range, bool, wildcard
- For time-based queries, use range on @timestamp with relative values like "now-1h", "now-24h"
- For IP addresses, use term queries
- For text fields, use match queries
- Limit results to 50 unless the question implies otherwise
- Include _source filtering for relevant fields only

Output the OpenSearch query body JSON:"""


class LogQuerier:
    """Translates natural language log queries into OpenSearch DSL and executes them."""

    def __init__(self, db: BaseDBConnector, llm: Any) -> None:
        self.db = db
        self.llm = llm

    def query(
        self,
        question: str,
        index: str,
        max_results: int = 50,
    ) -> dict[str, Any]:
        """Translate a natural language question to OpenSearch DSL and execute it.

        Returns:
            dict with keys: query_dsl, results, count, executed_at
        """
        field_mappings = self.discover_fields(index)
        if not field_mappings:
            return {
                "status": "error",
                "message": f"No field mappings found for index '{index}'",
                "results": [],
            }

        prompt = QUERY_PROMPT_TEMPLATE.format(
            index=index,
            field_mappings=self._format_fields(field_mappings),
            question=question,
        )

        try:
            response = self.llm.chat([{"role": "user", "content": prompt}])
            query_dsl = self._parse_json_response(response)
        except Exception as exc:
            logger.error("LLM query translation failed: %s", exc)
            return {
                "status": "error",
                "message": f"Failed to translate query: {exc}",
                "results": [],
            }

        if "size" not in query_dsl:
            query_dsl["size"] = max_results

        try:
            results = self.db.search(index=index, query=query_dsl, size=max_results)
            return {
                "status": "ok",
                "query_dsl": query_dsl,
                "results": results,
                "count": len(results),
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.error("Query execution failed: %s", exc)
            return {
                "status": "error",
                "message": f"Query execution failed: {exc}",
                "query_dsl": query_dsl,
                "results": [],
            }

    def discover_fields(self, index: str) -> dict[str, str]:
        """Discover available fields and their types for an index.

        Returns:
            dict mapping field names to their OpenSearch types
        """
        if not hasattr(self.db, "_client"):
            return {}

        try:
            mapping = self.db._client.indices.get_mapping(index=index)
            properties = (
                mapping.get(index, {})
                .get("mappings", {})
                .get("properties", {})
            )
            return self._flatten_properties(properties)
        except Exception as exc:
            logger.error("Field discovery failed for index '%s': %s", index, exc)
            return {}

    def _flatten_properties(
        self, properties: dict, prefix: str = ""
    ) -> dict[str, str]:
        """Flatten nested OpenSearch mapping properties into dotted field names."""
        fields = {}
        for name, spec in properties.items():
            full_name = f"{prefix}{name}" if not prefix else f"{prefix}.{name}"
            field_type = spec.get("type", "object")
            if field_type != "object":
                fields[full_name] = field_type
            if "properties" in spec:
                fields.update(self._flatten_properties(spec["properties"], full_name))
        return fields

    def _format_fields(self, fields: dict[str, str]) -> str:
        """Format field mappings for the LLM prompt."""
        lines = []
        for name, ftype in sorted(fields.items()):
            lines.append(f"  - {name}: {ftype}")
        return "\n".join(lines) if lines else "  (no fields discovered)"

    def _parse_json_response(self, response: str) -> dict:
        """Extract JSON from LLM response, handling markdown code blocks."""
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]  # skip ```json
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return json.loads(text)
