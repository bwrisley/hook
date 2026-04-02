#!/usr/bin/env python3
"""
scripts/query-logs.py -- Natural language log query interface for HOOK.

Called by the log-querier agent via exec. Translates analyst questions
into OpenSearch DSL queries, executes them, and returns structured results.

Usage:
  python3 $HOOK_DIR/scripts/query-logs.py "Show denied connections to port 3389"
  python3 $HOOK_DIR/scripts/query-logs.py "DNS queries to suspicious domains" --index "dns-*"
  python3 $HOOK_DIR/scripts/query-logs.py --fields "logs-*"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HOOK_DIR = os.environ.get("HOOK_DIR", str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, HOOK_DIR)

LOG_DIR = os.path.expanduser("~/.openclaw/logs/hook")
os.makedirs(LOG_DIR, exist_ok=True)


def _log_jsonl(action: str, data: dict) -> None:
    log_file = os.path.join(LOG_DIR, f"log-querier-{datetime.now().strftime('%Y-%m-%d')}.jsonl")
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


def main() -> None:
    parser = argparse.ArgumentParser(description="HOOK Log Querier CLI")
    parser.add_argument("question", nargs="?", help="Natural language query")
    parser.add_argument("--index", default="logs-*", help="OpenSearch index pattern")
    parser.add_argument("--hours", type=int, default=24, help="Hours of logs to search")
    parser.add_argument("--max-results", type=int, default=50, help="Max results to return")
    parser.add_argument("--fields", nargs="?", const="logs-*", default=None,
                        help="Discover available fields for an index")
    args = parser.parse_args()

    # Check OpenSearch config
    opensearch_host = os.environ.get("HOOK_OPENSEARCH_HOST")
    if not opensearch_host:
        result = {"status": "error", "message": "HOOK_OPENSEARCH_HOST not configured"}
        print(json.dumps(result))
        _log_jsonl("query_skipped", result)
        return

    try:
        from core.db.connector import OpenSearchConnector
        from core.db.querier import LogQuerier
    except ImportError as exc:
        print(json.dumps({"status": "error", "message": f"Import failed: {exc}"}))
        return

    try:
        db = OpenSearchConnector(host=opensearch_host)
    except Exception as exc:
        print(json.dumps({"status": "error", "message": f"OpenSearch connection failed: {exc}"}))
        return

    # Field discovery mode
    if args.fields is not None:
        index = args.fields
        try:
            llm_placeholder = type("LLM", (), {"chat": lambda self, m: "", "embed": lambda self, t: [0.0] * 64, "embedding_dimension": 64})()
            querier = LogQuerier(db=db, llm=llm_placeholder)
            fields = querier.discover_fields(index)
            print(json.dumps({"status": "ok", "index": index, "fields": fields, "count": len(fields)}))
            _log_jsonl("field_discovery", {"index": index, "field_count": len(fields)})
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}))
        return

    # Query mode
    if not args.question:
        print(json.dumps({"status": "error", "message": "No question provided"}))
        return

    # Get LLM for query translation
    llm = None
    try:
        from tests.mocks.mock_llm import MockLLMProvider
        llm = MockLLMProvider(embedding_dims=64)
    except ImportError:
        print(json.dumps({"status": "error", "message": "No LLM provider available"}))
        return

    querier = LogQuerier(db=db, llm=llm)
    result = querier.query(
        question=args.question,
        index=args.index,
        max_results=args.max_results,
    )

    _log_jsonl("query", {
        "question": args.question,
        "index": args.index,
        "status": result.get("status"),
        "count": result.get("count", 0),
    })

    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
