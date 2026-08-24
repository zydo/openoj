import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "/runner")

from leetcode_types import emit_protocol

PROTOCOL_PREFIX = "__OPENOJ_RESULT__"
MAX_CAPTURED_OUTPUT = 16_384


def _json_safe_rows(rows) -> list:
    safe = []
    for row in rows:
        values = []
        for value in row:
            if isinstance(value, bytes):
                raise ValueError("BLOB columns are not supported")
            if isinstance(value, float) and value != value:
                raise ValueError("NaN is not a valid SQL result value")
            values.append(value)
        safe.append(values)
    return safe


def main() -> None:
    response: dict
    try:
        payload = json.load(sys.stdin)
        invocation = payload["invocation"]
        case_setup = payload["input"][0] if payload.get("input") else ""
        schema = invocation.get("sql", {}).get("schema", "")
        connection = sqlite3.connect(":memory:")
        if schema.strip():
            connection.executescript(schema)
        if case_setup.strip():
            connection.executescript(case_setup)
        argv = sys.argv[1:]
        if "--" in argv:
            argv = argv[argv.index("--") + 1 :]
        query = Path(argv[0]).read_text(encoding="utf-8")
        # The submission is a single SELECT whose row set is the answer.
        cursor = connection.execute(f"SELECT * FROM ({query})")
        rows = cursor.fetchall()
        response = {"status": "completed", "actual": _json_safe_rows(rows), "stdout": ""}
    except sqlite3.Error as error:
        response = {
            "status": "runtime_error",
            "error": f"SQL error: {error}"[:1000],
            "stdout": "",
        }
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            error = RuntimeError("Solution interrupted execution")
        response = {
            "status": "runtime_error",
            "error": f"{type(error).__name__}: {error}"[:1000],
            "stdout": "",
        }
    emit_protocol(PROTOCOL_PREFIX + json.dumps(response, allow_nan=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
