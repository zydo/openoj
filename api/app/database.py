import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


DATA_DIR = Path(os.environ.get("OPENOJ_DATA_DIR", ".data"))
DATABASE_PATH = DATA_DIR / "openoj.sqlite3"

# Guest sessions expire after this much inactivity (seconds); everything the
# session owns — drafts and submissions — is deleted with it.
SESSION_IDLE_SECONDS = 3600


def initialize_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                problem_slug TEXT NOT NULL,
                language TEXT NOT NULL,
                code TEXT NOT NULL,
                status TEXT NOT NULL,
                passed INTEGER NOT NULL,
                total INTEGER NOT NULL,
                runtime_ms INTEGER NOT NULL,
                results_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                last_seen_at REAL NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                session_id TEXT NOT NULL,
                problem_slug TEXT NOT NULL,
                language TEXT NOT NULL,
                code TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (session_id, problem_slug, language)
            )
            """
        )
        # Databases created before guest sessions have no session_id column.
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(submissions)")}
        if "session_id" not in columns:
            connection.execute("ALTER TABLE submissions ADD COLUMN session_id TEXT")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def save_submission(
    slug: str,
    language: str,
    code: str,
    status: str,
    passed: int,
    total: int,
    runtime_ms: int,
    results: list[dict[str, Any]],
    session_id: str | None = None,
) -> int:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO submissions
                (session_id, problem_slug, language, code, status, passed, total, runtime_ms, results_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, slug, language, code, status, passed, total, runtime_ms, json.dumps(results)),
        )
        return int(cursor.lastrowid)


def list_submissions(
    slug: str, limit: int = 50, session_id: str | None = None
) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, problem_slug, language, status, passed, total, runtime_ms, created_at
            FROM submissions
            WHERE problem_slug = ? AND session_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (slug, session_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_submission(submission_id: int, session_id: str | None = None) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM submissions WHERE id = ? AND session_id = ?",
            (submission_id, session_id),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["results"] = json.loads(result.pop("results_json"))
    return result


# --- guest sessions -----------------------------------------------------------


def _purge_session(connection: sqlite3.Connection, session_id: str) -> None:
    connection.execute("DELETE FROM drafts WHERE session_id = ?", (session_id,))
    connection.execute("DELETE FROM submissions WHERE session_id = ?", (session_id,))
    connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def purge_expired_sessions() -> int:
    """Delete every idle-expired session and everything it owns. Returns the
    number of sessions purged."""
    cutoff = time.time() - SESSION_IDLE_SECONDS
    with connect() as connection:
        expired = [
            row["id"]
            for row in connection.execute("SELECT id FROM sessions WHERE last_seen_at < ?", (cutoff,))
        ]
        for session_id in expired:
            _purge_session(connection, session_id)
    return len(expired)


def create_session() -> str:
    session_id = uuid.uuid4().hex
    now = time.time()
    with connect() as connection:
        connection.execute(
            "INSERT INTO sessions (id, created_at, last_seen_at) VALUES (?, ?, ?)",
            (session_id, now, now),
        )
    return session_id


def validate_session(session_id: str) -> str | None:
    """Return the session id if it exists and is not idle-expired (touching
    its last-seen clock); otherwise None. Expired sessions are purged."""
    now = time.time()
    cutoff = now - SESSION_IDLE_SECONDS
    with connect() as connection:
        row = connection.execute(
            "SELECT last_seen_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        if row["last_seen_at"] < cutoff:
            _purge_session(connection, session_id)
            return None
        connection.execute("UPDATE sessions SET last_seen_at = ? WHERE id = ?", (now, session_id))
    return session_id


# --- session drafts -----------------------------------------------------------


def save_draft(session_id: str, slug: str, language: str, code: str) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO drafts (session_id, problem_slug, language, code, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id, problem_slug, language)
            DO UPDATE SET code = excluded.code, updated_at = excluded.updated_at
            """,
            (session_id, slug, language, code, time.time()),
        )


def list_drafts(session_id: str, slug: str) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT language, code, updated_at FROM drafts
            WHERE session_id = ? AND problem_slug = ?
            ORDER BY updated_at DESC
            """,
            (session_id, slug),
        ).fetchall()
    return [dict(row) for row in rows]

