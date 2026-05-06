"""
web/api/agent_runner.py -- Direct OpenAI agent runner for Shadowbox.

Replaces the OpenClaw gateway bridge. Each agent's SOUL.md + TOOLS.md
become the system prompt, and tool calls (exec) are handled directly
by this process. No external gateway needed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from openai import OpenAI

from web.api.sse import sse_event, extract_highlights

logger = logging.getLogger(__name__)

AGENT_TIMEOUT = 300  # seconds
HOOK_DIR = os.environ.get("HOOK_DIR", str(Path(__file__).resolve().parents[2]))

# Agent definitions
AGENTS = {
    "coordinator": {"model": "gpt-4.1", "callsign": "Marshall"},
    "triage-analyst": {"model": "gpt-4.1", "callsign": "Tara"},
    "osint-researcher": {"model": "gpt-4.1", "callsign": "Hunter"},
    "incident-responder": {"model": "gpt-4.1", "callsign": "Ward"},
    "threat-intel": {"model": "gpt-5", "callsign": "Driver"},
    "report-writer": {"model": "gpt-5", "callsign": "Page"},
    "log-querier": {"model": "gpt-4.1", "callsign": "Wells"},
}

SPECIALIST_AGENTS = {
    "triage-analyst", "osint-researcher", "incident-responder",
    "threat-intel", "report-writer", "log-querier",
}

CALLSIGNS = {aid: info["callsign"] for aid, info in AGENTS.items()}

# Fast-route patterns (skip Marshall for simple queries)
FAST_ROUTE_PATTERNS = [
    (r"^enrich\s+(ip\s+)?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", "osint-researcher"),
    (r"^enrich\s+(domain\s+)?([a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", "osint-researcher"),
    (r"^enrich\s+(hash\s+)?([a-fA-F0-9]{32,64})", "osint-researcher"),
    (r"^triage\s+", "triage-analyst"),
]

# Commands blocked from execution
BLOCKED_PATTERNS = [
    r"^\s*sudo\b", r"^\s*rm\s+-rf", r"^\s*kill\b", r"^\s*shutdown\b",
    r"^\s*reboot\b", r"^\s*launchctl\b", r"^\s*npm\s+", r"^\s*pip\s+",
    r"^\s*brew\s+", r"restart\.sh",
]

# OpenAI tool definition for exec
EXEC_TOOL = {
    "type": "function",
    "function": {
        "name": "exec",
        "description": "Execute a shell command on the host. Use this for enrichment scripts, investigation management, and RAG queries. Available commands: /app/scripts/enrich-ip.sh, /app/scripts/enrich-domain.sh, /app/scripts/enrich-hash.sh, /app/scripts/investigation.sh, /app/scripts/rag-inject.py",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
            },
            "required": ["command"],
        },
    },
}


def _load_env_file() -> dict[str, str]:
    """Load API keys from .env file."""
    env_extra = {}
    env_file = os.path.join(HOOK_DIR, ".env")
    if os.path.isfile(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key, val = key.strip(), val.strip()
                    if val and not os.environ.get(key):
                        env_extra[key] = val
    return env_extra


_ENV_EXTRA = _load_env_file()


def _get_api_key() -> str:
    """Get OpenAI API key."""
    return os.environ.get("OPENAI_API_KEY", _ENV_EXTRA.get("OPENAI_API_KEY", ""))


def _load_agent_prompt(agent_id: str) -> str:
    """Load SOUL.md + TOOLS.md as the system prompt for an agent."""
    workspace = os.path.join(HOOK_DIR, "workspaces", agent_id)
    parts = []

    soul_file = os.path.join(workspace, "SOUL.md")
    if os.path.isfile(soul_file):
        parts.append(Path(soul_file).read_text(encoding="utf-8"))

    tools_file = os.path.join(workspace, "TOOLS.md")
    if os.path.isfile(tools_file):
        parts.append(Path(tools_file).read_text(encoding="utf-8"))

    if not parts:
        return f"You are the {agent_id} agent for the Shadowbox SOC platform."

    return "\n\n---\n\n".join(parts)


def _is_blocked_command(cmd: str) -> bool:
    """Check if a command should be blocked."""
    lower = cmd.strip().lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, lower):
            return True
    return False


def _is_safe_exec(cmd: str) -> bool:
    """Check if an exec command is allowed."""
    if _is_blocked_command(cmd):
        return False
    # Allow enrichment scripts, investigation.sh, rag-inject.py, query-logs.py
    safe_prefixes = [
        f"{HOOK_DIR}/scripts/enrich-",
        f"{HOOK_DIR}/scripts/investigation.sh",
        f"{HOOK_DIR}/scripts/rag-inject.py",
        f"{HOOK_DIR}/scripts/query-logs.py",
        "/Users/bww/projects/hook/scripts/enrich-",
        "/Users/bww/projects/hook/scripts/investigation.sh",
        "/Users/bww/projects/hook/scripts/rag-inject.py",
        "/app/scripts/enrich-",
        "/app/scripts/investigation.sh",
        "/app/scripts/rag-inject.py",
    ]
    cmd_stripped = cmd.strip()
    for prefix in safe_prefixes:
        if cmd_stripped.startswith(prefix):
            return True
    # Also allow dig, whois, nmap for manual lookups
    if cmd_stripped.startswith(("dig ", "whois ", "nmap ")):
        return True
    return False


def _execute_command(cmd: str) -> str:
    """Execute a shell command and return output."""
    if not _is_safe_exec(cmd):
        return f"BLOCKED: Command not allowed for security reasons: {cmd[:100]}"

    try:
        env = {**os.environ, **_ENV_EXTRA, "HOOK_DIR": HOOK_DIR}
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=120, env=env,
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR: {result.stderr}"
        if result.returncode != 0:
            output += f"\nExit code: {result.returncode}"
        return output[:10000]  # Cap output to prevent token explosion
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out after 120 seconds"
    except Exception as exc:
        return f"ERROR: {exc}"


def _fast_route(message: str) -> Optional[str]:
    """Check if a message can be fast-routed directly to a specialist."""
    lower = message.strip().lower()
    for pattern, agent in FAST_ROUTE_PATTERNS:
        if re.match(pattern, lower):
            return agent
    return None


def _detect_chain(text: str) -> list[str]:
    """Detect which specialists the coordinator plans to chain."""
    lower = text.lower()
    found = []
    seen = set()
    for agent in SPECIALIST_AGENTS:
        if agent in lower and agent not in seen:
            found.append(agent)
            seen.add(agent)
    return found


async def _query_rag(query: str, category: str, k: int = 3) -> str:
    """Query RAG for context (non-blocking)."""
    try:
        env = {**os.environ, **_ENV_EXTRA, "HOOK_DIR": HOOK_DIR}
        proc = await asyncio.create_subprocess_exec(
            "python3", f"{HOOK_DIR}/scripts/rag-inject.py", "query", query,
            "--category", category, "--k", str(k),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        output = stdout.decode().strip()
        if output and "No relevant context found" not in output:
            return output
    except Exception as exc:
        logger.debug("RAG query failed: %s", exc)
    return ""


async def _get_rag_context(message: str) -> str:
    """Extract IOCs and check RAG for feed matches and past verdicts."""
    ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', message)
    domains = re.findall(r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b', message)
    iocs = list(set(ips + domains))

    if not iocs:
        return ""

    tasks = []
    for ioc in iocs:
        tasks.append(_query_rag(ioc, "feed_ioc", k=2))
        tasks.append(_query_rag(ioc, "ioc_verdict", k=2))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    contexts = [r for r in results if isinstance(r, str) and r]

    if contexts:
        return "RAG CONTEXT (from behavioral memory and threat feeds):\n" + "\n".join(contexts) + "\n---\n"
    return ""


class AgentRunner:
    """Runs agents directly via OpenAI API. No OpenClaw dependency."""

    def __init__(self) -> None:
        api_key = _get_api_key()
        if not api_key:
            logger.warning("OPENAI_API_KEY not set — agents will not work")
        self._client = OpenAI(api_key=api_key) if api_key else None
        # Cache loaded prompts
        self._prompt_cache: dict[str, str] = {}

    async def close(self) -> None:
        pass

    async def health_check(self) -> dict[str, Any]:
        """Check if OpenAI is reachable."""
        if not self._client:
            return {"status": "unreachable", "error": "No API key"}
        try:
            # Quick model list check
            models = self._client.models.list()
            return {"status": "ok", "provider": "openai"}
        except Exception as exc:
            return {"status": "unreachable", "error": str(exc)}

    async def get_agents(self) -> list[dict[str, Any]]:
        return []

    def _get_prompt(self, agent_id: str) -> str:
        """Get or cache the system prompt for an agent."""
        if agent_id not in self._prompt_cache:
            self._prompt_cache[agent_id] = _load_agent_prompt(agent_id)
        return self._prompt_cache[agent_id]

    async def send_message(
        self,
        message: str,
        session_key: Optional[str] = None,
        agent_id: str = "coordinator",
    ) -> AsyncGenerator[str, None]:
        """Send a message to an agent and yield SSE events."""
        session_id = session_key or str(uuid.uuid4())[:12]

        # SECURITY: Block system commands
        if _is_blocked_command(message):
            yield sse_event("meta", {"session_key": session_id, "agent_id": agent_id})
            yield sse_event("agent_result", {
                "agent": "coordinator",
                "content": "That looks like a system command. Shadowbox agents analyze security data — they do not execute system commands.",
                "highlights": {},
                "meta": {},
            })
            yield sse_event("done", {"session_key": session_id})
            return

        yield sse_event("meta", {
            "session_key": session_id,
            "agent_id": agent_id,
        })

        # Check for fast-route
        fast = _fast_route(message) if agent_id == "coordinator" else None

        if fast:
            callsign = CALLSIGNS.get(fast, fast)
            yield sse_event("coordinator", {
                "agent": "coordinator",
                "content": f"Direct enrichment request — routing straight to {callsign}.",
            })

            rag_context = await _get_rag_context(message)

            yield sse_event("agent_start", {
                "agent": fast,
                "content": f"{callsign} is working...",
            })

            specialist_message = f"""{rag_context}Operator request: {message}

