"""
web/api/gateway_bridge.py -- Bridge between HOOK web API and OpenClaw gateway.

Translates HTTP requests into OpenClaw gateway REST API calls.
The gateway runs on port 18789 with controlUi enabled.

This is a thin proxy -- the coordinator agent still handles all routing
via sessions_spawn. The bridge just provides a web-friendly interface.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncGenerator, Optional

import httpx

from web.api.sse import sse_event, extract_agent_attribution, extract_highlights

logger = logging.getLogger(__name__)

DEFAULT_GATEWAY_URL = "http://localhost:18789"
POLL_INTERVAL = 2.0  # seconds between session history polls
CHAIN_TIMEOUT = 600  # max seconds to wait for a chain to complete


class GatewayBridge:
    """Bridge between HOOK's web API and the OpenClaw gateway REST API.

    Manages sessions, sends messages, and streams chain progress as SSE events.
    """

    def __init__(self, gateway_url: Optional[str] = None) -> None:
        self.gateway_url = gateway_url or os.environ.get(
            "HOOK_GATEWAY_URL", DEFAULT_GATEWAY_URL
        )
        self._client = httpx.AsyncClient(
            base_url=self.gateway_url,
            timeout=httpx.Timeout(30.0, read=CHAIN_TIMEOUT),
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def health_check(self) -> dict[str, Any]:
        """Check if the OpenClaw gateway is reachable."""
        try:
            resp = await self._client.get("/api/health")
            if resp.status_code == 200:
                return {"status": "ok", "gateway": self.gateway_url}
        except httpx.ConnectError:
            pass
        except Exception as exc:
            logger.warning("Gateway health check failed: %s", exc)
        return {"status": "unreachable", "gateway": self.gateway_url}

    async def list_sessions(self) -> list[dict[str, Any]]:
        """List active sessions from the gateway."""
        try:
            resp = await self._client.get("/api/sessions")
            if resp.status_code == 200:
                return resp.json().get("sessions", [])
        except Exception as exc:
            logger.error("Failed to list sessions: %s", exc)
        return []

    async def get_agents(self) -> list[dict[str, Any]]:
        """Get agent information from the gateway."""
        try:
            resp = await self._client.get("/api/agents")
            if resp.status_code == 200:
                return resp.json().get("agents", [])
        except Exception as exc:
            logger.warning("Failed to get agents from gateway: %s", exc)
        return []

    async def send_message(
        self,
        message: str,
        session_key: Optional[str] = None,
        agent_id: str = "coordinator",
    ) -> AsyncGenerator[str, None]:
        """Send a message to the coordinator and yield SSE events as the chain progresses.

        If no session_key is provided, creates a new session.
        Polls session history to detect agent handoffs and results.

        Yields SSE-formatted event strings.
        """
        # 1. Create or reuse session
        if session_key is None:
            session_key = await self._create_session(agent_id)
            if not session_key:
                yield sse_event("error", {"message": "Failed to create gateway session"})
                yield sse_event("done", {})
                return

        yield sse_event("meta", {
            "session_key": session_key,
            "agent_id": agent_id,
        })

        # 2. Get current history length (baseline)
        baseline_history = await self._get_session_history(session_key)
        baseline_count = len(baseline_history)

        # 3. Send the message
        sent = await self._post_message(session_key, message)
        if not sent:
            yield sse_event("error", {"message": "Failed to send message to gateway"})
            yield sse_event("done", {})
            return

        # 4. Poll for new messages (chain progress)
        seen_count = baseline_count
        idle_polls = 0
        max_idle = int(CHAIN_TIMEOUT / POLL_INTERVAL)

        while idle_polls < max_idle:
            await asyncio.sleep(POLL_INTERVAL)

            history = await self._get_session_history(session_key)
            current_count = len(history)

            if current_count > seen_count:
                # New messages arrived
                idle_polls = 0
                for msg in history[seen_count:]:
                    event = self._message_to_sse(msg)
                    yield event
                seen_count = current_count

                # Check if chain is complete (coordinator's final message after agents)
                last_msg = history[-1]
                if self._is_chain_complete(last_msg, history):
                    break
            else:
                idle_polls += 1

        # 5. Emit final response with highlights
        if seen_count > baseline_count:
            last_msg = baseline_history[-1] if not history[baseline_count:] else history[-1]
            response_text = last_msg.get("content", "") if isinstance(last_msg, dict) else ""
            yield sse_event("response", {
                "session_key": session_key,
                "response": response_text,
                "highlights": extract_highlights(response_text),
            })

        yield sse_event("done", {"session_key": session_key})

    async def _create_session(self, agent_id: str) -> Optional[str]:
        """Create a new session via the gateway API."""
        try:
            resp = await self._client.post(
                "/api/sessions",
                json={"agentId": agent_id},
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                session_key = data.get("sessionKey") or data.get("session_key")
                logger.info("Created gateway session: %s", session_key)
                return session_key
        except Exception as exc:
            logger.error("Failed to create session: %s", exc)
        return None

    async def _post_message(self, session_key: str, message: str) -> bool:
        """Post a user message to an existing session."""
        try:
            resp = await self._client.post(
                f"/api/sessions/{session_key}/message",
                json={"content": message, "role": "user"},
            )
            return resp.status_code in (200, 201, 202)
        except Exception as exc:
            logger.error("Failed to post message to session %s: %s", session_key, exc)
            return False

    async def _get_session_history(self, session_key: str) -> list[dict]:
        """Fetch the full message history for a session."""
        try:
            resp = await self._client.get(f"/api/sessions/{session_key}/history")
            if resp.status_code == 200:
                return resp.json().get("messages", [])
        except Exception as exc:
            logger.warning("Failed to get session history: %s", exc)
        return []

    def _message_to_sse(self, msg: dict) -> str:
        """Convert a gateway message dict to an SSE event string."""
        content = msg.get("content", "")
        role = msg.get("role", "assistant")
        attribution = extract_agent_attribution(content)

        if attribution["event"] == "started":
            return sse_event("agent_start", {
                "agent": attribution["agent"],
                "content": content,
            })
        elif attribution["event"] == "completed":
            return sse_event("agent_result", {
                "agent": attribution["agent"],
                "content": content,
                "highlights": extract_highlights(content),
            })
        else:
            return sse_event("coordinator", {
                "agent": attribution["agent"],
                "role": role,
                "content": content,
            })

    def _is_chain_complete(self, last_msg: dict, history: list[dict]) -> bool:
        """Heuristic: detect if the coordinator has finished chaining agents.

        A chain is considered complete when:
        - The last message is from the assistant (coordinator)
        - It does not contain "sessions_spawn" or "Spawning agent" (no more handoffs)
        - At least one agent result has been seen
        """
        content = last_msg.get("content", "").lower()
        role = last_msg.get("role", "")

        if role != "assistant":
            return False

        if "sessions_spawn" in content or "spawning agent" in content:
            return False

        # Check if any agent results were seen in the conversation
        has_agent_results = any(
            "subagent" in msg.get("content", "").lower() and "finished" in msg.get("content", "").lower()
            for msg in history
        )

        # If we saw agent results and the last message is a coordinator summary, we're done
        if has_agent_results and "spawn" not in content:
            return True

        # If no agents were invoked, single-turn response is complete
        if role == "assistant" and len(history) >= 2:
            return True

        return False
