"""
web/api/auth.py -- Authentication for Shadowbox.

Simple username/password auth with session tokens.
Users and sessions stored in SQLite alongside conversations.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request

SESSION_TTL_HOURS = 24
COOKIE_NAME = "shadowbox_session"


def _hash_password(password: str, salt: str) -> str:
    """Hash a password with salt using SHA-256."""
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


class AuthDB:
    """User and session management."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'analyst',
                display_name TEXT,
                created_at TEXT NOT NULL,
                last_login TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (username) REFERENCES users(username)
            )
        """)
        self._conn.commit()

        # Create default admin if no users exist
        if self._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            self.create_user("admin", "shadowbox", role="admin", display_name="Administrator")

    def create_user(self, username: str, password: str, role: str = "analyst", display_name: str | None = None) -> dict:
        """Create a new user. Raises if username exists."""
        existing = self._conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            raise ValueError(f"User '{username}' already exists")

        salt = secrets.token_hex(16)
        password_hash = _hash_password(password, salt)
        now = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            "INSERT INTO users (username, password_hash, salt, role, display_name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (username, password_hash, salt, role, display_name or username, now),
        )
        self._conn.commit()
        return {"username": username, "role": role, "display_name": display_name or username}

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """Verify credentials. Returns user dict or None."""
        row = self._conn.execute(
            "SELECT username, password_hash, salt, role, display_name FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            return None

        expected_hash = _hash_password(password, row[2])
        if not hmac.compare_digest(row[1], expected_hash):
            return None

        # Update last login
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("UPDATE users SET last_login = ? WHERE username = ?", (now, username))
        self._conn.commit()

        return {"username": row[0], "role": row[3], "display_name": row[4]}

    def create_session(self, username: str) -> str:
        """Create a session token for a user."""
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=SESSION_TTL_HOURS)

        # Clean expired sessions
        self._conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now.isoformat(),))

        self._conn.execute(
            "INSERT INTO sessions (token, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, username, now.isoformat(), expires.isoformat()),
        )
        self._conn.commit()
        return token

    def validate_session(self, token: str) -> Optional[dict]:
        """Validate a session token. Returns user dict or None."""
        now = datetime.now(timezone.utc).isoformat()
        row = self._conn.execute(
            "SELECT s.username, u.role, u.display_name FROM sessions s JOIN users u ON s.username = u.username WHERE s.token = ? AND s.expires_at > ?",
            (token, now),
        ).fetchone()
        if not row:
            return None
        return {"username": row[0], "role": row[1], "display_name": row[2]}

    def delete_session(self, token: str) -> None:
        """Delete a session (logout)."""
        self._conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        self._conn.commit()

    def list_users(self) -> list[dict]:
        """List all users (admin only)."""
        rows = self._conn.execute(
            "SELECT username, role, display_name, created_at, last_login FROM users ORDER BY created_at"
        ).fetchall()
        return [
            {"username": r[0], "role": r[1], "display_name": r[2], "created_at": r[3], "last_login": r[4]}
            for r in rows
        ]

    def update_user(self, username: str, password: str | None = None, role: str | None = None, display_name: str | None = None) -> None:
        """Update user details."""
        if password:
            salt = secrets.token_hex(16)
            password_hash = _hash_password(password, salt)
            self._conn.execute(
                "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
                (password_hash, salt, username),
            )
        if role:
            self._conn.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
        if display_name:
            self._conn.execute("UPDATE users SET display_name = ? WHERE username = ?", (display_name, username))
        self._conn.commit()

    def delete_user(self, username: str) -> None:
        """Delete a user and their sessions."""
        if username == "admin":
            raise ValueError("Cannot delete the admin user")
        self._conn.execute("DELETE FROM sessions WHERE username = ?", (username,))
        self._conn.execute("DELETE FROM users WHERE username = ?", (username,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def get_current_user(request: Request) -> dict:
    """Extract and validate the current user from request cookies or Authorization header."""
    auth_db: AuthDB = request.app.state.auth_db

    # Check cookie first
    token = request.cookies.get(COOKIE_NAME)

    # Fall back to Authorization header
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = auth_db.validate_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired")

    return user


def require_admin(user: dict) -> None:
    """Raise 403 if user is not admin."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
