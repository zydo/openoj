import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


DATA_DIR = Path(os.environ.get("OPENOJ_DATA_DIR", ".data"))
DATABASE_PATH = DATA_DIR / "openoj.sqlite3"


def initialize_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
) -> int:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO submissions
                (problem_slug, language, code, status, passed, total, runtime_ms, results_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (slug, language, code, status, passed, total, runtime_ms, json.dumps(results)),
        )
        return int(cursor.lastrowid)


def list_submissions(slug: str, limit: int = 50) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, problem_slug, language, status, passed, total, runtime_ms, created_at
            FROM submissions WHERE problem_slug = ? ORDER BY id DESC LIMIT ?
            """,
            (slug, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_submission(submission_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["results"] = json.loads(result.pop("results_json"))
    return result

