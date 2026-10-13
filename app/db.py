"""Tiny SQLite job store (lives on the Railway volume so it survives redeploys)."""
import json
import sqlite3
import threading
import time

from . import config

_lock = threading.Lock()

STATUSES = ("queued", "processing", "waiting_approval", "approved", "posted", "rejected", "failed")


def _conn():
    c = sqlite3.connect(config.DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, _conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drive_file_id TEXT UNIQUE,
            name TEXT,
            product_link TEXT,
            status TEXT,
            script_json TEXT,
            output_path TEXT,
            output_drive_id TEXT,
            tg_message_id INTEGER,
            fb_post_id TEXT,
            rewrite_note TEXT,
            error TEXT,
            attempts INTEGER DEFAULT 0,
            created_at REAL,
            updated_at REAL
        )""")


def create(drive_file_id, name, product_link):
    now = time.time()
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO jobs (drive_file_id, name, product_link, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'queued', ?, ?)", (drive_file_id, name, product_link, now, now))
        return cur.lastrowid if cur.rowcount else None


def exists(drive_file_id):
    with _lock, _conn() as c:
        return c.execute("SELECT 1 FROM jobs WHERE drive_file_id=?", (drive_file_id,)).fetchone() is not None


def get(job_id):
    with _lock, _conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(r) if r else None


def by_message(msg_id):
    with _lock, _conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE tg_message_id=?", (msg_id,)).fetchone()
        return dict(r) if r else None


def next_queued():
    with _lock, _conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
        return dict(r) if r else None


def update(job_id, **fields):
    if "script" in fields:
        fields["script_json"] = json.dumps(fields.pop("script"), ensure_ascii=False)
    fields["updated_at"] = time.time()
    keys = ", ".join(f"{k}=?" for k in fields)
    with _lock, _conn() as c:
        c.execute(f"UPDATE jobs SET {keys} WHERE id=?", (*fields.values(), job_id))


def counts():
    with _lock, _conn() as c:
        return {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")}


def reset_stuck():
    """Jobs left in 'processing' after a crash/redeploy go back to the queue."""
    with _lock, _conn() as c:
        c.execute("UPDATE jobs SET status='queued' WHERE status='processing'")
