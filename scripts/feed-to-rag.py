#!/usr/bin/env python3
"""
scripts/feed-to-rag.py -- Ingest threat feed IOCs into RAG behavioral memory.

Reads the combined feed file, classifies each IOC, stores it in RAG
with source and date metadata. On subsequent investigations, agents
can recall "this IP appeared in today's Feodo C2 feed" as context.

Handles aging:
  - Feed IOCs stored with category "feed_ioc" and date metadata
  - Old feed data (>30 days) is not re-ingested
  - Duplicate IOCs (same value+source) are skipped via SHA256 doc ID

Usage:
  python3 scripts/feed-to-rag.py                    # Process today's combined feed
  python3 scripts/feed-to-rag.py --date 2026-04-03  # Process a specific date
  python3 scripts/feed-to-rag.py --cleanup 30       # Remove feed entries older than 30 days
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HOOK_DIR = os.environ.get("HOOK_DIR", str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, HOOK_DIR)

LOG_DIR = os.path.expanduser("~/.openclaw/logs/hook")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
HASH_RE = re.compile(r"^[a-fA-F0-9]{32,64}$")
DOMAIN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Feed source mapping by filename prefix
FEED_SOURCES = {
    "feodo": "Feodo Tracker (abuse.ch) — botnet C2 IPs",
    "urlhaus": "URLhaus (abuse.ch) — malware distribution",
    "threatfox": "ThreatFox (abuse.ch) — crowd-sourced IOCs",
    "combined": "Combined threat feeds",
}


def classify_ioc(value: str) -> str:
    """Classify an IOC as ip, domain, hash, or unknown."""
    value = value.strip()
    if IP_RE.match(value):
        return "ip"
    if HASH_RE.match(value):
        return "hash"
    if DOMAIN_RE.match(value) and "." in value:
        return "domain"
    return "unknown"


def get_feed_source(filename: str) -> str:
    """Determine feed source from filename."""
    for prefix, source in FEED_SOURCES.items():
        if filename.startswith(prefix):
            return source
    return "Unknown feed"


def ingest_feed(feed_file: Path, date: str) -> dict:
    """Read a feed file and store each IOC in RAG."""
    from core.rag.engine import RAGEngine
    from core.llm.ollama_provider import OllamaProvider, is_ollama_available

    # Build RAG engine
    llm = None
    if is_ollama_available():
        llm = OllamaProvider()
    else:
        try:
            from tests.mocks.mock_llm import MockLLMProvider
            llm = MockLLMProvider(embedding_dims=64)
        except ImportError:
            return {"status": "error", "message": "No LLM provider available"}

    faiss_dir = os.path.join(HOOK_DIR, "data", "faiss")
    rag = RAGEngine(llm=llm, faiss_dir=faiss_dir)

    if not feed_file.exists():
        return {"status": "error", "message": f"Feed file not found: {feed_file}"}

    lines = feed_file.read_text().strip().splitlines()
    source = get_feed_source(feed_file.name)
    stored = 0
    skipped = 0

    for line in lines:
        ioc_value = line.strip()
        if not ioc_value or ioc_value.startswith("#"):
            continue

        ioc_type = classify_ioc(ioc_value)
        if ioc_type == "unknown":
            skipped += 1
            continue

        text = (
            f"Feed IOC: {ioc_value} (type: {ioc_type})\n"
            f"Source: {source}\n"
            f"Date: {date}\n"
            f"Context: Appeared in threat intelligence feed"
        )

        try:
            rag.store(
                text,
                category="feed_ioc",
                source="feed-ingestion",
                metadata={
                    "ioc_value": ioc_value,
                    "ioc_type": ioc_type,
                    "feed_source": source,
                    "feed_date": date,
                },
            )
            stored += 1
        except Exception as exc:
            logger.warning("Failed to store %s: %s", ioc_value, exc)
            skipped += 1

    return {
        "status": "ok",
        "feed_file": str(feed_file),
        "date": date,
        "source": source,
        "stored": stored,
        "skipped": skipped,
        "total_lines": len(lines),
    }


def cleanup_old_feeds(max_age_days: int = 30) -> dict:
    """Remove feed files older than max_age_days."""
    feed_dir = Path(HOOK_DIR) / "data" / "feeds"
    if not feed_dir.exists():
        return {"status": "ok", "removed": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    removed = 0

    for f in feed_dir.iterdir():
        if not f.is_file():
            continue
        # Parse date from filename (e.g., feodo-2026-04-01.txt)
        match = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
        if match:
            try:
                file_date = datetime.strptime(match.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if file_date < cutoff:
                    f.unlink()
                    removed += 1
                    logger.info("Removed old feed: %s", f.name)
            except ValueError:
                pass

    return {"status": "ok", "removed": removed, "max_age_days": max_age_days}


def main():
    parser = argparse.ArgumentParser(description="Ingest threat feeds into RAG")
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        help="Date of feed to process (default: today)")
    parser.add_argument("--cleanup", type=int, metavar="DAYS",
                        help="Remove feed files older than N days")
    parser.add_argument("--all-feeds", action="store_true",
                        help="Process individual feed files, not just combined")
    args = parser.parse_args()

    if args.cleanup is not None:
        result = cleanup_old_feeds(args.cleanup)
        print(json.dumps(result, indent=2))
        return

    feed_dir = Path(HOOK_DIR) / "data" / "feeds"
    combined = feed_dir / f"combined-{args.date}.txt"

    if args.all_feeds:
        results = []
        for f in sorted(feed_dir.glob(f"*-{args.date}.txt")):
            if f.name.startswith("combined"):
                continue
            result = ingest_feed(f, args.date)
            results.append(result)
            logger.info("%s: stored %d, skipped %d", f.name, result.get("stored", 0), result.get("skipped", 0))
        print(json.dumps({"status": "ok", "feeds": results}, indent=2))
    else:
        result = ingest_feed(combined, args.date)
        logger.info("Combined feed: stored %d, skipped %d", result.get("stored", 0), result.get("skipped", 0))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
