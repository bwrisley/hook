"""
web/api/gateway_bridge.py -- Bridge between Shadowbox web API and OpenClaw gateway.

Uses the `openclaw agent` CLI to send messages to agents and capture responses.
When the coordinator delegates to a specialist via sessions_spawn, the bridge
detects this and runs a follow-up call to get the specialist's results.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from typing import Any, AsyncGenerator, Optional

from web.api.sse import sse_event, extract_highlights

logger = logging.getLogger(__name__)

AGENT_TIMEOUT = 180  # seconds

# Patterns that indicate the coordinator delegated to a specialist
SPAWN_PATTERNS = [
    r"routing to (\S+)",
    r"spawning (\S+)",
    r"sessions_spawn.*agentId.*?[\"'](\S+?)[\"']",
    r"delegat\w+ to (\S+)",
]

SPECIALIST_AGENTS = {
    "triage-analyst", "osint-researcher", "incident-responder",
    "threat-intel", "report-writer", "log-querier",
}


def _detect_delegation(text: str) -> Optional[str]:
    """Detect if the coordinator delegated to a specialist. Returns agent ID or None."""
    lower = text.lower()
    for pattern in SPAWN_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            candidate = match.group(1).strip(".,;:\"'")
            if candidate in SPECIALIST_AGENTS:
                return candidate
            # Partial match — check if any agent ID is in the text
            for agent in SPECIALIST_AGENTS:
                if agent in lower:
                    return agent
    return None


class GatewayBridge:
    """Bridge between Shadowbox's web API and the OpenClaw gateway.

    Uses `openclaw agent` CLI for message delivery and response capture.
    When the coordinator delegates, automatically follows up with the
    specialist agent to get the actual results.
    """

    def __init__(self) -> None:
        self._openclaw_bin = self._find_openclaw()

    def _find_openclaw(self) -> str:
        """Locate the openclaw binary."""
        for path in [
            "/opt/homebrew/bin/openclaw",
            "/usr/local/bin/openclaw",
            os.path.expanduser("~/.npm-global/bin/openclaw"),
        ]:
            if os.path.isfile(path):
                return path
        return "openclaw"

    async def close(self) -> None:
        pass

    async def health_check(self) -> dict[str, Any]:
        """Check if the OpenClaw gateway is reachable."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self._openclaw_bin, "gateway", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode()
            if "running" in output.lower() or proc.returncode == 0:
                return {"status": "ok", "gateway": "openclaw CLI"}
        except asyncio.TimeoutError:
            pass
        except FileNotFoundError:
            return {"status": "unreachable", "error": "openclaw binary not found"}
        except Exception as exc:
            logger.warning("Gateway health check failed: %s", exc)
        return {"status": "unreachable", "gateway": "openclaw CLI"}

    async def get_agents(self) -> list[dict[str, Any]]:
        return []

    async def send_message(
        self,
        message: str,
        session_key: Optional[str] = None,
        agent_id: str = "coordinator",
    ) -> AsyncGenerator[str, None]:
        """Send a message to an agent and yield SSE events.

        If the coordinator delegates to a specialist, automatically
        runs the specialist and returns its results.
        """
        session_id = session_key or str(uuid.uuid4())[:12]

        yield sse_event("meta", {
            "session_key": session_id,
            "agent_id": agent_id,
        })

        yield sse_event("agent_start", {
            "agent": agent_id,
            "content": "Processing request...",
        })

        # Run the agent
        result = await self._run_agent(agent_id, message, session_key)

        if result is None:
            yield sse_event("error", {"message": "Failed to get response from agent"})
            yield sse_event("done", {"session_key": session_id})
            return

        response_text = result["text"]
        meta = result["meta"]

        # Check if the coordinator delegated to a specialist
        delegated_to = _detect_delegation(response_text) if agent_id == "coordinator" else None

        if delegated_to:
            # Show the coordinator's routing message
            yield sse_event("coordinator", {
                "agent": "coordinator",
                "content": response_text,
            })

            # Now run the specialist directly
            yield sse_event("agent_start", {
                "agent": delegated_to,
                "content": f"Running {delegated_to}...",
            })

            # Build a context-enriched message for the specialist
            # Include the coordinator's routing context so the specialist has full findings
            specialist_message = f"""Context from coordinator (Marshall):
{response_text}

Original operator request: {message}

Complete the task described above. Use the context provided by the coordinator."""
            specialist_result = await self._run_agent(delegated_to, specialist_message)

            if specialist_result:
                yield sse_event("agent_result", {
                    "agent": delegated_to,
                    "content": specialist_result["text"],
                    "highlights": extract_highlights(specialist_result["text"]),
                    "meta": specialist_result["meta"],
                })
            else:
                yield sse_event("error", {
                    "message": f"Specialist {delegated_to} did not return results",
                })
        else:
            # Direct response (no delegation)
            yield sse_event("agent_result", {
                "agent": agent_id,
                "content": response_text,
                "highlights": extract_highlights(response_text),
                "meta": meta,
            })

        yield sse_event("done", {"session_key": session_id})

    async def _run_agent(
        self,
        agent_id: str,
        message: str,
        session_key: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Run an openclaw agent command and return parsed result.

        Returns dict with 'text' and 'meta' keys, or None on failure.
        """
        cmd = [
            self._openclaw_bin, "agent",
            "--agent", agent_id,
            "--message", message,
            "--timeout", str(AGENT_TIMEOUT),
            "--json",
        ]

        if session_key:
            cmd.extend(["--session-id", session_key])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={
                    **os.environ,
                    "NO_COLOR": "1",
                    "HOOK_DIR": os.environ.get("HOOK_DIR", "/Users/bww/projects/hook"),
                },
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=AGENT_TIMEOUT + 30,
            )

            if proc.returncode != 0:
                error_msg = stderr.decode().strip() or f"Agent exited with code {proc.returncode}"
                logger.error("openclaw agent %s failed: %s", agent_id, error_msg)
                return None

            output = stdout.decode().strip()
            if not output:
                return None

            result = json.loads(output)
            response_text = ""

            payloads = result.get("result", {}).get("payloads", [])
            for payload in payloads:
                text = payload.get("text", "")
                if text:
                    response_text += text + "\n"

            response_text = response_text.strip()

            agent_meta = result.get("result", {}).get("meta", {}).get("agentMeta", {})
            duration_ms = result.get("result", {}).get("meta", {}).get("durationMs", 0)

            return {
                "text": response_text,
                "meta": {
                    "duration_ms": duration_ms,
                    "model": agent_meta.get("model", ""),
                    "tokens": agent_meta.get("usage", {}).get("total", 0),
                },
            }

        except asyncio.TimeoutError:
            logger.error("Agent %s timed out after %ds", agent_id, AGENT_TIMEOUT)
            return None
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse %s response: %s", agent_id, exc)
            return None
        except FileNotFoundError:
            logger.error("openclaw binary not found")
            return None
        except Exception as exc:
            logger.error("Bridge error for %s: %s", agent_id, exc)
            return None
