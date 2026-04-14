"""
web/api/gateway_bridge.py -- Bridge between Shadowbox web API and OpenClaw gateway.

Uses the `openclaw agent` CLI to send messages to agents and capture responses.
When the coordinator delegates to specialists, the bridge detects the chain
plan and runs each specialist sequentially, passing accumulated context.
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

def _load_env_file() -> dict[str, str]:
    """Load API keys from .env file if not already in environment."""
    env_extra = {}
    hook_dir = os.environ.get("HOOK_DIR", "/Users/bww/projects/hook")
    env_file = os.path.join(hook_dir, ".env")
    if os.path.isfile(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if val and not os.environ.get(key):
                        env_extra[key] = val
    return env_extra

_ENV_EXTRA = _load_env_file()

SPECIALIST_AGENTS = {
    "triage-analyst", "osint-researcher", "incident-responder",
    "threat-intel", "report-writer", "log-querier",
}

# Callsign mapping for user-facing messages
CALLSIGNS = {
    "coordinator": "Marshall", "triage-analyst": "Tara",
    "osint-researcher": "Hunter", "incident-responder": "Ward",
    "threat-intel": "Driver", "report-writer": "Page", "log-querier": "Wells",
}

# Patterns for fast-routing (bypass Marshall)
FAST_ROUTE_PATTERNS = [
    (r"^enrich\s+(ip\s+)?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", "osint-researcher", "enrichment"),
    (r"^enrich\s+(domain\s+)?([a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", "osint-researcher", "enrichment"),
    (r"^enrich\s+(hash\s+)?([a-fA-F0-9]{32,64})", "osint-researcher", "enrichment"),
    (r"^triage\s+", "triage-analyst", "triage"),
    (r"^(what agents|list agents|show agents)", "coordinator", None),
]


def _fast_route(message: str) -> tuple[str, str] | None:
    """Check if a message can be fast-routed directly to a specialist.

    Returns (agent_id, route_type) or None if Marshall should route.
    """
    lower = message.strip().lower()
    for pattern, agent, route_type in FAST_ROUTE_PATTERNS:
        if re.match(pattern, lower):
            return (agent, route_type)
    return None

# Map common references to agent IDs
AGENT_ALIASES = {
    "triage": "triage-analyst",
    "triage-analyst": "triage-analyst",
    "osint": "osint-researcher",
    "osint-researcher": "osint-researcher",
    "incident": "incident-responder",
    "incident-responder": "incident-responder",
    "threat-intel": "threat-intel",
    "threat": "threat-intel",
    "report": "report-writer",
    "report-writer": "report-writer",
    "log-querier": "log-querier",
    "log": "log-querier",
}


def _detect_chain(text: str) -> list[str]:
    """Detect which specialists the coordinator plans to chain.

    Returns an ordered list of agent IDs found in the coordinator's response.
    """
    lower = text.lower()
    found = []
    seen = set()

    # Look for agent IDs mentioned in routing context
    for agent in SPECIALIST_AGENTS:
        if agent in lower and agent not in seen:
            found.append(agent)
            seen.add(agent)

    return found


def _detect_single_delegation(text: str) -> Optional[str]:
    """Detect if coordinator delegated to exactly one specialist."""
    chain = _detect_chain(text)
    patterns = [
        r"routing to (\S+)",
        r"spawning (\S+)",
        r"delegat\w+ to (\S+)",
        r"route.*?to (\S+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            candidate = match.group(1).strip(".,;:\"'")
            resolved = AGENT_ALIASES.get(candidate)
            if resolved:
                return resolved
    # If only one specialist mentioned, that's the delegation
    if len(chain) == 1:
        return chain[0]
    return None


# Commands and patterns that must NEVER be executed by agents
BLOCKED_PATTERNS = [
    r"^\s*\./scripts/",
    r"^\s*/Users/",
    r"^\s*/bin/",
    r"^\s*/usr/",
    r"^\s*/opt/",
    r"^\s*sudo\b",
    r"^\s*rm\s",
    r"^\s*kill\b",
    r"^\s*shutdown\b",
    r"^\s*reboot\b",
    r"^\s*launchctl\b",
    r"^\s*exec\s*:",
    r"^\s*curl\s",
    r"^\s*wget\s",
    r"^\s*python3?\s+-c",
    r"^\s*bash\s+-c",
    r"^\s*sh\s+-c",
    r"restart\.sh",
    r"openclaw\s+gateway",
    r"npm\s+",
    r"pip\s+",
    r"brew\s+",
]


def _is_blocked_command(message: str) -> bool:
    """Check if a message looks like a system command that should not be executed."""
    lower = message.strip().lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, lower):
            return True
    return False


class GatewayBridge:
    """Bridge between Shadowbox's web API and the OpenClaw gateway.

    Uses `openclaw agent` CLI for message delivery. Detects multi-agent
    chains and runs each specialist sequentially with accumulated context.
    Blocks system commands from being executed by agents.
    """

    def __init__(self) -> None:
        self._openclaw_bin = self._find_openclaw()

    def _find_openclaw(self) -> str:
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
        try:
            proc = await asyncio.create_subprocess_exec(
                self._openclaw_bin, "gateway", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            if "running" in stdout.decode().lower() or proc.returncode == 0:
                return {"status": "ok", "gateway": "openclaw CLI"}
        except (asyncio.TimeoutError, FileNotFoundError, Exception):
            pass
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

        Fast-routes simple queries directly to specialists.
        Detects multi-agent chains and runs each specialist sequentially.
        """
        session_id = session_key or str(uuid.uuid4())[:12]

        # SECURITY: Block system commands from reaching agents
        if _is_blocked_command(message):
            yield sse_event("meta", {"session_key": session_id, "agent_id": agent_id})
            yield sse_event("agent_result", {
                "agent": "coordinator",
                "content": "That looks like a system command. Shadowbox agents analyze security data — they do not execute system commands. If you need to run a script, use the server terminal directly.",
                "highlights": {},
                "meta": {},
            })
            yield sse_event("done", {"session_key": session_id})
            return

        yield sse_event("meta", {
            "session_key": session_id,
            "agent_id": agent_id,
        })

        # Check for fast-route (bypass Marshall for simple queries)
        fast = _fast_route(message) if agent_id == "coordinator" else None

        if fast and fast[1]:  # fast[1] is route_type, None means let Marshall handle
            target_agent, route_type = fast
            callsign = CALLSIGNS.get(target_agent, target_agent)

            yield sse_event("coordinator", {
                "agent": "coordinator",
                "content": f"Direct {route_type} request detected — routing straight to {callsign}, skipping the full coordinator turn.",
            })

            # Inject RAG context
            rag_context = await self._get_rag_context(message)

            yield sse_event("agent_start", {
                "agent": target_agent,
                "content": f"{callsign} is working...",
            })

            specialist_message = f"""{rag_context}Operator request: {message}

IMPORTANT: You MUST use your enrichment scripts to perform this task. Do NOT answer from memory or training data. Run the appropriate exec command from your TOOLS.md to get live, current data."""
            result = await self._run_agent(target_agent, specialist_message)

            if result:
                yield sse_event("agent_result", {
                    "agent": target_agent,
                    "content": result["text"],
                    "highlights": extract_highlights(result["text"]),
                    "meta": result["meta"],
                })
            else:
                yield sse_event("error", {"message": f"{callsign} did not return results"})

            yield sse_event("done", {"session_key": session_id})
            return

        yield sse_event("agent_start", {
            "agent": agent_id,
            "content": "Processing request...",
        })

        # Run the coordinator (or direct agent)
        result = await self._run_agent(agent_id, message, session_key)

        if result is None:
            yield sse_event("error", {"message": "Failed to get response from agent"})
            yield sse_event("done", {"session_key": session_id})
            return

        response_text = result["text"]

        # If not coordinator, just return the result directly
        if agent_id != "coordinator":
            yield sse_event("agent_result", {
                "agent": agent_id,
                "content": response_text,
                "highlights": extract_highlights(response_text),
                "meta": result["meta"],
            })
            yield sse_event("done", {"session_key": session_id})
            return

        # Coordinator response — detect chain
        chain = _detect_chain(response_text)

        if not chain:
            # No delegation — coordinator handled it directly
            yield sse_event("agent_result", {
                "agent": "coordinator",
                "content": response_text,
                "highlights": extract_highlights(response_text),
                "meta": result["meta"],
            })
            yield sse_event("done", {"session_key": session_id})
            return

        # Show Marshall's routing plan
        yield sse_event("coordinator", {
            "agent": "coordinator",
            "content": response_text,
        })

        # Run each specialist in the chain sequentially
        accumulated_findings = f"Original request: {message}\n\nMarshall's routing plan:\n{response_text}\n"

        for specialist in chain:
            yield sse_event("agent_start", {
                "agent": specialist,
                "content": f"Running {specialist}...",
            })

            # Inject RAG context (feed matches, past verdicts) if available
            rag_context = await self._get_rag_context(accumulated_findings)

            specialist_message = f"""{rag_context}{accumulated_findings}
You are the next agent in the chain. Complete your specific task based on the context above.
Focus on your expertise. Use the findings from prior agents in the chain.
If RAG CONTEXT is provided above, incorporate it into your analysis — especially any threat feed matches.
IMPORTANT: If your task involves enrichment, you MUST use your enrichment scripts (exec commands from TOOLS.md) to get live data. Do NOT answer from memory."""

            specialist_result = await self._run_agent(specialist, specialist_message)

            if specialist_result:
                yield sse_event("agent_result", {
                    "agent": specialist,
                    "content": specialist_result["text"],
                    "highlights": extract_highlights(specialist_result["text"]),
                    "meta": specialist_result["meta"],
                })
                # Accumulate findings for next agent in chain
                accumulated_findings += f"\n\n--- {specialist} findings ---\n{specialist_result['text']}\n"
            else:
                yield sse_event("error", {
                    "message": f"{specialist} did not return results",
                })

        yield sse_event("done", {"session_key": session_id})

    async def _query_rag(self, query: str, category: str, k: int = 3) -> str:
        """Query RAG for context (non-blocking)."""
        try:
            hook_dir = os.environ.get("HOOK_DIR", "/Users/bww/projects/hook")
            proc = await asyncio.create_subprocess_exec(
                "python3", f"{hook_dir}/scripts/rag-inject.py", "query", query, "--category", category, "--k", str(k),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **_ENV_EXTRA, "HOOK_DIR": hook_dir},
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            output = stdout.decode().strip()
            if output and "No relevant context found" not in output:
                return output
        except Exception as exc:
            logger.debug("RAG query failed: %s", exc)
        return ""

    async def _get_rag_context(self, message: str) -> str:
        """Extract IOCs and check RAG for feed matches and past verdicts (parallel)."""
        import re as _re
        ips = _re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', message)
        domains = _re.findall(r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b', message)
        iocs = list(set(ips + domains))

        if not iocs:
            return ""

        # Run all RAG queries in parallel
        tasks = []
        for ioc in iocs:
            tasks.append(self._query_rag(ioc, "feed_ioc", k=2))
            tasks.append(self._query_rag(ioc, "ioc_verdict", k=2))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        contexts = [r for r in results if isinstance(r, str) and r]

        if contexts:
            return "RAG CONTEXT (from behavioral memory and threat feeds):\n" + "\n".join(contexts) + "\n---\n"
        return ""

    async def _run_agent(
        self,
        agent_id: str,
        message: str,
        session_key: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Run an openclaw agent command and return parsed result."""
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
                    **_ENV_EXTRA,
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

            usage = agent_meta.get("usage", {})
            return {
                "text": response_text,
                "meta": {
                    "duration_ms": duration_ms,
                    "model": agent_meta.get("model", ""),
                    "tokens": usage.get("total", 0),
                    "tokens_in": usage.get("input", 0),
                    "tokens_out": usage.get("output", 0),
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
