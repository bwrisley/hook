"""
core/db/connector.py -- Database connector abstraction for HOOK.

Provides:
  - BaseDBConnector ABC for OpenSearch/Elasticsearch backends
  - OpenSearchConnector implementation (config-gated via HOOK_OPENSEARCH_HOST)
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class QueryMalformedException(Exception):
    """Raised when a search query is malformed (HTTP 400 from OpenSearch)."""


class BaseDBConnector(ABC):
    """Abstract base for database connectors used by RAG, baseliner, and log-querier."""

    @abstractmethod
    def search(self, index: str, query: dict, size: int = 100) -> list[dict]:
        """Execute a search query and return matching documents."""

    @abstractmethod
    def search_with_metadata(self, index: str, query: dict, size: int = 100) -> dict:
        """Execute a search query and return hits plus total count."""

    @abstractmethod
    def aggregate(self, index: str, query: dict) -> dict[str, Any]:
        """Execute an aggregation query and return aggregation results."""

    @abstractmethod
    def index_document(self, index: str, doc_id: str, body: dict) -> dict:
        """Index (upsert) a single document."""

    @abstractmethod
    def bulk_index(self, index: str, documents: list[dict]) -> dict:
        """Bulk index multiple documents."""

    @abstractmethod
    def knn_search(
        self,
        index: str,
        vector: list[float],
        k: int = 5,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        """Execute a k-nearest-neighbor vector search."""

    @abstractmethod
    def ensure_index(self, index: str, mappings: dict, settings: Optional[dict] = None) -> None:
        """Create an index with the given mappings if it does not exist."""

    @abstractmethod
    def delete_document(self, index: str, doc_id: str) -> None:
        """Delete a single document by ID."""


class OpenSearchConnector(BaseDBConnector):
    """OpenSearch/Elasticsearch connector. Config-gated via environment variables."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_ssl: bool = False,
        verify_certs: bool = False,
    ) -> None:
        self.host = host or os.environ.get("HOOK_OPENSEARCH_HOST", "localhost")
        self.port = port or int(os.environ.get("HOOK_OPENSEARCH_PORT", "9200"))
        self.username = username or os.environ.get("HOOK_OPENSEARCH_USER", "")
        self.password = password or os.environ.get("HOOK_OPENSEARCH_PASS", "")
        self.use_ssl = use_ssl
        self.verify_certs = verify_certs
        self._client = self._connect()

    def _connect(self):
        try:
            from opensearchpy import OpenSearch

            auth = (self.username, self.password) if self.username else None
            client = OpenSearch(
                hosts=[{"host": self.host, "port": self.port}],
                http_auth=auth,
                use_ssl=self.use_ssl,
                verify_certs=self.verify_certs,
                ssl_show_warn=False,
            )
            logger.info("Connected to OpenSearch at %s:%d", self.host, self.port)
            return client
        except Exception as exc:
            logger.error("Failed to connect to OpenSearch: %s", exc)
            raise

    def search(self, index: str, query: dict, size: int = 100) -> list[dict]:
        try:
            body = dict(query)
            if "size" not in body:
                body["size"] = size
            resp = self._client.search(index=index, body=body)
            return [hit["_source"] for hit in resp.get("hits", {}).get("hits", [])]
        except Exception as exc:
            if hasattr(exc, "status_code") and exc.status_code == 400:
                raise QueryMalformedException(str(exc)) from exc
            logger.error("Search failed on index '%s': %s", index, exc)
            return []

    def search_with_metadata(self, index: str, query: dict, size: int = 100) -> dict:
        try:
            body = dict(query)
            if "size" not in body:
                body["size"] = size
            resp = self._client.search(index=index, body=body)
            hits_data = resp.get("hits", {})
            return {
                "hits": [hit["_source"] for hit in hits_data.get("hits", [])],
                "total": hits_data.get("total", {}).get("value", 0),
            }
        except Exception as exc:
            if hasattr(exc, "status_code") and exc.status_code == 400:
                raise QueryMalformedException(str(exc)) from exc
            logger.error("Search failed on index '%s': %s", index, exc)
            return {"hits": [], "total": 0}

    def aggregate(self, index: str, query: dict) -> dict[str, Any]:
        try:
            resp = self._client.search(index=index, body=query)
            return resp.get("aggregations", {})
        except Exception as exc:
            logger.error("Aggregation failed on index '%s': %s", index, exc)
            return {}

    def index_document(self, index: str, doc_id: str, body: dict) -> dict:
        try:
            return self._client.index(index=index, id=doc_id, body=body)
        except Exception as exc:
            logger.error("Index document failed: %s", exc)
            raise

    def bulk_index(self, index: str, documents: list[dict]) -> dict:
        try:
            from opensearchpy.helpers import bulk

            actions = []
            for doc in documents:
                doc_id = doc.pop("_id", None)
                action = {"_index": index, "_source": doc}
                if doc_id:
                    action["_id"] = doc_id
                actions.append(action)
            success, errors = bulk(self._client, actions)
            return {"success": success, "errors": errors}
        except Exception as exc:
            logger.error("Bulk index failed: %s", exc)
            raise

    def knn_search(
        self,
        index: str,
        vector: list[float],
        k: int = 5,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        try:
            knn_query = {
                "knn": {
                    "embedding": {
                        "vector": vector,
                        "k": k,
                    }
                }
            }
            body: dict[str, Any] = {"size": k, "query": knn_query}
            if filters:
                body["query"] = {
                    "bool": {
                        "must": knn_query,
                        "filter": filters,
                    }
                }
            resp = self._client.search(index=index, body=body)
            hits = resp.get("hits", {}).get("hits", [])
            return [
                {**hit["_source"], "_score": hit.get("_score", 0.0)}
                for hit in hits
            ]
        except Exception as exc:
            logger.error("KNN search failed on index '%s': %s", index, exc)
            return []

    def ensure_index(self, index: str, mappings: dict, settings: Optional[dict] = None) -> None:
        try:
            if self._client.indices.exists(index=index):
                logger.debug("Index '%s' already exists", index)
                return
            body: dict[str, Any] = {"mappings": mappings}
            if settings:
                body["settings"] = settings
            self._client.indices.create(index=index, body=body)
            logger.info("Created index '%s'", index)
        except Exception as exc:
            logger.error("Failed to ensure index '%s': %s", index, exc)

    def delete_document(self, index: str, doc_id: str) -> None:
        try:
            self._client.delete(index=index, id=doc_id)
        except Exception as exc:
            logger.warning("Failed to delete document '%s' from '%s': %s", doc_id, index, exc)
