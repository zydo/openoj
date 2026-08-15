from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from .database import get_submission, initialize_database, list_submissions, save_submission
from .judge import RunnerUnavailable, execute
from .models import RunRequest, SubmitRequest
from .problems import (
    ProblemError,
    list_problems,
    load_all_cases,
    load_problem,
    load_reference_solution,
    public_problem,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="OpenOJ API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/problems")
def problems(page: int = 1, page_size: int = 0) -> dict[str, Any]:
    """List problems, optionally paginated.

    Without query params the full list is returned in a single page (the
    editor needs the whole ordering for prev/next and the drawer). With
    page_size set, only that page's items come back so the landing page's
    load stays small."""
    items = list_problems()
    total = len(items)
    if page_size <= 0:
        return {
            "items": items,
            "total": total,
            "page": 1,
            "page_size": total,
            "pages": 1 if total else 0,
        }
    page_size = min(page_size, 500)
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, pages))
    start = (page - 1) * page_size
    return {
        "items": items[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


@app.get("/problems/{slug}")
def problem(slug: str) -> dict[str, Any]:
    try:
        return public_problem(load_problem(slug))
    except (ProblemError, OSError, ValueError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


def _validate_language(problem_data: dict[str, Any], language: str) -> None:
    config = problem_data.get("languages", {}).get(language)
    if config is None:
        raise HTTPException(status_code=400, detail="Language is not available for this problem")
    if not config.get("enabled", False):
        raise HTTPException(status_code=400, detail="Language runner is not enabled yet")


def _run_judge(
    problem_data: dict[str, Any], language: str, code: str, cases: list[dict[str, Any]], public_count: int
) -> list[dict[str, Any]]:
    _validate_language(problem_data, language)
    try:
        return execute(code, language, problem_data["invocation"], problem_data["limits"], cases, public_count)
    except RunnerUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/run")
def run(request: RunRequest) -> dict[str, Any]:
    try:
        problem_data = load_problem(request.slug)
    except ProblemError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    canonical = problem_data["public_cases"]
    if request.cases is None:
        cases = canonical
    else:
        cases = []
        invocation = problem_data["invocation"]
        for index, custom_input in enumerate(request.cases):
            if invocation.get("type", "function") == "function":
                try:
                    wire_input = [custom_input[parameter["name"]] for parameter in invocation["parameters"]]
                except KeyError as error:
                    raise HTTPException(status_code=400, detail=f"Missing testcase argument: {error.args[0]}") from error
            else:
                wire_input = custom_input
            matched = next((case for case in canonical if case["input"] == wire_input), None)
            if matched is None:
                # Custom cases execute without an assertion; their actual value is returned.
                cases.append({"name": f"Custom case {index + 1}", "input": wire_input, "expected": None, "custom": True})
            else:
                cases.append(matched)

    results = _run_judge(problem_data, request.language, request.code, cases, len(cases))
    for case, result in zip(cases, results, strict=True):
        if case.get("custom") and result["status"] in {"wrong_answer", "accepted"}:
            result["status"] = "completed"
            result.pop("expected", None)
    return _summarize(results)


def _reference_runtime_ms(
    request: SubmitRequest,
    problem_data: dict[str, Any],
    cases: list[dict[str, Any]],
    public_count: int,
    accepted: bool,
) -> int | None:
    """Run the bundle's reference solution and return its total runtime.

    A hardware-independent baseline: both runs share the same container,
    executor calibration, and cases, so the ratio of the user's total to this
    total is meaningful even though absolute times vary by host. Best-effort —
    absent references, unavailable runners, or a failing reference simply
    yield None and the UI omits the comparison."""
    if not accepted:
        return None
    try:
        reference = load_reference_solution(request.slug, request.language)
    except (ProblemError, OSError):
        return None
    if reference is None:
        return None
    try:
        results = _run_judge(problem_data, request.language, reference, cases, public_count)
    except HTTPException:
        return None
    if any(result["status"] not in {"accepted", "completed"} for result in results):
        return None
    return sum(result.get("runtime_ms", result.get("_runtime_ms", 0)) for result in results)


@app.post("/submit")
def submit(request: SubmitRequest) -> dict[str, Any]:
    try:
        problem_data = load_problem(request.slug)
        cases, public_count = load_all_cases(request.slug)
    except ProblemError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    results = _run_judge(problem_data, request.language, request.code, cases, public_count)
    summary = _summarize(results)
    summary["reference_runtime_ms"] = _reference_runtime_ms(
        request, problem_data, cases, public_count, summary["status"] == "accepted"
    )
    submission_id = save_submission(
        request.slug,
        request.language,
        request.code,
        summary["status"],
        summary["passed"],
        summary["total"],
        summary["runtime_ms"],
        results,
    )
    summary["submission_id"] = submission_id
    return summary


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(result["status"] in {"accepted", "completed"} for result in results)
    runtime_ms = sum(result.get("runtime_ms", result.get("_runtime_ms", 0)) for result in results)
    for result in results:
        result.pop("_runtime_ms", None)
    status = "accepted" if passed == len(results) else next(
        (result["status"] for result in results if result["status"] not in {"accepted", "completed"}),
        "wrong_answer",
    )
    return {
        "status": status,
        "passed": passed,
        "total": len(results),
        "runtime_ms": runtime_ms,
        "results": results,
    }


@app.get("/submissions")
def submissions(slug: str = Query(min_length=1), limit: int = Query(default=30, ge=1, le=100)):
    return list_submissions(slug, limit)


@app.get("/submissions/{submission_id}")
def submission(submission_id: int):
    result = get_submission(submission_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    return result
