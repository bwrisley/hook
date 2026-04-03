"""
web/api/server.py -- HOOK Web API.

FastAPI server providing:
  - SSE-streamed chat via OpenClaw gateway bridge
  - Agent status and investigation management
  - Threat feed and config views

Runs on port 7799 alongside the existing Slack interface.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from web.api.gateway_bridge import GatewayBridge
from web.api.sse import sse_event, extract_highlights

ROOT = Path(__file__).resolve().parents[2]
DIST_DIR = ROOT / "web" / "dist"
DATA_DIR = ROOT / "data"
CONFIG_TEMPLATE = ROOT / "config" / "openclaw.json.template"
INVESTIGATIONS_DIR = DATA_DIR / "investigations"

SECRET_RE = re.compile(
    r"(password|secret|token|api[_-]?key|client[_-]?secret)", re.IGNORECASE
)

# Agent definitions for static fallback when gateway is unreachable
AGENTS = [
    {"id": "coordinator", "model": "openai/gpt-4.1", "role": "Senior SOC coordinator. Calm, dry, decisive. Earns authority by knowing exactly who to hand work to and giving them everything they need."},
    {"id": "triage-analyst", "model": "openai/gpt-4.1", "role": "Tier 2 SOC analyst. Seen everything twice. Clinical, precise, no-nonsense. Calls what she sees and shows her work."},
    {"id": "osint-researcher", "model": "openai/gpt-4.1", "role": "Infrastructure intelligence analyst. Follows the thread past where most analysts stop. Methodical, thorough, quietly precise."},
    {"id": "incident-responder", "model": "openai/gpt-4.1", "role": "Federal IR lead. Contain first, understand later. Calm, precise, framework-driven. Has been in worse situations than this one."},
    {"id": "threat-intel", "model": "openai/gpt-4.1", "role": "Intelligence analyst. IC-trained, cyber-focused. Precise, measured, patient. Confidence levels mean something here."},
    {"id": "report-writer", "model": "openai/gpt-4.1", "role": "Intelligence writer. Translates what the team found into what the audience needs. Precise, calibrated, quietly authoritative."},
    {"id": "log-querier", "model": "openai/gpt-4.1", "role": "Data engineer turned log intelligence specialist. Literal, precise, technically thorough. Returns what the data shows and nothing it doesn't."},
]


# -- Request/Response models --

class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    session_key: str | None = None

class InvestigateRequest(BaseModel):
    message: str
    investigation_id: str | None = None


# -- Input validation --

def _validate_id(value: str, label: str = "ID") -> None:
    """Validate that an ID contains only safe characters."""
    if not value or not all(c.isalnum() or c in "-_" for c in value):
        raise HTTPException(status_code=400, detail=f"Invalid {label} format")


def _mask_secrets(config: dict) -> dict:
    """Recursively mask secret values in a config dict."""
    masked = {}
    for key, value in config.items():
        if isinstance(value, dict):
            masked[key] = _mask_secrets(value)
        elif isinstance(value, str) and SECRET_RE.search(key):
            masked[key] = "********" if value and not value.startswith("YOUR_") else value
        else:
            masked[key] = value
    return masked


# -- Web session DB --

class AgentTracker:
    """Tracks agent activity and token usage."""

    def __init__(self, db_path: str) -> None:
        self._activity: dict[str, dict] = {}
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                model TEXT,
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                tokens_total INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                conversation_id TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def record_start(self, agent_id: str) -> None:
        self._activity[agent_id] = {
            "status": "working",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
        }

    def record_done(self, agent_id: str, meta: dict | None = None, conversation_id: str | None = None) -> None:
        if agent_id in self._activity:
            self._activity[agent_id]["status"] = "idle"
            self._activity[agent_id]["finished_at"] = datetime.now(timezone.utc).isoformat()

        if meta:
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                "INSERT INTO token_usage (agent, model, tokens_in, tokens_out, tokens_total, duration_ms, conversation_id, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    agent_id,
                    meta.get("model", ""),
                    meta.get("tokens_in", 0),
                    meta.get("tokens_out", 0),
                    meta.get("tokens", 0),
                    meta.get("duration_ms", 0),
                    conversation_id,
                    now,
                ),
            )
            self._conn.commit()

    def get_status(self) -> dict[str, dict]:
        return dict(self._activity)

    def get_agent_stats(self) -> dict[str, dict]:
        """Get per-agent token usage totals."""
        rows = self._conn.execute("""
            SELECT agent,
                   COUNT(*) as calls,
                   SUM(tokens_total) as total_tokens,
                   SUM(duration_ms) as total_duration_ms,
                   MAX(timestamp) as last_used
            FROM token_usage GROUP BY agent
        """).fetchall()
        return {
            r[0]: {
                "calls": r[1],
                "total_tokens": r[2] or 0,
                "total_duration_ms": r[3] or 0,
                "last_used": r[4],
            }
            for r in rows
        }

    def get_totals(self) -> dict:
        """Get overall token usage totals."""
        row = self._conn.execute("""
            SELECT COUNT(*) as calls,
                   SUM(tokens_total) as total_tokens,
                   SUM(duration_ms) as total_duration_ms
            FROM token_usage
        """).fetchone()
        return {
            "total_calls": row[0] or 0,
            "total_tokens": row[1] or 0,
            "total_duration_ms": row[2] or 0,
        }

    def close(self) -> None:
        self._conn.close()


class WebSessionDB:
    """SQLite store for web conversations and message history."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                session_key TEXT,
                investigation_id TEXT,
                created_at TEXT,
                last_message_at TEXT,
                title TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                agent TEXT,
                content TEXT NOT NULL,
                msg_type TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            )
        """)
        self._conn.commit()

    def get_or_create(self, conversation_id: str | None = None) -> dict:
        """Get existing conversation or create a new one."""
        if conversation_id:
            row = self._conn.execute(
                "SELECT conversation_id, session_key, investigation_id FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if row:
                return {
                    "conversation_id": row[0],
                    "session_key": row[1],
                    "investigation_id": row[2],
                }

        conv_id = conversation_id or str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR IGNORE INTO conversations (conversation_id, session_key, investigation_id, created_at, last_message_at, title) VALUES (?, ?, ?, ?, ?, ?)",
            (conv_id, None, None, now, now, None),
        )
        self._conn.commit()
        return {"conversation_id": conv_id, "session_key": None, "investigation_id": None}

    def update_session_key(self, conversation_id: str, session_key: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE conversations SET session_key = ?, last_message_at = ? WHERE conversation_id = ?",
            (session_key, now, conversation_id),
        )
        self._conn.commit()

    def add_message(self, conversation_id: str, role: str, content: str, agent: str | None = None, msg_type: str | None = None) -> None:
        """Store a message in the conversation history."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO messages (conversation_id, role, agent, content, msg_type, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (conversation_id, role, agent, content, msg_type, now),
        )
        # Update conversation timestamp and title (first user message becomes title)
        self._conn.execute(
            "UPDATE conversations SET last_message_at = ? WHERE conversation_id = ?",
            (now, conversation_id),
        )
        if role == "user":
            self._conn.execute(
                "UPDATE conversations SET title = ? WHERE conversation_id = ? AND title IS NULL",
                (content[:100], conversation_id),
            )
        self._conn.commit()

    def get_messages(self, conversation_id: str) -> list[dict]:
        """Get all messages for a conversation."""
        rows = self._conn.execute(
            "SELECT id, role, agent, content, msg_type, timestamp FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
        return [
            {
                "msg_id": r[0],
                "role": r[1],
                "agent": r[2],
                "content": r[3],
                "type": r[4],
                "timestamp": r[5],
            }
            for r in rows
        ]

    def list_conversations(self) -> list[dict]:
        """List all conversations ordered by most recent."""
        rows = self._conn.execute(
            "SELECT conversation_id, session_key, investigation_id, created_at, last_message_at, title "
            "FROM conversations ORDER BY last_message_at DESC"
        ).fetchall()
        return [
            {
                "conversation_id": r[0],
                "session_key": r[1],
                "investigation_id": r[2],
                "created_at": r[3],
                "last_message_at": r[4],
                "title": r[5],
            }
            for r in rows
        ]

    def delete_conversation(self, conversation_id: str) -> None:
        """Delete a conversation and all its messages."""
        self._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        self._conn.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
        self._conn.commit()

    def delete_message(self, message_id: int) -> None:
        """Delete a single message by its row ID."""
        self._conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


# -- App factory --

def create_app() -> FastAPI:
    bridge = GatewayBridge()
    db_path = str(DATA_DIR / "hook-web.db")

    tracker = AgentTracker(db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.bridge = bridge
        app.state.web_db = WebSessionDB(db_path)
        app.state.tracker = tracker
        yield
        await bridge.close()
        app.state.web_db.close()
        tracker.close()

    app = FastAPI(title="HOOK Web API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["content-type"],
        allow_credentials=False,
    )

    # -- Endpoints --

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        gw_health = await app.state.bridge.health_check()
        inv_count = 0
        if INVESTIGATIONS_DIR.exists():
            inv_count = sum(1 for p in INVESTIGATIONS_DIR.iterdir() if p.is_dir())
        return {
            "name": "HOOK",
            "version": "6.0.0",
            "gateway": gw_health,
            "agent_count": len(AGENTS),
            "active_investigations": inv_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/agents")
    async def agents() -> dict[str, Any]:
        web_db: WebSessionDB = app.state.web_db
        activity = app.state.tracker.get_status()
        token_stats = app.state.tracker.get_agent_stats()
        totals = app.state.tracker.get_totals()

        # Count messages per agent from DB
        agent_stats = {}
        try:
            rows = web_db._conn.execute(
                "SELECT agent, COUNT(*) as cnt, MAX(timestamp) as last_active "
                "FROM messages WHERE agent IS NOT NULL GROUP BY agent"
            ).fetchall()
            for row in rows:
                agent_stats[row[0]] = {"message_count": row[1], "last_active": row[2]}
        except Exception:
            pass

        enriched = []
        for agent in AGENTS:
            aid = agent["id"]
            live = activity.get(aid, {})
            stats = agent_stats.get(aid, {})
            tokens = token_stats.get(aid, {})
            enriched.append({
                **agent,
                "status": live.get("status", "idle"),
                "last_started": live.get("started_at"),
                "last_finished": live.get("finished_at"),
                "message_count": stats.get("message_count", 0),
                "last_active": stats.get("last_active"),
                "total_tokens": tokens.get("total_tokens", 0),
                "total_calls": tokens.get("calls", 0),
                "total_duration_ms": tokens.get("total_duration_ms", 0),
            })
        return {"agents": enriched, "totals": totals}

    @app.post("/api/chat/stream")
    async def chat_stream(body: ChatRequest):
        bridge: GatewayBridge = app.state.bridge
        web_db: WebSessionDB = app.state.web_db

        conv = web_db.get_or_create(body.conversation_id)
        conversation_id = conv["conversation_id"]
        session_key = body.session_key or conv["session_key"]

        # Persist the user message
        web_db.add_message(conversation_id, "user", body.message)

        # Build conversation context for multi-turn continuity
        CALLSIGNS = {
            "coordinator": "Marshall", "triage-analyst": "Tara",
            "osint-researcher": "Hunter", "incident-responder": "Ward",
            "threat-intel": "Driver", "report-writer": "Page", "log-querier": "Wells",
        }
        prior_messages = web_db.get_messages(conversation_id)
        context_lines = []
        # Compact context: user messages in full, agent findings truncated to key data
        for msg in prior_messages[:-1][-12:]:
            if msg["role"] == "user":
                context_lines.append(f"[Operator]: {msg['content']}")
            else:
                agent_name = CALLSIGNS.get(msg.get("agent"), msg.get("agent") or "System")
                content = msg["content"]
                # Truncate long agent findings to first 400 chars for context
                # The full findings are available if the operator asks for detail
                if len(content) > 400:
                    content = content[:400] + " [...]"
                context_lines.append(f"[{agent_name}]: {content}")
        conversation_context = "\n".join(context_lines)

        # Build the message with context if there's prior conversation
        message_with_context = body.message
        if conversation_context:
            message_with_context = f"""Conversation context:
{conversation_context}

Operator: {body.message}

Respond to the operator's latest message. Use the conversation context to resolve references ("that IP", "the report", etc.). If they need a specialist, route to one."""

        async def event_stream():
            yield sse_event("meta", {"conversation_id": conversation_id})

            new_session_key = None
            async for raw_event in bridge.send_message(message_with_context, session_key=session_key):
                yield raw_event

                # Parse the SSE event to extract type and data
                event_type = None
                event_data = None
                for line in raw_event.strip().split("\n"):
                    if line.startswith("event: "):
                        event_type = line[7:]
                    elif line.startswith("data: "):
                        try:
                            event_data = json.loads(line[6:])
                        except json.JSONDecodeError:
                            pass

                if not event_type or not event_data:
                    continue

                # Capture session key
                if event_type == "meta" and "session_key" in event_data and new_session_key is None:
                    new_session_key = event_data["session_key"]
                    web_db.update_session_key(conversation_id, new_session_key)

                # Track agent activity
                if event_type == "agent_start":
                    tracker.record_start(event_data.get("agent", "coordinator"))

                # Persist agent responses and track completion with token usage
                if event_type in ("agent_result", "coordinator"):
                    content = event_data.get("content", "")
                    agent = event_data.get("agent", "coordinator")
                    meta = event_data.get("meta", {})
                    tracker.record_done(agent, meta=meta, conversation_id=conversation_id)
                    if content:
                        web_db.add_message(conversation_id, "assistant", content, agent=agent, msg_type=event_type)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/api/conversations/{conversation_id}/messages")
    async def conversation_messages(conversation_id: str) -> dict[str, Any]:
        _validate_id(conversation_id, "conversation ID")
        web_db: WebSessionDB = app.state.web_db
        return {"messages": web_db.get_messages(conversation_id)}

    @app.delete("/api/conversations/{conversation_id}")
    async def delete_conversation(conversation_id: str) -> dict[str, str]:
        _validate_id(conversation_id, "conversation ID")
        web_db: WebSessionDB = app.state.web_db
        web_db.delete_conversation(conversation_id)
        return {"status": "ok"}

    @app.delete("/api/messages/{message_id}")
    async def delete_message(message_id: int) -> dict[str, str]:
        web_db: WebSessionDB = app.state.web_db
        web_db.delete_message(message_id)
        return {"status": "ok"}

    @app.get("/api/investigations")
    async def investigations() -> dict[str, Any]:
        items = []
        if INVESTIGATIONS_DIR.exists():
            for inv_dir in sorted(INVESTIGATIONS_DIR.iterdir(), reverse=True):
                state_file = inv_dir / "state.json"
                if state_file.exists():
                    try:
                        state = json.loads(state_file.read_text(encoding="utf-8"))
                        items.append({
                            "id": state.get("id", inv_dir.name),
                            "title": state.get("title", ""),
                            "status": state.get("status", "unknown"),
                            "ioc_count": len(state.get("iocs", [])),
                            "finding_count": len(state.get("findings", [])),
                            "created_at": state.get("created_at", ""),
                        })
                    except json.JSONDecodeError:
                        pass
        return {"items": items}

    @app.get("/api/investigations/{inv_id}")
    async def investigation_detail(inv_id: str) -> dict[str, Any]:
        _validate_id(inv_id, "investigation ID")
        inv_dir = INVESTIGATIONS_DIR / inv_id
        state_file = inv_dir / "state.json"

        # Prevent path traversal
        if not inv_dir.resolve().is_relative_to(INVESTIGATIONS_DIR.resolve()):
            raise HTTPException(status_code=403, detail="Access denied")

        if not state_file.exists():
            raise HTTPException(status_code=404, detail="Investigation not found")

        state = json.loads(state_file.read_text(encoding="utf-8"))

        # Load finding detail files
        findings_dir = inv_dir / "findings"
        findings_detail = []
        if findings_dir.exists():
            for f in sorted(findings_dir.iterdir()):
                if f.suffix == ".md":
                    findings_detail.append({
                        "filename": f.name,
                        "content": f.read_text(encoding="utf-8"),
                    })

        return {**state, "findings_detail": findings_detail}

    @app.post("/api/investigate")
    async def investigate(body: InvestigateRequest):
        """Start a new investigation. Creates investigation context then streams."""
        bridge: GatewayBridge = app.state.bridge
        web_db: WebSessionDB = app.state.web_db

        conv = web_db.get_or_create()
        conversation_id = conv["conversation_id"]

        async def event_stream():
            yield sse_event("meta", {"conversation_id": conversation_id})
            yield sse_event("investigation", {"status": "starting", "message": body.message})

            async for event in bridge.send_message(body.message):
                yield event

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/api/skills")
    async def skills() -> dict[str, Any]:
        """Return available Lobster pipelines."""
        pipelines_dir = ROOT / "pipelines"
        items = []
        if pipelines_dir.exists():
            for p in sorted(pipelines_dir.glob("*.yaml")):
                items.append({
                    "name": p.stem,
                    "filename": p.name,
                })
        return {"items": items}

    @app.get("/api/feeds")
    async def feeds() -> dict[str, Any]:
        """Return threat feed status."""
        feeds_dir = DATA_DIR / "feeds"
        watchlist_file = DATA_DIR / "watchlist.txt"

        feed_files = []
        if feeds_dir.exists():
            for f in sorted(feeds_dir.iterdir()):
                if f.is_file():
                    stat = f.stat()
                    feed_files.append({
                        "name": f.name,
                        "size_bytes": stat.st_size,
                        "last_modified": datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).isoformat(),
                    })

        watchlist_count = 0
        if watchlist_file.exists():
            watchlist_count = sum(
                1 for line in watchlist_file.read_text().splitlines()
                if line.strip() and not line.startswith("#")
            )

        return {
            "feeds": feed_files,
            "watchlist_count": watchlist_count,
        }

    @app.get("/api/config")
    async def config() -> dict[str, Any]:
        """Return masked configuration (read-only)."""
        if CONFIG_TEMPLATE.exists():
            try:
                raw = json.loads(CONFIG_TEMPLATE.read_text(encoding="utf-8"))
                return {"config": _mask_secrets(raw), "source": "template"}
            except json.JSONDecodeError:
                return {"config": {}, "error": "Invalid JSON in config template"}
        return {"config": {}, "error": "Config template not found"}

    @app.get("/api/conversations")
    async def conversations() -> dict[str, Any]:
        web_db: WebSessionDB = app.state.web_db
        return {"items": web_db.list_conversations()}

    # -- Static file serving (production SPA) --

    if DIST_DIR.exists():
        from fastapi.responses import FileResponse

        # Serve static assets (JS, CSS, etc.)
        app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

        # Catch-all: serve index.html for all non-API routes (SPA client-side routing)
        @app.get("/{path:path}")
        async def spa_catch_all(path: str):
            # If it's a real file in dist, serve it
            file_path = DIST_DIR / path
            if path and file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            # Otherwise serve index.html for client-side routing
            return FileResponse(str(DIST_DIR / "index.html"))
    else:
        @app.get("/")
        async def root() -> dict[str, str]:
            return {
                "message": "HOOK web frontend is not built yet.",
                "hint": "Run 'cd web && npm install && npm run build' then restart.",
            }

    return app


app = create_app()


def run_server(host: str = "0.0.0.0", port: int = 7799) -> None:
    """Entry point for running the HOOK web server."""
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    run_server()
