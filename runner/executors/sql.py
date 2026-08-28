import json
from pathlib import Path
from typing import Any

from .base import ExecutorError, PreparedProgram
from .python3 import Python3Executor


class SqlExecutor(Python3Executor):
    """SQLite SELECT-query executor sharing the Python runtime plugin."""

    language = "sql"
    harness_path = Path("/runner/sql_harness.py")

    def prepare(
        self,
        job_root: Path,
        scratch: Path,
        code: str,
        invocation: dict[str, Any],
        limits: dict[str, Any],
        assembly: dict[str, dict[str, str]] | None = None,
    ) -> PreparedProgram:
        invocation_sql = invocation.get("sql") or {}
        if not invocation_sql.get("dynamic_columns"):
            stripped = code.strip().rstrip(";").strip()
            if ";" in stripped:
                raise ExecutorError("SQL submissions must be a single SELECT statement")
        return super().prepare(job_root, scratch, code, invocation, limits, assembly)

    def encode_case(
        self, invocation: dict[str, Any], case_input: Any, limits: dict[str, Any] | None = None
    ) -> bytes:
        payload: dict[str, Any] = {"invocation": invocation, "input": case_input}
        if limits is not None:
            payload["limits"] = {"output_kb": int(limits.get("output_kb", 64))}
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