IMPORTANT: You MUST use your enrichment scripts to perform this task. Do NOT answer from memory."""

            result = await self._run_agent(fast, specialist_message)

            if result:
                yield sse_event("agent_result", {
                    "agent": fast,
                    "content": result["text"],
                    "highlights": extract_highlights(result["text"]),
                    "meta": result["meta"],
                })
            else:
                yield sse_event("error", {"message": f"{callsign} did not return results"})

            yield sse_event("done", {"session_key": session_id})
            return

        # Run coordinator
        yield sse_event("agent_start", {
            "agent": agent_id,
            "content": "Processing request...",
        })

        result = await self._run_agent(agent_id, message)

        if result is None:
            yield sse_event("error", {"message": "Failed to get response from agent"})
            yield sse_event("done", {"session_key": session_id})
            return

        response_text = result["text"]

        # Not coordinator — direct response
        if agent_id != "coordinator":
            yield sse_event("agent_result", {
                "agent": agent_id,
                "content": response_text,
                "highlights": extract_highlights(response_text),
                "meta": result["meta"],
            })
            yield sse_event("done", {"session_key": session_id})
            return

        # Coordinator — detect chain
        chain = _detect_chain(response_text)

        if not chain:
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

        # Run each specialist in chain
        accumulated = f"Original request: {message}\n\nMarshall's routing plan:\n{response_text}\n"

        for specialist in chain:
            yield sse_event("agent_start", {
                "agent": specialist,
                "content": f"Running {CALLSIGNS.get(specialist, specialist)}...",
            })

            rag_context = await _get_rag_context(accumulated)

            specialist_msg = f"""{rag_context}{accumulated}
