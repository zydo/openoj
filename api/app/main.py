import time
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response

from .database import (
    SESSION_IDLE_SECONDS,
    bind_session_user,
    count_users,
    create_session,
    create_user,
    get_submission,
    initialize_database,
    list_drafts,
    list_submissions,
    purge_expired_sessions,
    save_draft,
    save_submission,
    scope_key,
    session_user,
    validate_session,
    verify_user,
)
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

SESSION_COOKIE = "openoj_session"


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    purge_expired_sessions()
    yield


app = FastAPI(title="OpenOJ API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def current_session(openoj_session: Annotated[str | None, Cookie()] = None) -> str:
    """Require an active guest session; 401 otherwise (the frontend then
    shows the Continue-as-guest entrance)."""
    if openoj_session and validate_session(openoj_session):
        return openoj_session
    raise HTTPException(status_code=401, detail="No active session")


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=SESSION_IDLE_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
    )


@app.post("/session")
def start_session(response: Response) -> dict[str, Any]:
    session_id = create_session()
    purge_expired_sessions()
    _set_session_cookie(response, session_id)
    return {"status": "active", "idle_seconds": SESSION_IDLE_SECONDS}


@app.get("/session")
def session_status(session_id: Annotated[str, Depends(current_session)]) -> dict[str, Any]:
    user = session_user(session_id)
    return {
        "status": "active",
        "idle_seconds": SESSION_IDLE_SECONDS,
        "user": None if user is None else {"username": user["username"], "is_admin": user["is_admin"]},
    }


# --- user accounts (backend-only; the UI stays guest-only for now) -----------
# Fresh-start bootstrap: the very first account must be the fixed-name admin;
# afterwards registration is closed until the accounts UI ships.

# Minimal in-memory login throttle: per source, allow 10 failures per minute.
_LOGIN_WINDOW_SECONDS = 60.0
_LOGIN_MAX_FAILURES = 10
_login_failures: dict[str, list[float]] = {}


def _register_login_failure(source: str) -> bool:
    """Record a failure; returns False when the source is throttled."""
    now = time.monotonic()
    recent = [stamp for stamp in _login_failures.get(source, []) if now - stamp < _LOGIN_WINDOW_SECONDS]
    if len(recent) >= _LOGIN_MAX_FAILURES:
        _login_failures[source] = recent
        return False
    recent.append(now)
    _login_failures[source] = recent
    return True


@app.post("/auth/register")
def auth_register(
    body: dict[str, str],
    response: Response,
) -> dict[str, Any]:
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if count_users() == 0:
        if username != "admin":
            raise HTTPException(status_code=400, detail="The first account must be the admin (username 'admin')")
    else:
        raise HTTPException(status_code=403, detail="Registration is not open yet")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    try:
        create_user(username, password, is_admin=True)
    except Exception:  # noqa: BLE001 — username uniqueness races
        raise HTTPException(status_code=400, detail="That username is not available")
    _set_session_cookie(response, create_session())
    return {"status": "registered", "username": username}


@app.post("/auth/login")
def auth_login(
    body: dict[str, str],
    request: Request,
    session_id: Annotated[str, Depends(current_session)],
) -> dict[str, Any]:
    source = request.client.host if request.client else "unknown"
    user = verify_user(body.get("username", ""), body.get("password", ""))
    if user is None:
        if not _register_login_failure(source):
            raise HTTPException(status_code=429, detail="Too many failed attempts; wait a minute")
        raise HTTPException(status_code=401, detail="Invalid username or password")
    bind_session_user(session_id, user["id"])
    return {"status": "logged_in", "username": user["username"], "is_admin": user["is_admin"]}


@app.post("/auth/logout")
def auth_logout(session_id: Annotated[str, Depends(current_session)]) -> dict[str, Any]:
    bind_session_user(session_id, None)
    return {"status": "logged_out"}


@app.get("/drafts/{slug}")
def drafts(slug: str, session_id: Annotated[str, Depends(current_session)]) -> list[dict[str, Any]]:
    return list_drafts(scope_key(session_id), slug)


@app.put("/drafts/{slug}/{language}")
def put_draft(
    slug: str,
    language: str,
    body: dict[str, str],
    session_id: Annotated[str, Depends(current_session)],
) -> dict[str, str]:
    code = body.get("code", "")
    if len(code) > 256_000:
        raise HTTPException(status_code=400, detail="Draft too large")
    save_draft(scope_key(session_id), slug, language, code)
    return {"status": "saved"}


@app.get("/problems")
def problems(
    page: int = 1,
    page_size: int = 0,
    session_id: Annotated[str, Depends(current_session)] = None,
) -> dict[str, Any]:
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
def problem(slug: str, session_id: Annotated[str, Depends(current_session)] = None) -> dict[str, Any]:
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
def run(request: RunRequest, session_id: Annotated[str, Depends(current_session)] = None) -> dict[str, Any]:
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
def submit(request: SubmitRequest, session_id: Annotated[str, Depends(current_session)] = None) -> dict[str, Any]:
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
        scope_key(session_id),
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
def submissions(
    slug: str = Query(min_length=1),
    limit: int = Query(default=30, ge=1, le=100),
    session_id: Annotated[str, Depends(current_session)] = None,
):
    return list_submissions(slug, limit, scope_key(session_id))


@app.get("/submissions/{submission_id}")
def submission(submission_id: int, session_id: Annotated[str, Depends(current_session)] = None):
    result = get_submission(submission_id, scope_key(session_id))
    if result is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    return result
