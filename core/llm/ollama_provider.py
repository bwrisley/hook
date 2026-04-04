"""
core/llm/ollama_provider.py -- Ollama LLM provider for HOOK.

Provides embeddings via nomic-embed-text and chat via configurable model.
Used by RAG engine, baseliner, and rag-inject.py.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)

OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


class OllamaProvider:
    """LLM provider using local Ollama instance."""

    def __init__(
        self,
        embed_model: str = "nomic-embed-text",
        chat_model: str = "qwen2.5:14b",
        base_url: str | None = None,
    ) -> None:
        self.base_url = base_url or OLLAMA_BASE
        self.embed_model = embed_model
        self.chat_model = chat_model
        self._embedding_dims: int | None = None

    @property
    def embedding_dimension(self) -> int:
        if self._embedding_dims is None:
            # Detect by running a test embedding
            try:
                vec = self.embed("test")
                self._embedding_dims = len(vec)
            except Exception:
                self._embedding_dims = 768  # nomic-embed-text default
        return self._embedding_dims

    def embed(self, text: str) -> list[float]:
        """Generate an embedding vector via Ollama."""
        body = json.dumps({"model": self.embed_model, "input": text}).encode()
        req = Request(
            f"{self.base_url}/api/embed",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                embeddings = data.get("embeddings", [])
                if embeddings:
                    return embeddings[0]
                logger.error("Ollama embed returned no embeddings")
                return []
        except URLError as exc:
            logger.error("Ollama embed failed: %s", exc)
            raise

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Send a chat completion request to Ollama."""
        body = json.dumps({
            "model": self.chat_model,
            "messages": messages,
            "stream": False,
        }).encode()
        req = Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                return data.get("message", {}).get("content", "")
        except URLError as exc:
            logger.error("Ollama chat failed: %s", exc)
            raise


def is_ollama_available(base_url: str | None = None) -> bool:
    """Check if Ollama is running."""
    url = base_url or OLLAMA_BASE
    try:
        with urlopen(f"{url}/api/tags", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False
