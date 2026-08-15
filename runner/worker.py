import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any

# Isolated mode intentionally omits the script directory from sys.path. Add
# only the immutable runner image directory so trusted executor plugins remain
# importable without exposing the submission workspace.
sys.path.insert(0, "/runner")

from executors import get_executor, supported_languages
from executors.base import ExecutorError, LanguageExecutor, PreparedProgram
from executors.go import WRAPPER_IMPORTS


QUEUE_DIR = Path(os.environ.get("OPENOJ_QUEUE_DIR", "/queue"))
WORK_DIR = Path(os.environ.get("OPENOJ_WORK_DIR", "/work"))
POLL_INTERVAL = float(os.environ.get("OPENOJ_POLL_INTERVAL", "0.05"))
NOBODY_UID = 65534
NOBODY_GID = 65534
PROTOCOL_PREFIX = "__OPENOJ_RESULT__"
RUNTIME_SANDBOX = "/runner/runtime_sandbox.py"
SUPERVISOR_PYTHON = "/usr/local/bin/openoj-supervisor-python"
CALIBRATION_FACTORS: dict[str, float] = {}


def _sandboxed_runtime_command(
    command: tuple[str, ...],
    limits: dict[str, Any],
    output_bytes: int,
) -> tuple[str, ...]:
    cpu_seconds = max(1, math.ceil(int(limits.get("time_ms", 2000)) / 1000))
    return (
        SUPERVISOR_PYTHON,
        RUNTIME_SANDBOX,
        str(int(limits.get("memory_mb", 256))),
        str(cpu_seconds),
        str(output_bytes),
        str(int(limits.get("processes", 16))),
        *command,
    )


