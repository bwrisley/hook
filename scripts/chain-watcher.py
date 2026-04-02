#!/usr/bin/env python3
"""
HOOK Chain Watcher v2
=====================
Monitors #hook Slack channel for subagent announce messages and posts
stage-specific continue nudges to drive the full analysis chain.

Chain sequence: triage-analyst -> osint-researcher -> incident-responder -> report-writer

After each announce, the watcher:
1. Identifies which agent just finished
2. Posts a stage-specific nudge naming the next agent
3. Starts a timeout watching for the next announce
4. Re-nudges if nothing arrives within the timeout window
5. Posts a stall warning after max retries

Usage:
    python3 chain-watcher.py           # Start watching
    python3 chain-watcher.py --reset   # Clear state file and exit
    python3 chain-watcher.py --dry-run # Watch but don't post (debug mode)

Env vars:
    SLACK_BOT_TOKEN         Bot token (xoxb-...) - also read from openclaw.json
    HOOK_SLACK_CHANNEL_ID   Channel ID for #hook (default: C0AHNAL1370)

PUNCH Cyber Analytics Group
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
import urllib.parse
import argparse
import signal
import re
from pathlib import Path
from datetime import datetime, timezone

# --- Configuration --------------------------------------------------------

BOT_USER_ID = "U0AHHUNEY4B"
DEFAULT_CHANNEL_ID = "C0AHNAL1370"
STATE_FILE = Path(__file__).parent.parent / "data" / "chain-watcher-state.json"
POLL_INTERVAL = 3            # seconds between Slack API polls
POST_CONTINUE_DELAY = 3      # seconds after announce before posting nudge
STAGE_TIMEOUT = 120          # seconds to wait for next announce before re-nudge
MAX_RENUDGE = 3              # max re-nudge attempts before declaring stall
MAX_RETRIES = 3              # retries for Slack API calls

# --- Chain Definition -----------------------------------------------------
# Ordered agent sequence and stage-specific nudge messages

CHAIN_SEQUENCE = [
    "triage-analyst",
    "osint-researcher",
    "incident-responder",
    "report-writer",
]

CHAIN_NUDGES = {
    "triage-analyst": (
        "osint-researcher",
        "continue — route to osint-researcher to enrich all extracted IOCs "
        "from triage findings using VirusTotal, AbuseIPDB, Censys, and WHOIS"
    ),
    "osint-researcher": (
        "incident-responder",
        "continue — route to incident-responder for containment guidance, "
        "evidence preservation steps, and remediation recommendations based "
        "on the triage verdict and OSINT enrichment results"
    ),
    "incident-responder": (
        "report-writer",
        "continue — route to report-writer to produce an executive summary "
        "for the CISO and a detailed technical report covering the full "
        "investigation chain: triage, enrichment, and IR guidance"
    ),
    "report-writer": (
        None,
        None,  # End of chain
    ),
}

# --- Globals --------------------------------------------------------------

running = True


def signal_handler(sig, frame):
    global running
    print(f"\n[chain-watcher] Caught signal {sig}, shutting down...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# --- Token Resolution -----------------------------------------------------

def get_slack_token():
    """Resolve Slack bot token from env or openclaw.json."""
    token = os.environ.get("SLACK_BOT_TOKEN")
    if token:
        return token
    oc_config = Path.home() / ".openclaw" / "openclaw.json"
    if oc_config.exists():
        try:
            with open(oc_config) as f:
                config = json.load(f)
            token = config.get("channels", {}).get("slack", {}).get("botToken")
            if token:
                return token
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[chain-watcher] Warning: Could not read openclaw.json: {e}")
    return None


def get_channel_id():
    """Resolve channel ID from env or default."""
    return os.environ.get("HOOK_SLACK_CHANNEL_ID", DEFAULT_CHANNEL_ID)


# --- State Management -----------------------------------------------------

def load_state():
    """Load watcher state."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "last_ts": "0",
        "announces_seen": 0,
        "continues_posted": 0,
        "chains_completed": 0,
    }


def save_state(state):
    """Persist watcher state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def reset_state():
    """Clear state file for fresh start."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
        print(f"[chain-watcher] State file removed: {STATE_FILE}")
    else:
        print(f"[chain-watcher] No state file found at: {STATE_FILE}")


