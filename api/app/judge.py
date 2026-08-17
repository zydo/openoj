import json
import math
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


DEFAULT_CLOSE_TOLERANCE = 1e-9


def _close_enough(actual: Any, expected: Any, tolerance: float) -> bool:
    """Per-scalar tolerant comparison: numbers may differ by the given
    relative (and absolute) tolerance; structure must match exactly."""
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance)
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _close_enough(a, e, tolerance) for a, e in zip(actual, expected)
        )
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _close_enough(actual[key], expected[key], tolerance) for key in actual
        )
    return actual == expected


def _distribution_ok(actual: Any, spec: dict[str, Any]) -> bool:
    """Statistical judging for randomized methods (LeetCode semantics).

    The harness reports a frequency table {canonical value: count} over
    `repeat` draws; the case carries the expected distribution as
    {"mode": "distribution", "repeat": K, "tolerance": t,
     "probabilities": {canonical: p}}. Every observed value must be valid
    (a known key), the total must be K, and each bucket with enough
    expected mass must land within the relative tolerance band. Small
    buckets merge into one tail bucket so rare outcomes cannot flake."""
    if not isinstance(actual, dict):
        return False
    repeat = int(spec.get("repeat", 0))
    tolerance = float(spec.get("tolerance", 0.10))
    probabilities = spec.get("probabilities")
    if repeat <= 0 or not isinstance(probabilities, dict):
        return False
    if sum(actual.values()) != repeat:
        return False
    if any(key not in probabilities for key in actual):
        return False
    min_bucket = 10.0
    tail_expected = 0.0
    tail_actual = 0
    for key, probability in probabilities.items():
        expected_count = float(probability) * repeat
        actual_count = actual.get(key, 0)
        if expected_count >= min_bucket:
            # The band is the wider of the relative tolerance and 3.5
            # binomial standard deviations, so a correct sampler never
            # flakes while a genuinely biased one still fails.
            sigma = math.sqrt(expected_count * (1.0 - float(probability)))
            band = max(tolerance * expected_count, 3.5 * sigma)
            if abs(actual_count - expected_count) > band:
                return False
        else:
            tail_expected += expected_count
            tail_actual += actual_count
    if tail_expected > 0 or tail_actual > 0:
        if abs(tail_actual - tail_expected) > max(tolerance * tail_expected, min_bucket):
            return False
    return True


def _compare(actual: Any, expected: Any, comparison: Any) -> bool:
    # Design outputs are per-action lists; a statistical action's expected
    # element is a distribution spec compared against the harness frequency
    # table while every other element stays exact.
    if isinstance(expected, list) and any(
        isinstance(element, dict) and element.get("mode") in {"distribution", "any_of", "opaque"}
        for element in expected
    ):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_compare(a, e, "exact") for a, e in zip(actual, expected))
        )
    if isinstance(expected, dict) and expected.get("mode") == "distribution":
        return _distribution_ok(actual, expected)
    # {"mode": "any_of", "values": [...]} accepts any listed answer, the way
    # LeetCode accepts either key when two share the extreme count.
    if isinstance(expected, dict) and expected.get("mode") == "any_of":
        return any(_compare(actual, candidate, comparison) for candidate in expected.get("values", []))
    # {"mode": "opaque"} accepts any value: the slot is an intermediate whose
    # format the problem deliberately leaves free (a serialize call whose
    # output only has to round-trip back through deserialize).
    if isinstance(expected, dict) and expected.get("mode") == "opaque":
        return True
    if comparison == "exact":
        return actual == expected
    if comparison == "close" or (
        isinstance(comparison, dict) and comparison.get("mode") == "close"
    ):
        tolerance = (
            float(comparison.get("tolerance", DEFAULT_CLOSE_TOLERANCE))
            if isinstance(comparison, dict)
            else DEFAULT_CLOSE_TOLERANCE
        )
        return _close_enough(actual, expected, tolerance)
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
