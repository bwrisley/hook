#!/usr/bin/env python3
"""
scripts/rag-inject.py -- CLI interface for HOOK's RAG behavioral memory.

Called by agents via exec to store and retrieve behavioral context.
Follows the same pattern as investigation.sh and enrichment scripts.

Usage:
  python3 $HOOK_DIR/scripts/rag-inject.py query "45.77.65.211" [--category ioc_verdict] [--k 5]
  python3 $HOOK_DIR/scripts/rag-inject.py store-verdict --ioc "45.77.65.211" --type ip --verdict "HIGH risk, Cobalt Strike C2"
  python3 $HOOK_DIR/scripts/rag-inject.py store-finding --inv INV-20260302-001 --agent osint-researcher --summary "C2 confirmed"
  python3 $HOOK_DIR/scripts/rag-inject.py store-ttp --technique T1059.001 --description "PowerShell execution" [--actor "APT29"]
  python3 $HOOK_DIR/scripts/rag-inject.py store-baseline --identifier sensor-dmz-01 --summary "Normal traffic patterns..."
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Setup path so core modules can be imported
HOOK_DIR = os.environ.get("HOOK_DIR", str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, HOOK_DIR)

from core.rag.engine import RAGEngine
from core.rag.memory import BehavioralMemory

LOG_DIR = os.path.expanduser("~/.openclaw/logs/hook")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",
)
logger = logging.getLogger(__name__)


def _log_jsonl(action: str, data: dict) -> None:
    """Append structured log entry."""
    log_file = os.path.join(LOG_DIR, f"rag-{datetime.now().strftime('%Y-%m-%d')}.jsonl")
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        **data,
    }
    try:
        with open(log_file, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


def _build_rag() -> tuple[RAGEngine, BehavioralMemory]:
    """Construct RAG engine with appropriate backend."""
    db = None
    llm = None

    # Try OpenSearch backend
    opensearch_host = os.environ.get("HOOK_OPENSEARCH_HOST")
    if opensearch_host:
        try:
            from core.db.connector import OpenSearchConnector
            db = OpenSearchConnector(host=opensearch_host)
        except Exception as exc:
            logger.warning("OpenSearch unavailable: %s; using FAISS fallback", exc)

    # Try to get an LLM for embeddings
    # For now, use a simple deterministic embedder if no LLM configured
    try:
        from tests.mocks.mock_llm import MockLLMProvider
        llm = MockLLMProvider(embedding_dims=64)
    except ImportError:
        pass

    if llm is None:
        print(json.dumps({"status": "error", "message": "No LLM provider available for embeddings"}))
        sys.exit(1)

    faiss_dir = os.path.join(HOOK_DIR, "data", "faiss")
    rag = RAGEngine(llm=llm, db=db, faiss_dir=faiss_dir)
    memory = BehavioralMemory(rag)
    return rag, memory


def cmd_query(args: argparse.Namespace) -> None:
    """Query RAG for relevant context."""
    _, memory = _build_rag()

    if args.category == "ioc_verdict":
        result = memory.recall_ioc(args.query, k=args.k)
    elif args.category == "network_baseline":
        result = memory.recall_baseline(args.query, k=args.k)
    elif args.category == "investigation_finding":
        result = memory.recall_findings(args.query, k=args.k)
    elif args.category == "ttp_history":
        result = memory.recall_ttps(args.query, k=args.k)
    else:
        rag, _ = _build_rag()
        result = rag.build_context_string(args.query, k=args.k, category=args.category)

    _log_jsonl("query", {"query": args.query, "category": args.category, "k": args.k})
    print(result)


def cmd_store_verdict(args: argparse.Namespace) -> None:
    """Store an IOC verdict."""
    _, memory = _build_rag()
    doc_id = memory.store_verdict(
        ioc_value=args.ioc,
        ioc_type=args.type,
        verdict=args.verdict,
        source_agent=args.agent or "osint-researcher",
        confidence=args.confidence or "medium",
    )
    _log_jsonl("store_verdict", {"ioc": args.ioc, "type": args.type, "doc_id": doc_id})
    print(json.dumps({"status": "ok", "doc_id": doc_id, "ioc": args.ioc}))


def cmd_store_finding(args: argparse.Namespace) -> None:
    """Store an investigation finding."""
    _, memory = _build_rag()
    doc_id = memory.store_finding(
        investigation_id=args.inv,
        agent=args.agent,
        summary=args.summary,
        detail=args.detail or "",
    )
    _log_jsonl("store_finding", {"inv": args.inv, "agent": args.agent, "doc_id": doc_id})
    print(json.dumps({"status": "ok", "doc_id": doc_id, "investigation": args.inv}))


def cmd_store_ttp(args: argparse.Namespace) -> None:
    """Store a TTP observation."""
    _, memory = _build_rag()
    doc_id = memory.store_ttp(
        technique_id=args.technique,
        description=args.description,
        threat_actor=args.actor or "",
    )
    _log_jsonl("store_ttp", {"technique": args.technique, "doc_id": doc_id})
    print(json.dumps({"status": "ok", "doc_id": doc_id, "technique": args.technique}))


def cmd_store_baseline(args: argparse.Namespace) -> None:
    """Store a behavioral baseline."""
    _, memory = _build_rag()
    doc_id = memory.store_baseline(
        identifier=args.identifier,
        summary=args.summary,
    )
    _log_jsonl("store_baseline", {"identifier": args.identifier, "doc_id": doc_id})
    print(json.dumps({"status": "ok", "doc_id": doc_id, "identifier": args.identifier}))


def main() -> None:
    parser = argparse.ArgumentParser(description="HOOK RAG Behavioral Memory CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # query
    p_query = subparsers.add_parser("query", help="Query RAG for relevant context")
    p_query.add_argument("query", help="Search query text")
    p_query.add_argument("--category", default=None, help="Filter by category")
    p_query.add_argument("--k", type=int, default=5, help="Number of results")
    p_query.set_defaults(func=cmd_query)

    # store-verdict
    p_verdict = subparsers.add_parser("store-verdict", help="Store an IOC verdict")
    p_verdict.add_argument("--ioc", required=True, help="IOC value")
    p_verdict.add_argument("--type", required=True, help="IOC type (ip/domain/hash)")
    p_verdict.add_argument("--verdict", required=True, help="Verdict summary")
    p_verdict.add_argument("--agent", default="osint-researcher", help="Source agent")
    p_verdict.add_argument("--confidence", default="medium", help="Confidence level")
    p_verdict.set_defaults(func=cmd_store_verdict)

    # store-finding
    p_finding = subparsers.add_parser("store-finding", help="Store an investigation finding")
    p_finding.add_argument("--inv", required=True, help="Investigation ID")
    p_finding.add_argument("--agent", required=True, help="Agent that produced the finding")
    p_finding.add_argument("--summary", required=True, help="Finding summary")
    p_finding.add_argument("--detail", default="", help="Optional detailed content")
    p_finding.set_defaults(func=cmd_store_finding)

    # store-ttp
    p_ttp = subparsers.add_parser("store-ttp", help="Store a TTP observation")
    p_ttp.add_argument("--technique", required=True, help="MITRE technique ID")
    p_ttp.add_argument("--description", required=True, help="Description")
    p_ttp.add_argument("--actor", default="", help="Optional threat actor")
    p_ttp.set_defaults(func=cmd_store_ttp)

    # store-baseline
    p_baseline = subparsers.add_parser("store-baseline", help="Store a behavioral baseline")
    p_baseline.add_argument("--identifier", required=True, help="Sensor/network identifier")
    p_baseline.add_argument("--summary", required=True, help="Baseline summary text")
    p_baseline.set_defaults(func=cmd_store_baseline)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
