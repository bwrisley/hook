#!/usr/bin/env python3
"""
scripts/run-baseliner.py -- Entry point for HOOK's behavioral baseliner.

Runs via LaunchAgent every 6 hours. Queries log sources for recent activity,
builds behavioral baselines, and stores them in the RAG engine.

Requires HOOK_OPENSEARCH_HOST to be set; no-ops gracefully otherwise.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HOOK_DIR = os.environ.get("HOOK_DIR", str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, HOOK_DIR)

LOG_DIR = os.path.expanduser("~/.openclaw/logs/hook")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(LOG_DIR, f"baseliner-{datetime.now().strftime('%Y-%m-%d')}.log")
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("hook.baseliner")


def main() -> None:
    # Check if OpenSearch is configured
    opensearch_host = os.environ.get("HOOK_OPENSEARCH_HOST")
    if not opensearch_host:
        logger.info("HOOK_OPENSEARCH_HOST not set; baseliner skipping (no log source)")
        print(json.dumps({"status": "skipped", "reason": "no_opensearch"}))
        return

    try:
        from core.db.connector import OpenSearchConnector
        from core.rag.engine import RAGEngine
        from core.rag.baseliner import Baseliner
    except ImportError as exc:
        logger.error("Failed to import HOOK modules: %s", exc)
        print(json.dumps({"status": "error", "message": str(exc)}))
        sys.exit(1)

    # Initialize components
    try:
        db = OpenSearchConnector(host=opensearch_host)
    except Exception as exc:
        logger.error("OpenSearch connection failed: %s", exc)
        print(json.dumps({"status": "error", "message": f"OpenSearch: {exc}"}))
        sys.exit(1)

    # LLM for embeddings and summarization
    llm = None
    try:
        from core.llm.ollama_provider import OllamaProvider, is_ollama_available
        if is_ollama_available():
            llm = OllamaProvider()
            logger.info("Using Ollama (%s / %s)", llm.embed_model, llm.chat_model)
    except ImportError:
        pass

    if llm is None:
        try:
            from tests.mocks.mock_llm import MockLLMProvider
            llm = MockLLMProvider(embedding_dims=64)
            logger.info("Ollama not available; using mock LLM")
        except ImportError:
            logger.error("No LLM provider available")
            print(json.dumps({"status": "error", "message": "No LLM provider"}))
            sys.exit(1)

    rag = RAGEngine(llm=llm, db=db)
    baseliner = Baseliner(db=db, llm=llm, rag=rag)

    hours = int(os.environ.get("HOOK_BASELINE_HOURS", "6"))
    index = os.environ.get("HOOK_LOG_INDEX", "logs-*")

    logger.info("Running baseliner: %d hours, index=%s", hours, index)
    result = baseliner.run(hours=hours, index=index)
    logger.info("Baseliner result: %s", json.dumps(result, default=str))

    # Log structured output
    log_file = os.path.join(LOG_DIR, f"baseliner-{datetime.now().strftime('%Y-%m-%d')}.jsonl")
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "baseliner_run",
        **result,
    }
    with open(log_file, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")

    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
