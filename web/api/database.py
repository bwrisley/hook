"""
web/api/database.py -- Database abstraction for Shadowbox.

Supports SQLite (dev/local) and PostgreSQL (production).
Selected by DATABASE_URL environment variable:
  - Not set or sqlite:///path -> SQLite
  - postgresql://... -> PostgreSQL
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Any


def get_db_url() -> str:
    """Get database URL from environment."""
    return os.environ.get("DATABASE_URL", "")


def is_postgres() -> bool:
    """Check if PostgreSQL is configured."""
    return get_db_url().startswith("postgresql")


class Database:
    """Unified database interface for SQLite and PostgreSQL."""

    def __init__(self, db_url: str = "") -> None:
        self._url = db_url or get_db_url()
        self._pg_pool = None
        self._sqlite_conn = None

        if is_postgres():
            self._init_postgres()
        else:
            self._init_sqlite()

    def _init_sqlite(self) -> None:
        """Initialize SQLite connection."""
        from pathlib import Path
        db_path = self._url.replace("sqlite:///", "") if self._url else "data/hook-web.db"
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._sqlite_conn = sqlite3.connect(db_path, check_same_thread=False)

    def _init_postgres(self) -> None:
        """Initialize PostgreSQL connection pool."""
        import psycopg2
        from psycopg2 import pool
        self._pg_pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=self._url,
        )

    def execute(self, sql: str, params: tuple = ()) -> None:
        """Execute a write query."""
        if self._pg_pool:
            conn = self._pg_pool.getconn()
            try:
                with conn.cursor() as cur:
                    # Convert SQLite syntax to PostgreSQL
                    sql = self._adapt_sql(sql)
                    cur.execute(sql, params)
                conn.commit()
            finally:
                self._pg_pool.putconn(conn)
        else:
            self._sqlite_conn.execute(sql, params)
            self._sqlite_conn.commit()

    def execute_returning(self, sql: str, params: tuple = ()) -> int:
        """Execute an INSERT and return lastrowid."""
        if self._pg_pool:
            conn = self._pg_pool.getconn()
            try:
                with conn.cursor() as cur:
                    sql = self._adapt_sql(sql)
                    if "INSERT" in sql.upper() and "RETURNING" not in sql.upper():
                        sql = sql.rstrip(";") + " RETURNING id"
                    cur.execute(sql, params)
                    row = cur.fetchone()
                    conn.commit()
                    return row[0] if row else 0
            finally:
                self._pg_pool.putconn(conn)
        else:
            cursor = self._sqlite_conn.execute(sql, params)
            self._sqlite_conn.commit()
            return cursor.lastrowid

    def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        """Execute a read query and return all rows."""
        if self._pg_pool:
            conn = self._pg_pool.getconn()
            try:
                with conn.cursor() as cur:
                    sql = self._adapt_sql(sql)
                    cur.execute(sql, params)
                    return cur.fetchall()
            finally:
                self._pg_pool.putconn(conn)
        else:
            return self._sqlite_conn.execute(sql, params).fetchall()

    def fetchone(self, sql: str, params: tuple = ()) -> tuple | None:
        """Execute a read query and return one row."""
        if self._pg_pool:
            conn = self._pg_pool.getconn()
            try:
                with conn.cursor() as cur:
                    sql = self._adapt_sql(sql)
                    cur.execute(sql, params)
                    return cur.fetchone()
            finally:
                self._pg_pool.putconn(conn)
        else:
            return self._sqlite_conn.execute(sql, params).fetchone()

    def _adapt_sql(self, sql: str) -> str:
        """Adapt SQLite SQL to PostgreSQL syntax."""
        # AUTOINCREMENT -> SERIAL (handled in CREATE TABLE)
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        # Boolean: INTEGER -> BOOLEAN
        sql = sql.replace("INTEGER DEFAULT 0", "BOOLEAN DEFAULT FALSE")
        sql = sql.replace("INTEGER DEFAULT 1", "BOOLEAN DEFAULT TRUE")
        # datetime('now', ...) -> NOW() - INTERVAL
        sql = sql.replace("datetime('now', '-7 days')", "NOW() - INTERVAL '7 days'")
        return sql

    def close(self) -> None:
        """Close connections."""
        if self._pg_pool:
            self._pg_pool.closeall()
        if self._sqlite_conn:
            self._sqlite_conn.close()
