#!/usr/bin/env python3
"""
scripts/watch-check.py -- Re-enrich watched IOCs and detect risk changes.

Runs on schedule (every 4 hours via LaunchAgent). For each active
watched IOC, re-runs enrichment, compares risk level against the
stored value, and creates notifications + auto-investigations
when risk changes.

Usage:
  python3 scripts/watch-check.py              # Check all watched IOCs
  python3 scripts/watch-check.py --dry-run    # Show what would be checked without enriching
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

HOOK_DIR = os.environ.get("HOOK_DIR", str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, HOOK_DIR)

LOG_DIR = os.path.expanduser("~/.openclaw/logs/hook")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [watch-check] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"watch-check-{datetime.now().strftime('%Y-%m-%d')}.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

RISK_LEVELS = {"CLEAN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4, "UNKNOWN": -1}


def extract_risk(enrichment_output: str) -> str:
    """Extract risk level from enrichment script output."""
    try:
        data = json.loads(enrichment_output)
        return data.get("risk", "UNKNOWN").upper()
    except json.JSONDecodeError:
        # Try to find risk in text output
        match = re.search(r'"risk"\s*:\s*"(\w+)"', enrichment_output)
        if match:
            return match.group(1).upper()
    return "UNKNOWN"


def build_summary(ioc_value: str, ioc_type: str, old_risk: str, new_risk: str, enrichment_output: str) -> str:
    """Build a human-readable change summary."""
    direction = "escalated" if RISK_LEVELS.get(new_risk, -1) > RISK_LEVELS.get(old_risk, -1) else "de-escalated"
    summary = f"Risk {direction}: {ioc_value} ({ioc_type}) changed from {old_risk} to {new_risk}"

    # Extract key details from enrichment
    try:
        data = json.loads(enrichment_output)
        sources = data.get("sources", {})
        details = []
        vt = sources.get("virustotal", {})
        if vt:
            details.append(f"VT: {vt.get('detections', '?')} detections")
        abuse = sources.get("abuseipdb", {})
        if abuse:
            details.append(f"AbuseIPDB: {abuse.get('confidence', '?')}% confidence, {abuse.get('reports', '?')} reports")
        if details:
            summary += f" ({', '.join(details)})"
    except Exception:
        pass

    return summary


def enrich_ioc(ioc_value: str, ioc_type: str) -> tuple[str, str]:
    """Run enrichment script and return (risk, raw_output)."""
    script_map = {
        "ip": f"{HOOK_DIR}/scripts/enrich-ip.sh",
        "domain": f"{HOOK_DIR}/scripts/enrich-domain.sh",
        "hash": f"{HOOK_DIR}/scripts/enrich-hash.sh",
    }

    script = script_map.get(ioc_type)
    if not script or not os.path.isfile(script):
        return "UNKNOWN", json.dumps({"error": f"No enrichment script for type: {ioc_type}"})

    try:
        result = subprocess.run(
            [script, "--no-cache", ioc_value],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "HOOK_DIR": HOOK_DIR},
        )
        output = result.stdout.strip()
        risk = extract_risk(output)
        return risk, output
    except subprocess.TimeoutExpired:
        return "UNKNOWN", json.dumps({"error": "Enrichment timed out"})
    except Exception as exc:
        return "UNKNOWN", json.dumps({"error": str(exc)})


def main():
    parser = argparse.ArgumentParser(description="Re-enrich watched IOCs")
    parser.add_argument("--dry-run", action="store_true", help="Show watchlist without enriching")
    args = parser.parse_args()

    from web.api.watchlist import WatchlistDB
    from web.api.server import WebSessionDB, DATA_DIR

    db_path = str(DATA_DIR / "hook-web.db")
    watchlist_db = WatchlistDB(db_path)
    web_db = WebSessionDB(db_path)

    watched = watchlist_db.get_all_active()
    logger.info("Watch check starting: %d active IOCs", len(watched))

    if args.dry_run:
        for w in watched:
            print(f"  {w['ioc_value']} ({w['ioc_type']}) — current: {w['current_risk']}, checks: {w['check_count']}, user: {w['user_id']}")
        return

    changes = 0
    for w in watched:
        ioc_value = w["ioc_value"]
        ioc_type = w["ioc_type"]
        old_risk = w["current_risk"]

        logger.info("Checking %s (%s) — current risk: %s", ioc_value, ioc_type, old_risk)

        new_risk, raw_output = enrich_ioc(ioc_value, ioc_type)
        summary = build_summary(ioc_value, ioc_type, old_risk, new_risk, raw_output)

        # Update risk and get users to notify
        notify_users = watchlist_db.update_risk(ioc_value, new_risk, summary, raw_output)

        if notify_users:
            changes += 1
            logger.info("RISK CHANGE: %s", summary)

            for user_id in notify_users:
                # Create auto-investigation
                conv_id = str(uuid.uuid4())[:8]
                web_db.get_or_create(conv_id, user_id=user_id)
                web_db.add_message(conv_id, "assistant", f"Watchlist Alert: {summary}\n\nThis IOC is on your watchlist and its risk profile has changed. Review the updated enrichment data below.", agent="coordinator", msg_type="coordinator")
                web_db.add_message(conv_id, "assistant", raw_output[:3000], agent="osint-researcher", msg_type="agent_result")

                # Create notification
                watchlist_db.create_notification(
                    user_id=user_id,
                    title=f"Risk change: {ioc_value}",
                    body=summary,
                    type="watch_alert",
                    ioc_value=ioc_value,
                    conversation_id=conv_id,
                )
                logger.info("Notified user %s, created investigation %s", user_id, conv_id)
        else:
            logger.info("No change: %s remains %s", ioc_value, new_risk)

    logger.info("Watch check complete: %d IOCs checked, %d changes detected", len(watched), changes)

    # Log structured output
    log_file = os.path.join(LOG_DIR, f"watch-check-{datetime.now().strftime('%Y-%m-%d')}.jsonl")
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "watch_check",
        "total": len(watched),
        "changes": changes,
    }
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


if __name__ == "__main__":
    main()
