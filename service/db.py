"""SQLite storage for API keys and usage. Zero-infra v1."""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.environ.get("VOXPOP_DB", "voxpop.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS keys (
    key_hash    TEXT PRIMARY KEY,
    key_prefix  TEXT NOT NULL,
    email       TEXT NOT NULL,
    plan        TEXT NOT NULL DEFAULT 'free',
    quota       INTEGER NOT NULL DEFAULT 100,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    key_hash TEXT NOT NULL,
    period   TEXT NOT NULL,
    count    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (key_hash, period)
);
CREATE INDEX IF NOT EXISTS idx_keys_email ON keys(email);
"""

PLANS = {"free": 100, "pro": 10_000, "team": 100_000}


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def current_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def issue_key(email: str, plan: str = "free") -> str:
    """Generate a key, store only its hash, return the raw key once."""
    raw = f"vp_live_{secrets.token_urlsafe(24)}"
    with conn() as c:
        c.execute(
            "INSERT INTO keys (key_hash, key_prefix, email, plan, quota, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (
                hash_key(raw),
                raw[:16],
                email,
                plan,
                PLANS.get(plan, 100),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return raw


def set_plan(email: str, plan: str) -> int:
    """Upgrade/downgrade every active key for an email. Returns rows changed."""
    with conn() as c:
        cur = c.execute(
            "UPDATE keys SET plan=?, quota=? WHERE email=? AND active=1",
            (plan, PLANS.get(plan, 100), email),
        )
        return cur.rowcount


def deactivate(email: str) -> int:
    with conn() as c:
        cur = c.execute("UPDATE keys SET active=0 WHERE email=?", (email,))
        return cur.rowcount


def lookup(raw: str) -> sqlite3.Row | None:
    with conn() as c:
        return c.execute(
            "SELECT * FROM keys WHERE key_hash=? AND active=1", (hash_key(raw),)
        ).fetchone()


def consume(key_hash: str, quota: int) -> tuple[bool, int]:
    """Atomically increment usage. Returns (allowed, used_after)."""
    period = current_period()
    with conn() as c:
        c.execute(
            "INSERT INTO usage (key_hash, period, count) VALUES (?,?,0)"
            " ON CONFLICT(key_hash, period) DO NOTHING",
            (key_hash, period),
        )
        row = c.execute(
            "SELECT count FROM usage WHERE key_hash=? AND period=?", (key_hash, period)
        ).fetchone()
        used = row["count"]
        if used >= quota:
            return False, used
        c.execute(
            "UPDATE usage SET count=count+1 WHERE key_hash=? AND period=?",
            (key_hash, period),
        )
        return True, used + 1


def usage_for(key_hash: str) -> int:
    with conn() as c:
        row = c.execute(
            "SELECT count FROM usage WHERE key_hash=? AND period=?",
            (key_hash, current_period()),
        ).fetchone()
        return row["count"] if row else 0
