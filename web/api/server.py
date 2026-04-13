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
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from web.api.gateway_bridge import GatewayBridge
from web.api.sse import sse_event, extract_highlights
from web.api.auth import AuthDB, get_current_user, require_admin, COOKIE_NAME
from web.api.watchlist import WatchlistDB

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
    {"id": "threat-intel", "model": "openai/gpt-5", "role": "Intelligence analyst. IC-trained, cyber-focused. Precise, measured, patient. Confidence levels mean something here."},
    {"id": "report-writer", "model": "openai/gpt-5", "role": "Intelligence writer. Translates what the team found into what the audience needs. Precise, calibrated, quietly authoritative."},
    {"id": "log-querier", "model": "openai/gpt-4.1", "role": "Data engineer turned log intelligence specialist. Literal, precise, technically thorough. Returns what the data shows and nothing it doesn't."},
]


# -- Request/Response models --

class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    session_key: str | None = None
    agent: str | None = None  # Direct agent routing (bypass Marshall)

class InvestigateRequest(BaseModel):
    message: str
    investigation_id: str | None = None

class LoginRequest(BaseModel):
    username: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "analyst"
    display_name: str | None = None

class UpdateUserRequest(BaseModel):
    password: str | None = None
    role: str | None = None
    display_name: str | None = None

class ShareRequest(BaseModel):
    username: str
    mode: str = "read"  # "read" or "collaborate"

class WatchRequest(BaseModel):
    ioc_value: str
    ioc_type: str = "ip"  # ip, domain, hash
    risk: str = "UNKNOWN"


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

