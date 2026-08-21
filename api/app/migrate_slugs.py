"""One-shot submission/draft slug migration for the cutover rename.

Submissions and drafts are keyed by problem slug. The default problem
tree is now the adapted set (problems/), whose slugs differ from the
LeetCode-derived originals the site has served until now. This script
rewrites every stored slug through problems/MAPPING.json, so a user's
history follows them to the same problem under its new name.

Idempotent: slugs with no mapping entry are left untouched (they are
either already migrated or belong to a problem that kept its slug).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def migrate(database_path: str, mapping_path: str) -> dict[str, int]:
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    slug_map = {
        source.split("_", 1)[1]: entry["adapted"].split("_", 1)[1]
        for source, entry in mapping.items()
    }
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        changed = {"submissions": 0, "drafts": 0}
        for table, key in (("submissions", "problem_slug"), ("drafts", "problem_slug")):
            rows = connection.execute(f"SELECT DISTINCT {key} FROM {table}").fetchall()
            for row in rows:
                slug = row[key]
                target = slug_map.get(slug)
                if target is None or target == slug:
                    continue
                connection.execute(
                    f"UPDATE {table} SET {key} = ? WHERE {key} = ?",
                    (target, slug),
                )
                changed[table] += 1
        connection.commit()
        return changed
    finally:
        connection.close()


if __name__ == "__main__":
    import os

    database = os.environ.get("OPENOJ_DB", "/data/openoj.db")
    mapping = os.environ.get(
        "OPENOJ_MAPPING",
        "/cache/problems/current/problems/MAPPING.json",
    )
    result = migrate(database, mapping)
    print(
        f"migrated {result['submissions']} submission slugs, "
        f"{result['drafts']} draft slugs"
    )
