import json
import os
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any


QUEUE_DIR = Path(os.environ.get("OPENOJ_QUEUE_DIR", ".queue"))
RUNNER_TIMEOUT = float(os.environ.get("OPENOJ_RUNNER_TIMEOUT_SECONDS", "20"))


class RunnerUnavailable(RuntimeError):
    pass


def _compare(actual: Any, expected: Any, comparison: str) -> bool:
    if comparison == "exact":
        return actual == expected
    if comparison in {"sorted", "multiset", "set"}:
        if not isinstance(actual, list) or not isinstance(expected, list):
            return False
        normalize = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"))
        normalized_actual = list(map(normalize, actual))
        normalized_expected = list(map(normalize, expected))
        if comparison == "sorted":
            return sorted(normalized_actual) == sorted(normalized_expected)
        if comparison == "multiset":
            return Counter(normalized_actual) == Counter(normalized_expected)
        return set(normalized_actual) == set(normalized_expected)
    raise ValueError(f"Unsupported comparison: {comparison}")


def _display_input(invocation: dict[str, Any], raw_input: Any) -> Any:
    if invocation.get("type", "function") == "function" and isinstance(raw_input, list):
        names = [parameter["name"] for parameter in invocation.get("parameters", [])]
        return dict(zip(names, raw_input))
    return raw_input


def execute(
    code: str,
    language: str,
    invocation: dict[str, Any],
    limits: dict[str, Any],
    cases: list[dict[str, Any]],
    public_count: int,
) -> list[dict[str, Any]]:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    if not os.access(QUEUE_DIR, os.R_OK | os.W_OK | os.X_OK):
        raise RunnerUnavailable("The isolated judge queue is not accessible")
    job_id = uuid.uuid4().hex
    job_dir = QUEUE_DIR / job_id
    job_dir.mkdir(mode=0o770)
    job_dir.chmod(0o770)
    request_path = job_dir / "request.json"
    ready_path = job_dir / "ready"
    result_path = job_dir / "result.json"
    request = {
        "version": 2,
        "job_id": job_id,
        "language": language,
        "code": code,
        "invocation": invocation,
        "limits": limits,
        # Expected values deliberately remain in the API trust boundary.
        "cases": [{"input": case["input"]} for case in cases],
    }
    request_path.write_text(json.dumps(request), encoding="utf-8")
    ready_path.touch(mode=0o600)

    deadline = time.monotonic() + RUNNER_TIMEOUT
    try:
        while time.monotonic() < deadline:
            if result_path.exists():
                raw_results = json.loads(result_path.read_text(encoding="utf-8"))["results"]
                break
            time.sleep(0.025)
        else:
            raise RunnerUnavailable("The isolated runner did not respond in time")
    finally:
        for path in (ready_path, request_path, result_path):
            path.unlink(missing_ok=True)
        try:
            job_dir.rmdir()
        except OSError:
            pass

    comparison = invocation.get("comparison", "exact")
    results = []
    if len(raw_results) < len(cases):
        raw_results.extend(
            {"status": "system_error", "error": "Runner returned an incomplete result", "runtime_ms": 0}
            for _ in range(len(cases) - len(raw_results))
        )
    for index, (case, raw) in enumerate(zip(cases, raw_results)):
        visible = index < public_count
        status = raw["status"]
        passed = status == "completed" and _compare(raw.get("actual"), case["expected"], comparison)
        result = {
            "index": index,
            "name": case.get("name", f"Case {index + 1}") if visible else f"Hidden case {index - public_count + 1}",
            "status": "accepted" if passed else ("wrong_answer" if status == "completed" else status),
        }
        if visible:
            result.update({
                "runtime_ms": raw.get("runtime_ms", 0),
                "timeout_ms": raw.get("timeout_ms"),
                "input": _display_input(invocation, case["input"]),
                "expected": case["expected"],
                "actual": raw.get("actual"),
                "stdout": raw.get("stdout", ""),
                "error": raw.get("error"),
            })
        else:
            # Keep the duration private long enough to form an honest aggregate,
            # then remove it in _summarize before results cross the API boundary.
            result["_runtime_ms"] = raw.get("runtime_ms", 0)
            if status not in {"completed"}:
                hidden_errors = {
                    "runtime_error": "Solution raised an error on a hidden testcase",
                    "time_limit_exceeded": "Solution exceeded the calibrated deadline on a hidden testcase",
                    "memory_limit_exceeded": "Solution exceeded the memory limit on a hidden testcase",
                    "skipped": "Testcase was not run after an earlier execution failure",
                }
                result["error"] = hidden_errors.get(status, "Execution failed on a hidden testcase")
        results.append(result)
    return results
