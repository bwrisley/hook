"""
core/rag/engine.py -- Retrieval-Augmented Generation engine for HOOK.

Provides:
  - Embedding text chunks via an LLM provider
  - Storing embeddings in OpenSearch (k-NN) or local FAISS
  - Retrieving top-k similar chunks for a query
  - Building context strings for agent prompt injection

Adapted from SecurityClaw's core/rag_engine.py for HOOK's multi-agent model.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.db.connector import BaseDBConnector

logger = logging.getLogger(__name__)


class FAISSStore:
    """Local FAISS-backed vector store. Fallback when OpenSearch is not configured.

    Persists index and metadata to data/faiss/ as .faiss + .json files.
    """

    def __init__(self, persist_dir: str = "data/faiss", dims: int = 64) -> None:
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.dims = dims
        self._index = None
        self._metadata: dict[int, dict] = {}  # position -> metadata
        self._id_to_pos: dict[str, int] = {}   # doc_id -> position in index
        self._load()

    def _load(self) -> None:
        """Load persisted FAISS index and metadata from disk."""
        index_path = self.persist_dir / "hook-vectors.faiss"
        meta_path = self.persist_dir / "hook-vectors.json"

        try:
            import faiss
        except ImportError:
            logger.warning("faiss-cpu not installed; FAISS store will use in-memory fallback")
            self._index = None
            if meta_path.exists():
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                self._metadata = {int(k): v for k, v in data.get("metadata", {}).items()}
                self._id_to_pos = data.get("id_to_pos", {})
            return

        if index_path.exists():
            self._index = faiss.read_index(str(index_path))
            if meta_path.exists():
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                self._metadata = {int(k): v for k, v in data.get("metadata", {}).items()}
                self._id_to_pos = data.get("id_to_pos", {})
            logger.info("Loaded FAISS index: %d vectors", self._index.ntotal)
        else:
            self._index = faiss.IndexFlatIP(self.dims)
            logger.info("Created new FAISS index (dims=%d)", self.dims)

    def _save(self) -> None:
        """Persist FAISS index and metadata to disk."""
        try:
            import faiss
        except ImportError:
            # Save metadata even without FAISS
            meta_path = self.persist_dir / "hook-vectors.json"
            meta_path.write_text(
                json.dumps({"metadata": self._metadata, "id_to_pos": self._id_to_pos}, default=str),
                encoding="utf-8",
            )
            return

        if self._index is not None:
            index_path = self.persist_dir / "hook-vectors.faiss"
            faiss.write_index(self._index, str(index_path))

        meta_path = self.persist_dir / "hook-vectors.json"
        meta_path.write_text(
            json.dumps({"metadata": self._metadata, "id_to_pos": self._id_to_pos}, default=str),
            encoding="utf-8",
        )

    def store(self, doc_id: str, embedding: list[float], metadata: dict) -> None:
        """Add or update a vector in the index."""
        if doc_id in self._id_to_pos:
            # Mark old position as stale (superseded)
            pass

        if self._index is not None:
            import numpy as np
            vec = np.array([embedding], dtype=np.float32)
            pos = self._index.ntotal
            self._index.add(vec)
        else:
            # Pure-Python fallback: store vector in metadata for later search
            pos = max(self._metadata.keys(), default=-1) + 1

        # Always store the embedding in metadata so pure-Python search works
        metadata_with_vec = dict(metadata)
        metadata_with_vec["_embedding"] = embedding
        self._metadata[pos] = metadata_with_vec
        self._id_to_pos[doc_id] = pos
        self._save()

    def search(
        self,
        query_vec: list[float],
        k: int = 5,
        category: Optional[str] = None,
    ) -> list[dict]:
        """Search for the k most similar vectors."""
        if self._index is not None and self._index.ntotal > 0:
            return self._search_faiss(query_vec, k, category)
        return self._search_pure_python(query_vec, k, category)

    def _search_faiss(self, query_vec: list[float], k: int, category: Optional[str]) -> list[dict]:
        """Search using FAISS index."""
        import numpy as np
        vec = np.array([query_vec], dtype=np.float32)
        actual_k = min(k * 3, self._index.ntotal)
        scores, indices = self._index.search(vec, actual_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            meta = self._metadata.get(int(idx), {})
            if category and meta.get("category") != category:
                continue
            doc_id = meta.get("id", "")
            if doc_id and self._id_to_pos.get(doc_id) != int(idx):
                continue
            result = {k2: v for k2, v in meta.items() if k2 != "_embedding"}
            result["_score"] = float(score)
            results.append(result)
            if len(results) >= k:
                break
        return results

    def _search_pure_python(self, query_vec: list[float], k: int, category: Optional[str]) -> list[dict]:
        """Pure-Python cosine similarity search. Used when FAISS is not installed."""
        import math
        scored = []
        for pos, meta in self._metadata.items():
            if category and meta.get("category") != category:
                continue
            doc_id = meta.get("id", "")
            if doc_id and self._id_to_pos.get(doc_id) != pos:
                continue  # stale entry
            embedding = meta.get("_embedding")
            if not embedding:
                continue
            # Cosine similarity
            dot = sum(a * b for a, b in zip(query_vec, embedding))
            norm_q = math.sqrt(sum(x * x for x in query_vec)) or 1.0
            norm_e = math.sqrt(sum(x * x for x in embedding)) or 1.0
            score = dot / (norm_q * norm_e)
            scored.append((score, pos, meta))

        scored.sort(key=lambda x: -x[0])
        results = []
        for score, _, meta in scored[:k]:
            result = {k2: v for k2, v in meta.items() if k2 != "_embedding"}
            result["_score"] = score
            results.append(result)
        return results

    def delete(self, doc_id: str) -> None:
        """Mark a document as deleted (does not physically remove from FAISS)."""
        if doc_id in self._id_to_pos:
            pos = self._id_to_pos.pop(doc_id)
            self._metadata.pop(pos, None)
            self._save()

    @property
    def count(self) -> int:
        return len(self._id_to_pos)


class RAGEngine:
    """Embeds, stores, and retrieves behavioral context chunks.

    Uses OpenSearch k-NN when a BaseDBConnector is provided,
    otherwise falls back to local FAISS storage.
    """

    def __init__(
        self,
        llm: Any,
        db: Optional[BaseDBConnector] = None,
        index_name: str = "hook-vectors",
        faiss_dir: str = "data/faiss",
        top_k: int = 5,
    ) -> None:
        self.llm = llm
        self.db = db
        self.index_name = os.environ.get("HOOK_VECTOR_INDEX", index_name)
        self.top_k = top_k

        # Determine backend
        if self.db is not None:
            self._backend = "opensearch"
            self._ensure_vector_index()
            self._faiss = None
        else:
            self._backend = "faiss"
            dims = self.llm.embedding_dimension if self.llm else 64
            self._faiss = FAISSStore(persist_dir=faiss_dir, dims=dims)
            logger.info("RAG using FAISS backend (dims=%d)", dims)

    def _ensure_vector_index(self) -> None:
        """Create the OpenSearch vector index if it does not exist."""
        if self.db is None:
            return

        dims = 768
        if self.llm is not None:
            try:
                test_vec = self.llm.embed("test")
                dims = len(test_vec)
            except Exception as exc:
                logger.warning("Could not detect embedding dimension: %s", exc)
                if hasattr(self.llm, "embedding_dimension"):
                    dims = self.llm.embedding_dimension

        mappings = {
            "properties": {
                "text": {"type": "text"},
                "embedding": {"type": "knn_vector", "dimension": dims},
                "category": {"type": "keyword"},
                "source": {"type": "keyword"},
                "timestamp": {"type": "date"},
                "id": {"type": "keyword"},
            }
        }
        settings = {"index": {"knn": True}}
        self.db.ensure_index(self.index_name, mappings, settings)

    def store(
        self,
        text: str,
        category: str = "general",
        source: str = "unknown",
        metadata: Optional[dict] = None,
    ) -> str:
        """Embed text and store in the vector index. Returns the document ID."""
        if not text or not text.strip():
            logger.warning("Skipping empty text for storage")
            return ""

        doc_id = hashlib.sha256(text.encode()).hexdigest()[:32]
        embedding = self.llm.embed(text)
        if not embedding:
            raise ValueError("Embedding generation returned empty result")

        doc = {
            "id": doc_id,
            "text": text,
            "embedding": embedding,
            "category": category,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if metadata:
            doc.update(metadata)

        if self._backend == "opensearch" and self.db is not None:
            self.db.index_document(self.index_name, doc_id, doc)
        elif self._faiss is not None:
            self._faiss.store(doc_id, embedding, doc)

        logger.debug("Stored RAG chunk: %s (category=%s)", doc_id[:8], category)
        return doc_id

    def bulk_store(
        self,
        chunks: list[str],
        category: str = "general",
        source: str = "unknown",
        metadata: Optional[dict] = None,
    ) -> list[str]:
        """Embed and store multiple chunks. Returns list of document IDs."""
        ids = []
        for chunk in chunks:
            try:
                ids.append(self.store(chunk, category=category, source=source, metadata=metadata))
            except Exception as exc:
                logger.error("Failed to store chunk: %s", exc)
        return ids

    def retrieve(
        self,
        query: str,
        k: Optional[int] = None,
        category: Optional[str] = None,
    ) -> list[dict]:
        """Retrieve top-k most similar stored chunks for a query.

        Falls back to keyword search if embedding fails.
        """
        k = k or self.top_k

        # Try embedding the query
        query_vec = None
        if self.llm is not None:
            try:
                query_vec = self.llm.embed(query)
            except Exception as exc:
                logger.warning("Embed for retrieve failed: %s; using keyword fallback", exc)

        if self._backend == "faiss" and self._faiss is not None:
            if query_vec is not None:
                return self._faiss.search(query_vec, k=k, category=category)
            return []

        # OpenSearch backend
        if self.db is None:
            return []

        # Try k-NN search first
        if query_vec is not None:
            filters = {"term": {"category": category}} if category else None
            try:
                hits = self.db.knn_search(
                    index=self.index_name,
                    vector=query_vec,
                    k=k,
                    filters=filters,
                )
                return hits
            except Exception as exc:
                logger.warning("KNN search failed (%s), falling back to keyword", exc)

        # Keyword fallback
        try:
            query_dict: dict[str, Any] = {
                "query": {
                    "bool": {
                        "must": [
                            {"multi_match": {
                                "query": query,
                                "fields": ["text", "source", "category"],
                            }}
                        ]
                    }
                },
                "size": k,
            }
            if category:
                query_dict["query"]["bool"]["filter"] = [
                    {"term": {"category": category}}
                ]
            return self.db.search(index=self.index_name, query=query_dict, size=k)
        except Exception as exc:
            logger.error("Keyword search fallback also failed: %s", exc)
            return []

    def build_context_string(
        self,
        query: str,
        k: Optional[int] = None,
        category: Optional[str] = None,
        prefix: str = "### Relevant Behavioral Context\n",
    ) -> str:
        """Retrieve top-k chunks and format as a numbered context block for prompt injection."""
        hits = self.retrieve(query, k=k, category=category)
        if not hits:
            return prefix + "_No relevant context found._\n"

        lines = [prefix]
        for i, hit in enumerate(hits, 1):
            text = hit.get("text", "")
            src = hit.get("source", "?")
            cat = hit.get("category", "?")
            lines.append(f"{i}. [{cat}/{src}] {text}")

        return "\n".join(lines) + "\n"