def _parse_protocol(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        if line.startswith(PROTOCOL_PREFIX):
            try:
                data = json.loads(line[len(PROTOCOL_PREFIX):])
                if isinstance(data, dict) and data.get("status") in {"completed", "runtime_error"}:
                    return data
            except json.JSONDecodeError:
                continue
    return {"status": "runtime_error", "error": "Solution did not produce a valid judge response"}


# The judge protocol travels on a dedicated inherited fd so submission code
# cannot forge a verdict by printing the protocol prefix to stdout. Harnesses
# fall back to stdout only when the fd is absent (local authoring tooling).
PROTOCOL_FD = 63


def _kill_lingering_children() -> None:
    """Remove processes a submission attempted to leave behind."""
    for status_path in Path("/proc").glob("[0-9]*/status"):
        try:
            status = status_path.read_text(encoding="utf-8", errors="ignore")
            uid_line = next(line for line in status.splitlines() if line.startswith("Uid:"))
            if int(uid_line.split()[1]) == NOBODY_UID:
                os.kill(int(status_path.parent.name), signal.SIGKILL)
        except (FileNotFoundError, PermissionError, ProcessLookupError, StopIteration, ValueError):
            continue


def _run_case(
    job_root: Path,
    case_input: Any,
    invocation: dict[str, Any],
    limits: dict[str, Any],
    executor: LanguageExecutor,
    program: PreparedProgram,
) -> dict[str, Any]:
    scratch = job_root / "scratch"
    scratch.mkdir(mode=0o700)
    # The capability-minimized supervisor needs execute permission to chdir;
    # only the submission UID retains read/write access.
    scratch.chmod(0o711)
    os.chown(scratch, NOBODY_UID, NOBODY_GID)
    output_limit = int(limits.get("output_kb", 64)) * 1024
    nominal_time_ms = int(limits.get("time_ms", 2000))
    calibrated_time_ms = max(100, round(nominal_time_ms * CALIBRATION_FACTORS[executor.language]))
    effective_limits = {
        **limits,
        "time_ms": calibrated_time_ms,
        # Managed runtimes reserve address space for the VM in addition to the
        # problem's user-memory allowance. The executor declares that overhead.
        "memory_mb": int(limits.get("memory_mb", 256)) + executor.address_space_overhead_mb,
        "processes": executor.max_processes,
    }
    timeout_seconds = calibrated_time_ms / 1000
    if getattr(executor, "encode_case_with_limits", False):
        payload = executor.encode_case(invocation, case_input, limits)
    else:
        payload = executor.encode_case(invocation, case_input)

    with tempfile.TemporaryFile(mode="w+b", dir="/tmp") as output_file, \
            tempfile.TemporaryFile(mode="w+b", dir="/tmp") as protocol_file:
        protocol_fd = protocol_file.fileno()
        channel = os.dup2(protocol_fd, PROTOCOL_FD)
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                _sandboxed_runtime_command(program.command, effective_limits, output_limit),
                cwd=scratch,
                stdin=subprocess.PIPE,
                stdout=output_file,
                stderr=subprocess.STDOUT,
                env=program.environment,
                start_new_session=True,
                pass_fds=(channel,),
            )
            try:
                process.communicate(payload, timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                _kill_lingering_children()
                return {
                    "status": "time_limit_exceeded",
                    "runtime_ms": int((time.monotonic() - started) * 1000),
                    "timeout_ms": calibrated_time_ms,
                }

            runtime_ms = int((time.monotonic() - started) * 1000)
            output_file.seek(0)
            output = output_file.read(output_limit).decode("utf-8", errors="replace")
            protocol_file.seek(0)
            protocol = protocol_file.read(1 << 20).decode("utf-8", errors="replace")
            # Trust the dedicated protocol channel; stdout parsing remains
            # only as the fallback for harnesses that could not use it.
            parsed = _parse_protocol(protocol) if protocol.strip() else _parse_protocol(output)
        finally:
            os.close(channel)
        parsed["runtime_ms"] = runtime_ms
        parsed["timeout_ms"] = calibrated_time_ms
        if process.returncode != 0 and parsed["status"] == "runtime_error" and not parsed.get("error"):
            parsed["error"] = f"{executor.language} exited with status {process.returncode}"
        _kill_lingering_children()
        return parsed


def _process_job(job_dir: Path) -> None:
    request_path = job_dir / "request.json"
    result_path = job_dir / "result.json"
    request: dict[str, Any] = {}
    try:
        loaded_request = json.loads(request_path.read_text(encoding="utf-8"))
        if not isinstance(loaded_request, dict):
            raise ValueError("Runner request must be an object")
        request = loaded_request
        if request.get("version") != 2:
            raise ValueError("Unsupported runner request")
        executor = get_executor(request.get("language", ""))
        code = request.get("code")
        if not isinstance(code, str) or not code or len(code) > 100_000:
            raise ValueError("Invalid source code")

        job_root = Path(
            tempfile.mkdtemp(prefix=f"openoj-{request['job_id'][:12]}-", dir=WORK_DIR)
        )
        try:
            program = executor.prepare(
                job_root,
                job_root / "scratch",
                code,
                request["invocation"],
                request.get("limits", {}),
            )
            job_root.chmod(0o755)
            results = []
            request_cases = request.get("cases", [])
            for case_index, case in enumerate(request_cases):
                result = _run_case(
                    job_root,
                    case["input"],
                    request["invocation"],
                    request.get("limits", {}),
                    executor,
                    program,
                )
                results.append(result)
                scratch = job_root / "scratch"
                try:
                    os.chown(scratch, os.getuid(), os.getgid())
                    scratch.chmod(0o700)
                except FileNotFoundError:
                    pass
                shutil.rmtree(scratch, ignore_errors=True)
                if result["status"] != "completed":
                    results.extend(
                        {
                            "status": "skipped",
                            "error": "Not run after the preceding testcase stopped execution",
                            "runtime_ms": 0,
                        }
                        for _ in request_cases[case_index + 1:]
                    )
                    break
        finally:
            os.chown(job_root, os.getuid(), os.getgid())
            job_root.chmod(0o755)
            shutil.rmtree(job_root, ignore_errors=True)
        response = {"version": 2, "job_id": request["job_id"], "results": results}
    except ExecutorError as error:
        case_count = max(1, len(request.get("cases", [])))
        response = {
            "version": 2,
            "job_id": request.get("job_id", job_dir.name),
            "results": [
                {"status": "compile_error", "error": str(error), "runtime_ms": 0}
                for _ in range(case_count)
            ],
        }
    except Exception as error:
        case_count = max(1, len(request.get("cases", [])))
        print(f"Runner job {job_dir.name} failed:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        response = {
            "version": 2,
            "job_id": job_dir.name,
            "results": [
                {"status": "system_error", "error": f"Runner rejected job: {error}", "runtime_ms": 0}
                for _ in range(case_count)
            ],
        }

    temporary = job_dir / "result.tmp"
    temporary.write_text(json.dumps(response, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, result_path)
    (job_dir / "ready").unlink(missing_ok=True)


def _prewarm_toolchains_once() -> None:
    """Compile throwaway programs so a user's first submission never pays
    the cold toolchain cost (page-cache faults dominate rustc/g++/javac/tsc
    cold starts; the shared compile budget measures wall clock)."""
    warm_dir = Path(os.environ.get("OPENOJ_PREWARM_DIR", "/tmp/openoj-prewarm"))
    try:
        warm_dir.mkdir(parents=True, exist_ok=True)
        # The Go job runs as the compiler uid so it can share its build cache;
        # make the directory writable by that uid.
        warm_dir.chmod(0o1777)
        environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/nonexistent", "TMPDIR": str(warm_dir)}
        jobs = []
        rust_source = warm_dir / "warm.rs"
        rust_source.write_text("fn main() {}\n", encoding="utf-8")
        jobs.append((
            ("/usr/bin/rustc", "--edition=2021", "-C", "opt-level=2", "-C", "debuginfo=0",
             "-C", "strip=symbols", "-o", str(warm_dir / "warm-rust"), str(rust_source)),
            environment,
            None,
        ))
        cpp_source = warm_dir / "warm.cpp"
        cpp_source.write_text("int main() { return 0; }\n", encoding="utf-8")
        jobs.append((
            ("/usr/bin/g++", "-std=c++20", "-O2", "-pipe", "-o", str(warm_dir / "warm-cpp"), str(cpp_source)),
            environment,
            None,
        ))
        go_source = warm_dir / "warm-go"
        go_dir = warm_dir / "go"
        go_dir.mkdir(exist_ok=True)
        (go_dir / "go.mod").write_text("module warm\n\ngo 1.24\n", encoding="utf-8")
        # Every submission imports the wrapper stdlib packages (see
        # GoExecutor), so the warm build must import them too — blank imports
        # pull their archives into the shared GOCACHE without needing symbols.
        # An empty main only warms the runtime chain, leaving fmt, json, math,
        # os, io, and binary cold for the first submission.
        (go_dir / "main.go").write_text(
            "package main\n\n"
            + "".join(f'import _ "{package}"\n' for package in WRAPPER_IMPORTS)
            + "\nfunc main() {}\n",
            encoding="utf-8",
        )
        # The cache is shared with real submissions (see GoExecutor), so this
        # build leaves the standard library precompiled for every job. The Go
        # toolchain refuses to reuse a build cache written by another uid, so
        # the warm build drops to the compiler uid (65534) that submissions
        # run under; the directory is chowned to match.
        go_cache = Path("/tmp/openoj-gocache")
        go_cache.mkdir(parents=True, exist_ok=True)
        go_cache.chmod(0o1777)
        os.chown(go_cache, NOBODY_UID, NOBODY_GID)
        jobs.append((
            (SUPERVISOR_PYTHON, "/runner/compiler_sandbox.py", "2048", "32",
             "/usr/bin/go", "build", "-trimpath", "-o", str(warm_dir / "warm-go-bin"), str(go_dir / "main.go")),
            {**environment, "GOCACHE": str(go_cache), "GOENV": "off", "GOPROXY": "off", "CGO_ENABLED": "0"},
            None,
        ))
        java_source = warm_dir / "Warm.java"
        java_source.write_text("class Warm {}\n", encoding="utf-8")
        jobs.append((
            ("/usr/bin/javac", "-proc:none", "-g:none", "-d", str(warm_dir), str(java_source)),
            environment,
            None,
        ))
        ts_source = warm_dir / "warm.ts"
        ts_source.write_text("const value: number = 1;\nconsole.log(value);\n", encoding="utf-8")
        jobs.append((
            ("/usr/local/bin/tsc", "--target", "ES2022", "--module", "commonjs",
             "--skipLibCheck", "--outDir", str(warm_dir / "ts"), str(ts_source)),
            environment,
            None,
        ))
        for command, job_environment, preexec in jobs:
            try:
                subprocess.run(
                    command, env=job_environment, cwd=warm_dir,
                    preexec_fn=preexec,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=90, check=False,
                )
            except (OSError, subprocess.SubprocessError) as error:
                print(f"OpenOJ pre-warm skipped {' '.join(command[:2])}: {error}", file=sys.stderr, flush=True)
    except OSError as error:
        print(f"OpenOJ pre-warm disabled: {error}", file=sys.stderr, flush=True)


def _prewarm_loop() -> None:
    interval = float(os.environ.get("OPENOJ_PREWARM_INTERVAL", "600"))
    while True:
        _prewarm_toolchains_once()
        time.sleep(interval)


def main() -> None:
    for language in supported_languages():
        elapsed_ms, factor = get_executor(language).calibrate()
        CALIBRATION_FACTORS[language] = factor
        print(
            f"OpenOJ {language} calibration: {elapsed_ms:.1f} ms, deadline factor {factor:.2f}x",
            file=sys.stderr,
            flush=True,
        )
    # Serve immediately; warming runs alongside queue polling so startup is
    # never delayed, and repeats periodically to keep the toolchains warm.
    threading.Thread(target=_prewarm_loop, name="openoj-prewarm", daemon=True).start()
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        found = False
        for ready in QUEUE_DIR.glob("*/ready"):
            found = True
            _process_job(ready.parent)
        if not found:
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
