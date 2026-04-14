"""
web/api/watchlist.py -- IOC watchlist with change detection and notifications.

Stores watched IOCs, tracks risk history, detects changes,
and creates notifications when risk profiles shift.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


class WatchlistDB:
    """Manages watched IOCs, risk history, and notifications."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ioc_value TEXT NOT NULL,
                ioc_type TEXT NOT NULL,
                user_id TEXT NOT NULL,
                current_risk TEXT DEFAULT 'UNKNOWN',
                last_checked TEXT,
                last_changed TEXT,
                check_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                UNIQUE(ioc_value, user_id)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS watch_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ioc_value TEXT NOT NULL,
                risk_before TEXT,
                risk_after TEXT,
                summary TEXT,
                detail TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT,
                ioc_value TEXT,
                conversation_id TEXT,
                read INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_feed (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                ioc_value TEXT,
                ioc_type TEXT,
                risk TEXT,
                detail TEXT,
                conversation_id TEXT,
                investigation_id TEXT,
                created_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    # -- Activity Feed --

    def log_activity(
        self,
        user_id: str,
        action: str,
        ioc_value: str | None = None,
        ioc_type: str | None = None,
        risk: str | None = None,
        detail: str | None = None,
        conversation_id: str | None = None,
        investigation_id: str | None = None,
    ) -> None:
        """Log an activity to the shared team feed."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO activity_feed (user_id, action, ioc_value, ioc_type, risk, detail, conversation_id, investigation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, action, ioc_value, ioc_type, risk, detail, conversation_id, investigation_id, now),
        )
        self._conn.commit()

    def get_activity(self, limit: int = 50) -> list[dict]:
        """Get the shared activity feed (all users)."""
        rows = self._conn.execute(
            "SELECT id, user_id, action, ioc_value, ioc_type, risk, detail, conversation_id, investigation_id, created_at "
            "FROM activity_feed ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0], "user_id": r[1], "action": r[2], "ioc_value": r[3],
                "ioc_type": r[4], "risk": r[5], "detail": r[6],
                "conversation_id": r[7], "investigation_id": r[8], "created_at": r[9],
            }
            for r in rows
        ]

    def get_ioc_history(self, ioc_value: str) -> list[dict]:
        """Get all activity for a specific IOC across all users."""
        rows = self._conn.execute(
            "SELECT user_id, action, risk, detail, created_at FROM activity_feed WHERE ioc_value = ? ORDER BY created_at DESC LIMIT 20",
            (ioc_value,),
        ).fetchall()
        return [{"user_id": r[0], "action": r[1], "risk": r[2], "detail": r[3], "created_at": r[4]} for r in rows]

    # -- Watchlist CRUD --

    def watch(self, ioc_value: str, ioc_type: str, user_id: str, initial_risk: str = "UNKNOWN") -> dict:
        """Add an IOC to the watchlist."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._conn.execute(
                "INSERT INTO watchlist (ioc_value, ioc_type, user_id, current_risk, created_at) VALUES (?, ?, ?, ?, ?)",
                (ioc_value, ioc_type, user_id, initial_risk, now),
            )
            self._conn.commit()
            return {"status": "ok", "ioc": ioc_value, "action": "added"}
        except sqlite3.IntegrityError:
            # Already watching — reactivate if inactive
            self._conn.execute(
                "UPDATE watchlist SET active = 1, current_risk = ? WHERE ioc_value = ? AND user_id = ?",
                (initial_risk, ioc_value, user_id),
            )
            self._conn.commit()
            return {"status": "ok", "ioc": ioc_value, "action": "reactivated"}

    def unwatch(self, ioc_value: str, user_id: str) -> None:
        """Remove an IOC from the watchlist."""
        self._conn.execute(
            "UPDATE watchlist SET active = 0 WHERE ioc_value = ? AND user_id = ?",
            (ioc_value, user_id),
        )
        self._conn.commit()

    def list_watched(self, user_id: str | None = None, active_only: bool = True) -> list[dict]:
        """List watched IOCs, optionally filtered by user."""
        query = "SELECT ioc_value, ioc_type, user_id, current_risk, last_checked, last_changed, check_count, created_at FROM watchlist"
        params = []
        conditions = []
        if active_only:
            conditions.append("active = 1")
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC"

        rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "ioc_value": r[0], "ioc_type": r[1], "user_id": r[2],
                "current_risk": r[3], "last_checked": r[4], "last_changed": r[5],
                "check_count": r[6], "created_at": r[7],
            }
            for r in rows
        ]

    def get_all_active(self) -> list[dict]:
        """Get all active watched IOCs across all users (for scheduled re-enrichment)."""
        return self.list_watched(active_only=True)

    def update_risk(self, ioc_value: str, new_risk: str, summary: str, detail: str = "") -> list[str]:
        """Update risk for a watched IOC. Returns list of user_ids to notify if risk changed."""
        now = datetime.now(timezone.utc).isoformat()
        rows = self._conn.execute(
            "SELECT user_id, current_risk FROM watchlist WHERE ioc_value = ? AND active = 1",
            (ioc_value,),
        ).fetchall()

        changed_users = []
        for user_id, old_risk in rows:
            self._conn.execute(
                "UPDATE watchlist SET current_risk = ?, last_checked = ?, check_count = check_count + 1 WHERE ioc_value = ? AND user_id = ?",
                (new_risk, now, ioc_value, user_id),
            )
            if old_risk != new_risk and old_risk != "UNKNOWN":
                self._conn.execute(
                    "UPDATE watchlist SET last_changed = ? WHERE ioc_value = ? AND user_id = ?",
                    (now, ioc_value, user_id),
                )
                changed_users.append(user_id)

        # Record history
        if rows:
            old_risk = rows[0][1]
            self._conn.execute(
                "INSERT INTO watch_history (ioc_value, risk_before, risk_after, summary, detail, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (ioc_value, old_risk, new_risk, summary, detail, now),
            )

        self._conn.commit()
        return changed_users

    def get_history(self, ioc_value: str, limit: int = 20) -> list[dict]:
        """Get risk change history for an IOC."""
        rows = self._conn.execute(
            "SELECT risk_before, risk_after, summary, detail, timestamp FROM watch_history WHERE ioc_value = ? ORDER BY timestamp DESC LIMIT ?",
            (ioc_value, limit),
        ).fetchall()
        return [
            {"risk_before": r[0], "risk_after": r[1], "summary": r[2], "detail": r[3], "timestamp": r[4]}
            for r in rows
        ]

    # -- Notifications --

    def create_notification(self, user_id: str, title: str, body: str, type: str = "watch_alert", ioc_value: str | None = None, conversation_id: str | None = None) -> int:
        """Create a notification for a user. Returns notification ID."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "INSERT INTO notifications (user_id, type, title, body, ioc_value, conversation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, type, title, body, ioc_value, conversation_id, now),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_notifications(self, user_id: str, unread_only: bool = False) -> list[dict]:
        """Get notifications for a user."""
        query = "SELECT id, type, title, body, ioc_value, conversation_id, read, created_at FROM notifications WHERE user_id = ?"
        params = [user_id]
        if unread_only:
            query += " AND read = 0"
        query += " ORDER BY created_at DESC LIMIT 50"

        rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "id": r[0], "type": r[1], "title": r[2], "body": r[3],
                "ioc_value": r[4], "conversation_id": r[5], "read": bool(r[6]),
                "created_at": r[7],
            }
            for r in rows
        ]

    def unread_count(self, user_id: str) -> int:
        """Get count of unread notifications."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read = 0",
            (user_id,),
        ).fetchone()
        return row[0] if row else 0

    def mark_read(self, notification_id: int, user_id: str) -> None:
        """Mark a notification as read."""
        self._conn.execute(
            "UPDATE notifications SET read = 1 WHERE id = ? AND user_id = ?",
            (notification_id, user_id),
        )
        self._conn.commit()

    def mark_all_read(self, user_id: str) -> None:
        """Mark all notifications as read for a user."""
        self._conn.execute(
            "UPDATE notifications SET read = 1 WHERE user_id = ? AND read = 0",
            (user_id,),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