# --- Slack API -------------------------------------------------------------

def slack_api(method, token, params=None, body=None):
    """Make a Slack API call. Returns parsed JSON or None on failure."""
    url = f"https://slack.com/api/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    data = json.dumps(body).encode("utf-8") if body else None

    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("ok"):
                    return result
                if result.get("error") == "ratelimited":
                    retry_after = int(result.get("headers", {}).get("Retry-After", 5))
                    print(f"[chain-watcher] Rate limited, waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue
                print(f"[chain-watcher] Slack API error ({method}): {result.get('error')}")
                return None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", 5))
                print(f"[chain-watcher] Rate limited (429), waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            print(f"[chain-watcher] HTTP error ({method}): {e.code} {e.reason}")
        except urllib.error.URLError as e:
            print(f"[chain-watcher] Network error ({method}): {e.reason}")
        except Exception as e:
            print(f"[chain-watcher] Unexpected error ({method}): {e}")
        if attempt < MAX_RETRIES - 1:
            time.sleep(2 ** attempt)
    return None


def fetch_messages(token, channel_id, oldest_ts):
    """Fetch channel messages newer than oldest_ts."""
    return slack_api("conversations.history", token, params={
        "channel": channel_id,
        "oldest": oldest_ts,
        "limit": 50,
        "inclusive": False,
    })


def post_message(token, channel_id, text, thread_ts=None):
    """Post a message to the channel."""
    body = {"channel": channel_id, "text": text}
    if thread_ts:
        body["thread_ts"] = thread_ts
    return slack_api("chat.postMessage", token, body=body)


# --- Agent Detection -------------------------------------------------------

def extract_agent_from_announce(text):
    """
    Extract the agent name from an announce message.
    Pattern: "Subagent <agent-name> finished"
    Returns agent name string or None.
    """
    match = re.search(r'[Ss]ubagent\s+([\w-]+)\s+finished', text)
    if match:
        return match.group(1).lower().strip()

    # Fallback: check if any known agent name appears near "finished"
    text_lower = text.lower()
    for agent in CHAIN_SEQUENCE:
        if agent in text_lower and "finished" in text_lower:
            return agent
    return None


def is_announce_message(msg):
    """Detect subagent announce messages."""
    text = msg.get("text", "")
    text_lower = text.lower()
    return "subagent" in text_lower and "finished" in text_lower


def is_our_message(msg):
    """Check if a message is one we posted (avoid loops)."""
    text = msg.get("text", "")
    if f"<@{BOT_USER_ID}> continue" in text and "route to" in text.lower():
        return True
    if text.startswith("[HOOK Chain Watcher]"):
        return True
    return False


# --- Chain Logic -----------------------------------------------------------

def get_nudge_for_agent(agent_name):
    """
    Given the agent that just finished, return (next_agent, nudge_text).
    Returns (None, None) if end of chain.
    """
    if agent_name in CHAIN_NUDGES:
        return CHAIN_NUDGES[agent_name]
    print(f"[chain-watcher] Warning: Unknown agent '{agent_name}', using generic nudge")
    return "unknown", "continue"


def format_nudge(nudge_text):
    """Wrap nudge text with bot mention."""
    return f"<@{BOT_USER_ID}> {nudge_text}"


def format_status(text):
    """Format a status message from the watcher."""
    return f"[HOOK Chain Watcher] {text}"


# --- Main Loop -------------------------------------------------------------

def watch(token, channel_id, dry_run=False):
    """Main polling loop with stage-specific nudges and timeout re-nudge."""
    state = load_state()
    last_ts = state["last_ts"]
    announces_seen = state.get("announces_seen", 0)
    continues_posted = state.get("continues_posted", 0)
    chains_completed = state.get("chains_completed", 0)

    # Re-nudge tracking
    waiting_for_agent = None
    last_nudge_time = None
    renudge_count = 0
    active_thread_ts = None
    last_nudge_text = None

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[chain-watcher] HOOK Chain Watcher v2 started at {now}")
    print(f"[chain-watcher] Channel: {channel_id}")
    print(f"[chain-watcher] Bot user: {BOT_USER_ID}")
    print(f"[chain-watcher] Chain: {' -> '.join(CHAIN_SEQUENCE)}")
    print(f"[chain-watcher] Poll: {POLL_INTERVAL}s | Timeout: {STAGE_TIMEOUT}s | Max re-nudge: {MAX_RENUDGE}")
    print(f"[chain-watcher] Resuming from ts: {last_ts}")
    print(f"[chain-watcher] Stats: {announces_seen} announces, {continues_posted} continues, {chains_completed} chains")
    if dry_run:
        print(f"[chain-watcher] DRY RUN MODE -- will not post messages")
    print(f"[chain-watcher] Watching... (Ctrl+C to stop)\n")

    while running:
        try:
            # -- Check for re-nudge timeout --------------------------------
            if waiting_for_agent and last_nudge_time:
                elapsed = time.time() - last_nudge_time
                if elapsed >= STAGE_TIMEOUT:
                    if renudge_count < MAX_RENUDGE:
                        renudge_count += 1
                        ts_human = datetime.now(timezone.utc).strftime("%H:%M:%S")
                        print(f"[chain-watcher] [{ts_human}] TIMEOUT waiting for {waiting_for_agent} "
                              f"({int(elapsed)}s elapsed, re-nudge {renudge_count}/{MAX_RENUDGE})")

                        if not dry_run:
                            status = format_status(
                                f"Waiting for {waiting_for_agent}... "
                                f"re-nudging ({renudge_count}/{MAX_RENUDGE})"
                            )
                            post_message(token, channel_id, status, thread_ts=active_thread_ts)
                            time.sleep(1)

                            if last_nudge_text:
                                result_post = post_message(
                                    token, channel_id,
                                    format_nudge(last_nudge_text),
                                    thread_ts=active_thread_ts
                                )
                                if result_post:
                                    continues_posted += 1
                                    print(f"[chain-watcher]   -> Re-nudge posted (total: {continues_posted})")
                                else:
                                    print(f"[chain-watcher]   -> FAILED to post re-nudge")

                        last_nudge_time = time.time()

                    else:
                        # Stalled
                        ts_human = datetime.now(timezone.utc).strftime("%H:%M:%S")
                        print(f"[chain-watcher] [{ts_human}] STALL -- {waiting_for_agent} did not respond "
                              f"after {MAX_RENUDGE} re-nudges")

                        if not dry_run:
                            stall_msg = format_status(
                                f"Chain appears stalled waiting for {waiting_for_agent}. "
                                f"Manual intervention may be needed. "
                                f"Try: @HOOK continue -- route to {waiting_for_agent}"
                            )
                            post_message(token, channel_id, stall_msg, thread_ts=active_thread_ts)

                        waiting_for_agent = None
                        last_nudge_time = None
                        renudge_count = 0

            # -- Poll for new messages -------------------------------------
            result = fetch_messages(token, channel_id, last_ts)
            if not result:
                time.sleep(POLL_INTERVAL)
                continue

            messages = result.get("messages", [])
            if not messages:
                time.sleep(POLL_INTERVAL)
                continue

            messages.sort(key=lambda m: float(m.get("ts", "0")))

            for msg in messages:
                msg_ts = msg.get("ts", "0")
                text = msg.get("text", "")

                if float(msg_ts) > float(last_ts):
                    last_ts = msg_ts

                if is_our_message(msg):
                    continue

                # -- Announce detection ------------------------------------
                if is_announce_message(msg):
                    agent_name = extract_agent_from_announce(text)
                    announces_seen += 1
                    ts_human = datetime.fromtimestamp(
                        float(msg_ts), tz=timezone.utc
                    ).strftime("%H:%M:%S")

                    print(f"[chain-watcher] [{ts_human}] ANNOUNCE: {agent_name or 'unknown'} finished")
                    print(f"[chain-watcher]   -> Announces seen: {announces_seen}")

                    # Clear pending re-nudge state
                    if waiting_for_agent:
                        if agent_name == waiting_for_agent:
                            print(f"[chain-watcher]   -> Cleared pending wait for {waiting_for_agent}")
                        else:
                            print(f"[chain-watcher]   -> Expected {waiting_for_agent}, got {agent_name}")
                        waiting_for_agent = None
                        renudge_count = 0

                    # Determine next step
                    next_agent, nudge_text = get_nudge_for_agent(agent_name)

                    if next_agent is None:
                        # --- Chain complete --------------------------------
                        chains_completed += 1
                        print(f"[chain-watcher]   -> CHAIN COMPLETE (total: {chains_completed})")
                        if not dry_run:
                            done_msg = format_status(
                                f"Chain complete. All agents finished. "
                                f"({' -> '.join(CHAIN_SEQUENCE)})"
                            )
                            thread_ts = msg.get("thread_ts", msg_ts)
                            post_message(token, channel_id, done_msg, thread_ts=thread_ts)
                        waiting_for_agent = None
                        last_nudge_time = None
                        active_thread_ts = None
                        last_nudge_text = None

                    elif nudge_text:
                        # --- Post stage-specific nudge --------------------
                        time.sleep(POST_CONTINUE_DELAY)
                        thread_ts = msg.get("thread_ts", msg_ts)
                        active_thread_ts = thread_ts

                        print(f"[chain-watcher]   -> Nudging: route to {next_agent}")

                        if dry_run:
                            print(f"[chain-watcher]   -> DRY RUN: Would post nudge for {next_agent}")
                        else:
                            status = format_status(f"Routing to {next_agent}...")
                            post_message(token, channel_id, status, thread_ts=thread_ts)
                            time.sleep(1)

                            full_nudge = format_nudge(nudge_text)
                            result_post = post_message(
                                token, channel_id, full_nudge, thread_ts=thread_ts
                            )
                            if result_post:
                                continues_posted += 1
                                print(f"[chain-watcher]   -> Continue posted (total: {continues_posted})")
                            else:
                                print(f"[chain-watcher]   -> FAILED to post continue")

                        # Start timeout for next announce
                        waiting_for_agent = next_agent
                        last_nudge_time = time.time()
                        last_nudge_text = nudge_text
                        renudge_count = 0

            # Save state
            save_state({
                "last_ts": last_ts,
                "announces_seen": announces_seen,
                "continues_posted": continues_posted,
                "chains_completed": chains_completed,
                "waiting_for": waiting_for_agent,
                "updated": datetime.now(timezone.utc).isoformat(),
            })

        except Exception as e:
            print(f"[chain-watcher] Error in main loop: {e}")
            import traceback
            traceback.print_exc()

        time.sleep(POLL_INTERVAL)

    # Clean shutdown
    save_state({
        "last_ts": last_ts,
        "announces_seen": announces_seen,
        "continues_posted": continues_posted,
        "chains_completed": chains_completed,
        "updated": datetime.now(timezone.utc).isoformat(),
    })
    print(f"\n[chain-watcher] Stopped. {announces_seen} announces, "
          f"{continues_posted} continues, {chains_completed} chains completed.")


# --- Entry Point -----------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="HOOK Chain Watcher v2 -- stage-specific nudges with timeout and re-nudge"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Clear state file and exit (use before fresh test runs)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Watch and detect announces but don't post messages"
    )
    parser.add_argument(
        "--channel", type=str, default=None,
        help=f"Override channel ID (default: env or {DEFAULT_CHANNEL_ID})"
    )
    args = parser.parse_args()

    if args.reset:
        reset_state()
        sys.exit(0)

    token = get_slack_token()
    if not token:
        print("[chain-watcher] ERROR: No Slack bot token found.")
        print("  Set SLACK_BOT_TOKEN env var or configure in ~/.openclaw/openclaw.json")
        sys.exit(1)

    channel_id = args.channel or get_channel_id()

    # Validate token
    auth = slack_api("auth.test", token)
    if not auth:
        print("[chain-watcher] ERROR: Slack auth failed. Check your bot token.")
        sys.exit(1)

    bot_name = auth.get("user", "unknown")
    team = auth.get("team", "unknown")
    print(f"[chain-watcher] Authenticated as @{bot_name} in {team}")

    watch(token, channel_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
