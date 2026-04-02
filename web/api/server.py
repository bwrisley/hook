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
    {"id": "coordinator", "model": "openai/gpt-4.1", "role": "Routes requests, chains workflows"},
    {"id": "triage-analyst", "model": "openai/gpt-4.1", "role": "Alert triage: TP/FP/Suspicious/Escalate"},
    {"id": "osint-researcher", "model": "openai/gpt-4.1", "role": "IOC enrichment via VT, Censys, AbuseIPDB"},
    {"id": "incident-responder", "model": "openai/gpt-5", "role": "NIST 800-61 IR guidance"},
    {"id": "threat-intel", "model": "openai/gpt-5", "role": "Structured analytic techniques (ACH)"},
    {"id": "report-writer", "model": "openai/gpt-4.1", "role": "Audience-adapted reports"},
    {"id": "log-querier", "model": "openai/gpt-4.1", "role": "Natural language log queries"},
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

class WebSessionDB:
    """Lightweight SQLite store mapping web conversations to OpenClaw sessions."""

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
                last_message_at TEXT
            )
        """)
        self._conn.commit()

    def get_or_create(self, conversation_id: str | None = None) -> dict:
        """Get existing conversation or create a new one."""
        if conversation_id:
            row = self._conn.execute(
                "SELECT * FROM conversations WHERE conversation_id = ?",
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
            "INSERT OR IGNORE INTO conversations VALUES (?, ?, ?, ?, ?)",
            (conv_id, None, None, now, now),
        )
        self._conn.commit()
        return {"conversation_id": conv_id, "session_key": None, "investigation_id": None}

    def update_session_key(self, conversation_id: str, session_key: str) -> None:
        """Link a web conversation to an OpenClaw session."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE conversations SET session_key = ?, last_message_at = ? WHERE conversation_id = ?",
            (session_key, now, conversation_id),
        )
        self._conn.commit()

    def list_conversations(self) -> list[dict]:
        """List all conversations ordered by most recent."""
        rows = self._conn.execute(
            "SELECT conversation_id, session_key, investigation_id, created_at, last_message_at "
            "FROM conversations ORDER BY last_message_at DESC"
        ).fetchall()
        return [
            {
                "conversation_id": r[0],
                "session_key": r[1],
                "investigation_id": r[2],
                "created_at": r[3],
                "last_message_at": r[4],
            }
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()


# -- App factory --

def create_app() -> FastAPI:
    bridge = GatewayBridge()
    db_path = str(DATA_DIR / "hook-web.db")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.bridge = bridge
        app.state.web_db = WebSessionDB(db_path)
        yield
        await bridge.close()
        app.state.web_db.close()

    app = FastAPI(title="HOOK Web API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:7799",
            "http://127.0.0.1:7799",
        ],
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
        gw_agents = await app.state.bridge.get_agents()
        if gw_agents:
            return {"agents": gw_agents}
        return {"agents": AGENTS, "source": "static"}

    @app.post("/api/chat/stream")
    async def chat_stream(body: ChatRequest):
        bridge: GatewayBridge = app.state.bridge
        web_db: WebSessionDB = app.state.web_db

        conv = web_db.get_or_create(body.conversation_id)
        conversation_id = conv["conversation_id"]
        session_key = body.session_key or conv["session_key"]

        async def event_stream():
            yield sse_event("meta", {"conversation_id": conversation_id})

            new_session_key = None
            async for event in bridge.send_message(body.message, session_key=session_key):
                yield event
                # Capture session key from meta event if new session was created
                if '"session_key"' in event and new_session_key is None:
                    try:
                        data = json.loads(event.split("data: ", 1)[1].split("\n")[0])
                        if "session_key" in data:
                            new_session_key = data["session_key"]
                            web_db.update_session_key(conversation_id, new_session_key)
                    except (json.JSONDecodeError, IndexError):
                        pass

        return StreamingResponse(event_stream(), media_type="text/event-stream")

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

    # -- Static file serving (production) --

    if DIST_DIR.exists():
        app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="web")
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