# OpenAI pricing per 1M tokens (as of 2026-04)
MODEL_PRICING = {
    "gpt-4.1":       {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini":  {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano":  {"input": 0.10, "output": 0.40},
    "gpt-4o":        {"input": 2.50, "output": 10.00},
    "gpt-4o-mini":   {"input": 0.15, "output": 0.60},
    "gpt-5":         {"input": 10.00, "output": 30.00},
}


def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate cost in USD based on model and token counts."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING.get("gpt-4.1", {"input": 2.00, "output": 8.00}))
    cost = (tokens_in / 1_000_000) * pricing["input"] + (tokens_out / 1_000_000) * pricing["output"]
    return round(cost, 6)


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
                cost_usd REAL DEFAULT 0,
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
            model = meta.get("model", "")
            tokens_in = meta.get("tokens_in", 0)
            tokens_out = meta.get("tokens_out", 0)
            tokens_total = meta.get("tokens", 0)
            cost = _estimate_cost(model, tokens_in, tokens_out)
            self._conn.execute(
                "INSERT INTO token_usage (agent, model, tokens_in, tokens_out, tokens_total, duration_ms, cost_usd, conversation_id, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (agent_id, model, tokens_in, tokens_out, tokens_total, meta.get("duration_ms", 0), cost, conversation_id, now),
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
                   SUM(cost_usd) as total_cost,
                   MAX(timestamp) as last_used
            FROM token_usage GROUP BY agent
        """).fetchall()
        return {
            r[0]: {
                "calls": r[1],
                "total_tokens": r[2] or 0,
                "total_duration_ms": r[3] or 0,
                "total_cost": round(r[4] or 0, 4),
                "last_used": r[5],
            }
            for r in rows
        }

    def get_totals(self) -> dict:
        """Get overall token usage totals."""
        row = self._conn.execute("""
            SELECT COUNT(*) as calls,
                   SUM(tokens_total) as total_tokens,
                   SUM(duration_ms) as total_duration_ms,
                   SUM(cost_usd) as total_cost
            FROM token_usage
        """).fetchone()
        return {
            "total_calls": row[0] or 0,
            "total_tokens": row[1] or 0,
            "total_duration_ms": row[2] or 0,
            "total_cost": round(row[3] or 0, 4),
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
                user_id TEXT,
                created_at TEXT,
                last_message_at TEXT,
                title TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_shares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                shared_with TEXT NOT NULL,
                shared_by TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'read',
                shared_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id),
                UNIQUE(conversation_id, shared_with)
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

    def get_or_create(self, conversation_id: str | None = None, user_id: str | None = None) -> dict:
        """Get existing conversation or create a new one."""
        if conversation_id:
            row = self._conn.execute(
                "SELECT conversation_id, session_key, investigation_id, user_id FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if row:
                return {
                    "conversation_id": row[0],
                    "session_key": row[1],
                    "investigation_id": row[2],
                    "user_id": row[3],
                }

        conv_id = conversation_id or str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR IGNORE INTO conversations (conversation_id, session_key, investigation_id, user_id, created_at, last_message_at, title) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (conv_id, None, None, user_id, now, now, None),
        )
        self._conn.commit()
        return {"conversation_id": conv_id, "session_key": None, "investigation_id": None, "user_id": user_id}

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

    def list_conversations(self, user_id: str | None = None) -> list[dict]:
        """List conversations: owned + shared with this user."""
        if user_id:
            # Own conversations
            rows = self._conn.execute(
                "SELECT conversation_id, session_key, investigation_id, created_at, last_message_at, title, user_id "
                "FROM conversations WHERE user_id = ? ORDER BY last_message_at DESC",
                (user_id,),
            ).fetchall()
            owned = [
                {
                    "conversation_id": r[0], "session_key": r[1], "investigation_id": r[2],
                    "created_at": r[3], "last_message_at": r[4], "title": r[5],
                    "owner": r[6], "access": "owner",
                }
                for r in rows
            ]
            # Shared with me
            shared_rows = self._conn.execute(
                "SELECT c.conversation_id, c.session_key, c.investigation_id, c.created_at, c.last_message_at, c.title, c.user_id, cs.mode "
                "FROM conversations c JOIN conversation_shares cs ON c.conversation_id = cs.conversation_id "
                "WHERE cs.shared_with = ? ORDER BY c.last_message_at DESC",
                (user_id,),
            ).fetchall()
            shared = [
                {
                    "conversation_id": r[0], "session_key": r[1], "investigation_id": r[2],
                    "created_at": r[3], "last_message_at": r[4], "title": r[5],
                    "owner": r[6], "access": r[7],
                }
                for r in shared_rows
            ]
            return owned + shared
        else:
            rows = self._conn.execute(
                "SELECT conversation_id, session_key, investigation_id, created_at, last_message_at, title, user_id "
                "FROM conversations ORDER BY last_message_at DESC"
            ).fetchall()
            return [
                {
                    "conversation_id": r[0], "session_key": r[1], "investigation_id": r[2],
                    "created_at": r[3], "last_message_at": r[4], "title": r[5],
                    "owner": r[6], "access": "admin",
                }
                for r in rows
            ]

    def share_conversation(self, conversation_id: str, shared_with: str, shared_by: str, mode: str = "read") -> None:
        """Share a conversation with another user."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO conversation_shares (conversation_id, shared_with, shared_by, mode, shared_at) VALUES (?, ?, ?, ?, ?)",
            (conversation_id, shared_with, shared_by, mode, now),
        )
        self._conn.commit()

    def unshare_conversation(self, conversation_id: str, shared_with: str) -> None:
        """Revoke a user's access to a shared conversation."""
        self._conn.execute(
            "DELETE FROM conversation_shares WHERE conversation_id = ? AND shared_with = ?",
            (conversation_id, shared_with),
        )
        self._conn.commit()

    def get_shares(self, conversation_id: str) -> list[dict]:
        """Get all shares for a conversation."""
        rows = self._conn.execute(
            "SELECT shared_with, shared_by, mode, shared_at FROM conversation_shares WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchall()
        return [{"shared_with": r[0], "shared_by": r[1], "mode": r[2], "shared_at": r[3]} for r in rows]

    def get_share_mode(self, conversation_id: str, username: str) -> str | None:
        """Check if a user has shared access. Returns mode or None."""
        row = self._conn.execute(
            "SELECT mode FROM conversation_shares WHERE conversation_id = ? AND shared_with = ?",
            (conversation_id, username),
        ).fetchone()
        return row[0] if row else None

    def get_conversation_owner(self, conversation_id: str) -> str | None:
        """Get the owner of a conversation."""
        row = self._conn.execute(
            "SELECT user_id FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        return row[0] if row else None

    def link_investigation(self, conversation_id: str, investigation_id: str) -> None:
        """Link a conversation to an investigation."""
        self._conn.execute(
            "UPDATE conversations SET investigation_id = ? WHERE conversation_id = ?",
            (investigation_id, conversation_id),
        )
        self._conn.commit()

    def get_conversation_for_investigation(self, investigation_id: str) -> str | None:
        """Find the conversation linked to an investigation."""
        row = self._conn.execute(
            "SELECT conversation_id FROM conversations WHERE investigation_id = ?",
            (investigation_id,),
        ).fetchone()
        return row[0] if row else None

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
    auth_db = AuthDB(db_path)
    watchlist_db = WatchlistDB(db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.bridge = bridge
        app.state.web_db = WebSessionDB(db_path)
        app.state.tracker = tracker
        app.state.auth_db = auth_db
        app.state.watchlist = watchlist_db
        yield
        await bridge.close()
        app.state.web_db.close()
        tracker.close()
        auth_db.close()
        watchlist_db.close()

    app = FastAPI(title="HOOK Web API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?",
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["content-type", "authorization"],
        allow_credentials=True,
    )

    # -- Auth Endpoints (no auth required) --

    @app.post("/api/auth/login")
    async def login(body: LoginRequest):
        auth: AuthDB = app.state.auth_db
        user = auth.authenticate(body.username, body.password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token = auth.create_session(body.username)
        response = JSONResponse({"status": "ok", "user": user})
        response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", max_age=86400)
        return response

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        token = request.cookies.get(COOKIE_NAME)
        if token:
            app.state.auth_db.delete_session(token)
        response = JSONResponse({"status": "ok"})
        response.delete_cookie(COOKIE_NAME)
        return response

    @app.get("/api/auth/me")
    async def me(request: Request):
        try:
            user = get_current_user(request)
            return {"status": "ok", "user": user}
        except HTTPException:
            return {"status": "unauthenticated", "user": None}

    # -- Admin Endpoints --

    @app.get("/api/admin/users")
    async def admin_list_users(request: Request):
        user = get_current_user(request)
        require_admin(user)
        return {"users": app.state.auth_db.list_users()}

    @app.post("/api/admin/users")
    async def admin_create_user(body: CreateUserRequest, request: Request):
        user = get_current_user(request)
        require_admin(user)
        try:
            new_user = app.state.auth_db.create_user(
                body.username, body.password, role=body.role, display_name=body.display_name
            )
            return {"status": "ok", "user": new_user}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.put("/api/admin/users/{username}")
    async def admin_update_user(username: str, body: UpdateUserRequest, request: Request):
        user = get_current_user(request)
        require_admin(user)
        app.state.auth_db.update_user(username, password=body.password, role=body.role, display_name=body.display_name)
        return {"status": "ok"}

    @app.delete("/api/admin/users/{username}")
    async def admin_delete_user(username: str, request: Request):
        user = get_current_user(request)
        require_admin(user)
        try:
            app.state.auth_db.delete_user(username)
            return {"status": "ok"}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

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

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        """Comprehensive health check for all services."""
        import subprocess as _sp

        checks = {}

        # Gateway
        gw = await app.state.bridge.health_check()
        checks["gateway"] = {"status": gw.get("status", "unknown"), "port": 18789}

        # Ollama
        try:
            from urllib.request import urlopen
            with urlopen("http://localhost:11434/api/tags", timeout=3) as resp:
                data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
                checks["ollama"] = {"status": "ok", "models": models}
        except Exception:
            checks["ollama"] = {"status": "unreachable", "models": []}

        # API keys — check env vars, .env file, and openclaw config
        def _key_exists(name):
            if os.environ.get(name):
                return True
            # Check .env file
            env_file = ROOT / ".env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith(f"{name}=") and len(line.split("=", 1)[1].strip()) > 0:
                        return True
            # Check openclaw config
            oc_config = Path.home() / ".openclaw" / "openclaw.json"
            if oc_config.exists():
                try:
                    oc = json.loads(oc_config.read_text())
                    if oc.get("env", {}).get(name):
                        return True
                except Exception:
                    pass
            return False

        env_keys = {
            "OPENAI_API_KEY": _key_exists("OPENAI_API_KEY"),
            "VT_API_KEY": _key_exists("VT_API_KEY"),
            "CENSYS_API_ID": _key_exists("CENSYS_API_ID"),
            "ABUSEIPDB_API_KEY": _key_exists("ABUSEIPDB_API_KEY"),
            "OTX_API_KEY": _key_exists("OTX_API_KEY"),
            "SHODAN_API_KEY": _key_exists("SHODAN_API_KEY"),
        }
        checks["api_keys"] = env_keys

        # Feed freshness
        feed_dir = DATA_DIR / "feeds"
        latest_feed = None
        if feed_dir.exists():
            feeds = sorted(feed_dir.glob("combined-*.txt"), reverse=True)
            if feeds:
                latest_feed = feeds[0].name
        checks["feeds"] = {"latest": latest_feed, "directory": str(feed_dir)}

        # RAG vector store
        faiss_dir = ROOT / "data" / "faiss"
        faiss_meta = faiss_dir / "hook-vectors.json"
        rag_count = 0
        if faiss_meta.exists():
            try:
                meta = json.loads(faiss_meta.read_text())
                rag_count = len(meta.get("id_to_pos", {}))
            except Exception:
                pass
        checks["rag"] = {"vectors": rag_count, "backend": "faiss" if faiss_meta.exists() else "none"}

        # Database
        web_db: WebSessionDB = app.state.web_db
        try:
            conv_count = len(web_db.list_conversations())
            msg_count = web_db._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            user_count = app.state.auth_db._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            checks["database"] = {"status": "ok", "conversations": conv_count, "messages": msg_count, "users": user_count}
        except Exception as exc:
            checks["database"] = {"status": "error", "error": str(exc)}

        # Token usage totals
        checks["usage"] = app.state.tracker.get_totals()

        # Overall
        all_ok = checks["gateway"]["status"] == "ok" and checks["database"]["status"] == "ok"
        return {
            "status": "healthy" if all_ok else "degraded",
            "checks": checks,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/audit")
    async def audit_log(request: Request) -> dict[str, Any]:
        """Return audit log of all agent calls with user, cost, and timing."""
        user = get_current_user(request)
        require_admin(user)
        tracker: AgentTracker = app.state.tracker
        rows = tracker._conn.execute(
            "SELECT agent, model, tokens_in, tokens_out, tokens_total, duration_ms, cost_usd, conversation_id, timestamp "
            "FROM token_usage ORDER BY timestamp DESC LIMIT 200"
        ).fetchall()
        entries = [
            {
                "agent": r[0], "model": r[1], "tokens_in": r[2], "tokens_out": r[3],
                "tokens_total": r[4], "duration_ms": r[5], "cost_usd": round(r[6] or 0, 4),
                "conversation_id": r[7], "timestamp": r[8],
            }
            for r in rows
        ]
        # Get conversation owners for audit context
        web_db: WebSessionDB = app.state.web_db
        for entry in entries:
            if entry["conversation_id"]:
                owner = web_db.get_conversation_owner(entry["conversation_id"])
                entry["user"] = owner
            else:
                entry["user"] = None
        return {"entries": entries, "totals": tracker.get_totals()}

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
                "total_cost": tokens.get("total_cost", 0),
            })
        return {"agents": enriched, "totals": totals}

    @app.post("/api/chat/stream")
    async def chat_stream(body: ChatRequest, request: Request):
        user = get_current_user(request)
        bridge: GatewayBridge = app.state.bridge
        web_db: WebSessionDB = app.state.web_db

        conv = web_db.get_or_create(body.conversation_id, user_id=user["username"])
        conversation_id = conv["conversation_id"]
        session_key = body.session_key or conv["session_key"]

        # Check access: owner, collaborator, or admin can send messages
        conv_owner = conv.get("user_id")
        if conv_owner and conv_owner != user["username"] and user["role"] != "admin":
            share_mode = web_db.get_share_mode(conversation_id, user["username"])
            if share_mode != "collaborate":
                raise HTTPException(status_code=403, detail="Read-only access to this conversation")

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
            agent_id = body.agent or "coordinator"
            async for raw_event in bridge.send_message(message_with_context, session_key=session_key, agent_id=agent_id):
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
                        # Detect investigation creation (INV-YYYYMMDD-NNN)
                        import re as _re
                        inv_match = _re.search(r'(INV-\d{8}-\d{3})', content)
                        if inv_match:
                            web_db.link_investigation(conversation_id, inv_match.group(1))

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

    @app.post("/api/conversations/{conversation_id}/share")
    async def share_conversation(conversation_id: str, body: ShareRequest, request: Request):
        user = get_current_user(request)
        _validate_id(conversation_id, "conversation ID")
        web_db: WebSessionDB = app.state.web_db
        owner = web_db.get_conversation_owner(conversation_id)
        if owner != user["username"] and user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Only the owner can share this conversation")
        if body.mode not in ("read", "collaborate"):
            raise HTTPException(status_code=400, detail="Mode must be 'read' or 'collaborate'")
        web_db.share_conversation(conversation_id, body.username, user["username"], body.mode)
        return {"status": "ok", "shared_with": body.username, "mode": body.mode}

    @app.delete("/api/conversations/{conversation_id}/share/{username}")
    async def unshare_conversation(conversation_id: str, username: str, request: Request):
        user = get_current_user(request)
        _validate_id(conversation_id, "conversation ID")
        web_db: WebSessionDB = app.state.web_db
        owner = web_db.get_conversation_owner(conversation_id)
        if owner != user["username"] and user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Only the owner can manage sharing")
        web_db.unshare_conversation(conversation_id, username)
        return {"status": "ok"}

    @app.get("/api/conversations/{conversation_id}/shares")
    async def get_shares(conversation_id: str, request: Request):
        user = get_current_user(request)
        _validate_id(conversation_id, "conversation ID")
        web_db: WebSessionDB = app.state.web_db
        return {"shares": web_db.get_shares(conversation_id)}

    # -- Watchlist & Notifications --

    @app.get("/api/watchlist")
    async def list_watchlist(request: Request):
        user = get_current_user(request)
        wl: WatchlistDB = app.state.watchlist
        items = wl.list_watched(user_id=user["username"])
        return {"items": items}

    @app.post("/api/watchlist")
    async def add_to_watchlist(body: WatchRequest, request: Request):
        user = get_current_user(request)
        wl: WatchlistDB = app.state.watchlist
        result = wl.watch(body.ioc_value, body.ioc_type, user["username"], body.risk)
        return result

    @app.delete("/api/watchlist/{ioc_value}")
    async def remove_from_watchlist(ioc_value: str, request: Request):
        user = get_current_user(request)
        wl: WatchlistDB = app.state.watchlist
        wl.unwatch(ioc_value, user["username"])
        return {"status": "ok"}

    @app.get("/api/watchlist/{ioc_value}/history")
    async def watch_history(ioc_value: str, request: Request):
        user = get_current_user(request)
        wl: WatchlistDB = app.state.watchlist
        return {"history": wl.get_history(ioc_value)}

    @app.get("/api/notifications")
    async def get_notifications(request: Request):
        user = get_current_user(request)
        wl: WatchlistDB = app.state.watchlist
        return {
            "items": wl.get_notifications(user["username"]),
            "unread": wl.unread_count(user["username"]),
        }

    @app.post("/api/notifications/{notification_id}/read")
    async def mark_notification_read(notification_id: int, request: Request):
        user = get_current_user(request)
        wl: WatchlistDB = app.state.watchlist
        wl.mark_read(notification_id, user["username"])
        return {"status": "ok"}

    @app.post("/api/notifications/read-all")
    async def mark_all_notifications_read(request: Request):
        user = get_current_user(request)
        wl: WatchlistDB = app.state.watchlist
        wl.mark_all_read(user["username"])
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

        # Find linked conversation
        web_db: WebSessionDB = app.state.web_db
        linked_conversation = web_db.get_conversation_for_investigation(inv_id)

        return {**state, "findings_detail": findings_detail, "conversation_id": linked_conversation}

    @app.put("/api/investigations/{inv_id}/status")
    async def update_investigation_status(inv_id: str, request: Request):
        _validate_id(inv_id, "investigation ID")
        body = await request.json()
        new_status = body.get("status")
        disposition = body.get("disposition")

        inv_dir = INVESTIGATIONS_DIR / inv_id
        state_file = inv_dir / "state.json"
        if not inv_dir.resolve().is_relative_to(INVESTIGATIONS_DIR.resolve()):
            raise HTTPException(status_code=403, detail="Access denied")
        if not state_file.exists():
            raise HTTPException(status_code=404, detail="Investigation not found")

        state = json.loads(state_file.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc).isoformat()

        if new_status:
            state["status"] = new_status
            state["timeline"].append({
                "timestamp": now,
                "event": f"Status changed to {new_status}",
                "agent": "operator",
            })
        if disposition:
            state["disposition"] = disposition
            state["timeline"].append({
                "timestamp": now,
                "event": f"Disposition set to {disposition}",
                "agent": "operator",
            })
        state["updated_at"] = now
        state_file.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        return {"status": "ok"}

    @app.post("/api/investigations/{inv_id}/notes")
    async def add_investigation_note(inv_id: str, request: Request):
        _validate_id(inv_id, "investigation ID")
        body = await request.json()
        note_text = body.get("note", "").strip()
        if not note_text:
            raise HTTPException(status_code=400, detail="Note cannot be empty")

        inv_dir = INVESTIGATIONS_DIR / inv_id
        state_file = inv_dir / "state.json"
        if not inv_dir.resolve().is_relative_to(INVESTIGATIONS_DIR.resolve()):
            raise HTTPException(status_code=403, detail="Access denied")
        if not state_file.exists():
            raise HTTPException(status_code=404, detail="Investigation not found")

        user = get_current_user(request)
        state = json.loads(state_file.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc).isoformat()

        if "notes" not in state:
            state["notes"] = []
        state["notes"].append({
            "text": note_text,
            "author": user.get("display_name", user["username"]),
            "timestamp": now,
        })
        state["timeline"].append({
            "timestamp": now,
            "event": f"Note added by {user.get('display_name', user['username'])}",
            "agent": "operator",
        })
        state["updated_at"] = now
        state_file.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        return {"status": "ok"}

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
    async def conversations(request: Request) -> dict[str, Any]:
        user = get_current_user(request)
        web_db: WebSessionDB = app.state.web_db
        # Admins see all conversations, analysts see only their own
        user_filter = None if user["role"] == "admin" else user["username"]
        return {"items": web_db.list_conversations(user_id=user_filter)}

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