You are the next agent in the chain. Complete your specific task based on the context above.
IMPORTANT: If your task involves enrichment, you MUST use your exec scripts. Do NOT answer from memory."""

            specialist_result = await self._run_agent(specialist, specialist_msg)

            if specialist_result:
                yield sse_event("agent_result", {
                    "agent": specialist,
                    "content": specialist_result["text"],
                    "highlights": extract_highlights(specialist_result["text"]),
                    "meta": specialist_result["meta"],
                })
                accumulated += f"\n\n--- {specialist} findings ---\n{specialist_result['text']}\n"
            else:
                yield sse_event("error", {
                    "message": f"{CALLSIGNS.get(specialist, specialist)} did not return results",
                })

        yield sse_event("done", {"session_key": session_id})

    async def _run_agent(
        self,
        agent_id: str,
        message: str,
    ) -> Optional[dict[str, Any]]:
        """Run an agent turn with tool use loop."""
        if not self._client:
            logger.error("No OpenAI client — API key not set")
            return None

        agent_info = AGENTS.get(agent_id, {"model": "gpt-4.1"})
        model = agent_info["model"]
        system_prompt = self._get_prompt(agent_id)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]

        # Tool use loop — agent may call exec multiple times
        total_tokens = 0
        start_time = asyncio.get_event_loop().time()
        max_tool_rounds = 10  # Prevent infinite loops

        try:
            for round_num in range(max_tool_rounds):
                response = await asyncio.to_thread(
                    self._client.chat.completions.create,
                    model=model,
                    messages=messages,
                    tools=[EXEC_TOOL],
                    tool_choice="auto",
                    timeout=AGENT_TIMEOUT,
                )

                choice = response.choices[0]
                usage = response.usage
                if usage:
                    total_tokens += usage.total_tokens

                # If the model wants to call a tool
                if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                    # Add the assistant message with tool calls
                    messages.append(choice.message)

                    # Execute each tool call
                    for tool_call in choice.message.tool_calls:
                        if tool_call.function.name == "exec":
                            try:
                                args = json.loads(tool_call.function.arguments)
                                cmd = args.get("command", "")
                                logger.info("Agent %s exec: %s", agent_id, cmd[:100])
                                output = _execute_command(cmd)
                            except json.JSONDecodeError:
                                output = "ERROR: Invalid tool call arguments"

                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": output,
                            })
                    continue  # Loop back for the model to process tool results

                # Model produced a final response
                duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
                response_text = choice.message.content or ""

                return {
                    "text": response_text,
                    "meta": {
                        "duration_ms": duration_ms,
                        "model": model,
                        "tokens": total_tokens,
                        "tokens_in": usage.prompt_tokens if usage else 0,
                        "tokens_out": usage.completion_tokens if usage else 0,
                    },
                }

            # Exhausted tool rounds
            logger.warning("Agent %s exhausted %d tool rounds", agent_id, max_tool_rounds)
            return {
                "text": "Agent reached maximum tool call limit. Partial results may be available.",
                "meta": {"duration_ms": 0, "model": model, "tokens": total_tokens},
            }

        except Exception as exc:
            logger.error("Agent %s failed: %s", agent_id, exc)
            return None
