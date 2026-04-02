"""
web/api/sse.py -- Server-Sent Events formatting utilities for HOOK.

Event types:
  - meta:          Conversation/session metadata
  - agent_start:   Coordinator spawned a specialist agent
  - agent_result:  Specialist agent announced results
  - coordinator:   Coordinator's own message/summary
  - investigation: Investigation state update
  - error:         Error message
  - done:          Stream complete
"""
from __future__ import annotations

import json
import re
from typing import Any


def sse_event(event_type: str, payload: dict[str, Any]) -> str:
    """Format a single SSE event string."""
    return f"event: {event_type}\ndata: {json.dumps(payload, default=str)}\n\n"


def extract_highlights(text: str) -> dict[str, list[dict[str, Any]]]:
    """Extract IPs, ports, and timestamps from response text for UI highlighting."""
    highlights: dict[str, list[dict[str, Any]]] = {
        "ips": [],
        "ports": [],
        "timestamps": [],
    }

    ip_pattern = r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
    for match in re.finditer(ip_pattern, text):
        highlights["ips"].append({
            "value": match.group(0),
            "start": match.start(),
            "end": match.end(),
        })

    timestamp_pattern = r'\b\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b'
    for match in re.finditer(timestamp_pattern, text):
        highlights["timestamps"].append({
            "value": match.group(0),
            "start": match.start(),
            "end": match.end(),
        })

    port_pattern = r'\bports?\s+([0-9]{1,5})'
    for match in re.finditer(port_pattern, text):
        port_num = match.group(1)
        port_start = match.start() + match.group(0).rfind(port_num)
        highlights["ports"].append({
            "value": port_num,
            "start": port_start,
            "end": port_start + len(port_num),
        })

    return highlights


def extract_agent_attribution(message_text: str) -> dict[str, Any]:
    """Parse an OpenClaw message to identify which agent produced it.

    Detects patterns like:
      - "Subagent triage-analyst finished"
      - "Spawning agent osint-researcher"
      - Agent ID in metadata
    """
    agents = [
        "coordinator", "triage-analyst", "osint-researcher",
        "incident-responder", "threat-intel", "report-writer",
        "log-querier",
    ]

    text_lower = message_text.lower()

    # Check for subagent completion announce
    for agent in agents:
        if f"subagent {agent} finished" in text_lower:
            return {"agent": agent, "event": "completed"}
        if f"spawning agent {agent}" in text_lower or f"sessions_spawn" in text_lower and agent in text_lower:
            return {"agent": agent, "event": "started"}

    # Check for agent name anywhere in the message
    for agent in agents:
        if agent in text_lower:
            return {"agent": agent, "event": "message"}

    return {"agent": "coordinator", "event": "message"}
