"""Authoring-side CLI services on the runner image.

Run the image as root when compiling (the executors' privilege dance
chowns work directories to the compiler uid): `docker run --user 0:0 ...`.

The image carries the pinned toolchain for every offered language, the
executors, and the judge's own harness code — these entry points expose
that machinery to problem creators, so authoring needs no local
toolchain beyond Docker:

  cli.py format <files...>            format to the OpenOJ standard
  cli.py gen-starters <problem.json>  emit every starter.<ext> for a
                                      bundle's language-agnostic schema
  cli.py judge <bundle-dir>           run every solution.* in the
                                      bundle through the real judging
                                      path; all must pass every case

In the image these run as `openoj format ...` / `openoj gen-starters
...` / `openoj judge ...` (see the ojcli entrypoint installed by the
Dockerfile). They operate on a bundle directory bind-mounted at any
path; nothing here writes outside the paths it is given.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RUNNER = Path(__file__).resolve().parent

# The executors and harness live beside this file; the gen_starters and
# format implementations are imported from a mounted problems repo (the
# schema is the contract, the tools are the standard) or, when the image
# carries its own copy, from there.
TOOLS_CANDIDATES = [
    Path("/tools"),                    # image convention
    RUNNER.parent / "problems-tools",  # beside a checkout
]


def _tools() -> Path:
    for candidate in TOOLS_CANDIDATES:
        if (candidate / "scripts" / "gen_starters.py").exists():
            return candidate
    raise SystemExit(
        "gen_starters.py not found; bind-mount the problems repo at /tools"
    )


def _executors_ready() -> None:
    sys.path.insert(0, str(RUNNER))
    from executors import get_executor  # noqa: F401  (probe)


LANGUAGE_BY_EXTENSION = {
    "py": "python3", "js": "javascript", "ts": "typescript",
    "java": "java", "cpp": "cpp", "go": "go", "rs": "rust", "sql": "sql",
    "json": "json", "md": "markdown",
}


def cmd_format(arguments: argparse.Namespace) -> int:
    """Format files (in place, or --check) with the pinned toolchain."""
    from formatters import format_source

    # expand directories into their formattable files
    files: list[Path] = []
    for name in arguments.files:
        path = Path(name)
        if path.is_dir():
            files += sorted(
                child for child in path.rglob("*")
                if child.is_file() and child.suffix.lstrip(".") in LANGUAGE_BY_EXTENSION
            )
        elif path.is_file():
            files.append(path)
        else:
            print(f"not a file: {path}", file=sys.stderr)
            return 2

    changed = unformatted = 0
    for path in files:
        extension = path.suffix.lstrip(".")
        language = LANGUAGE_BY_EXTENSION.get(extension)
        if language is None:
            if not arguments.check:
                print(f"no formatter for .{extension}", file=sys.stderr)
                return 2
            continue
        original = path.read_text(encoding="utf-8")
        formatted = format_source(language, original)
        if formatted != original:
            if arguments.check:
                unformatted += 1
                print(f"UNFORMATTED {path}")
            else:
                path.write_text(formatted, encoding="utf-8")
                changed += 1
                print(f"formatted {path}")
    if arguments.check:
        print(f"format check: {unformatted} unformatted files")
        return 1 if unformatted else 0
    print(f"{changed} file(s) changed")
    return 0


def cmd_gen_starters(arguments: argparse.Namespace) -> int:
    """Emit starter.<ext> for every offered language beside problem.json."""
    import importlib.util

    tools = _tools()
    spec = importlib.util.spec_from_file_location("gen_starters", tools / "scripts" / "gen_starters.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    problem_path = Path(arguments.problem)
    invocation = json.loads(problem_path.read_text(encoding="utf-8"))["invocation"]
    bundle = problem_path.parent
    gen.set_python_style(arguments.style)
    expected = gen.starter_files(invocation)
    for language, content in expected.items():
        target = bundle / f"starter.{gen.EXTENSIONS[language]}"
        target.write_text(content, encoding="utf-8")
        print(f"wrote {target}")
    return 0


def cmd_judge(arguments: argparse.Namespace) -> int:
    """Judge every solution.* in the bundle through the real executors."""
    _executors_ready()
    from executors import get_executor
    from executors.base import ExecutorError

    # The compiler sandbox exists for untrusted solver submissions; an
    # author judging their own reference solutions on their own machine
    # doesn't need it, and its per-uid process cap breaks `docker run`
    # (where root's pids are shared with the dropped compiler uid).
    # Compile plainly instead — same command, same pinned tools.
    import executors.compiled as compiled

    def _plain_compile(self, job_root, command, output_path, environment):
        import subprocess as sp

        merged = {**environment, "PATH": "/usr/local/bin:" + environment.get("PATH", "/usr/bin:/bin")}
        completed = sp.run(
            list(command), cwd=job_root, env=merged,
            stdout=sp.PIPE, stderr=sp.STDOUT, timeout=300,
        )
        if completed.returncode != 0:
            raw = completed.stdout or completed.stderr or b""
            raise ExecutorError(
                "Compilation failed:\n" + raw.decode("utf-8", "replace")[-4000:]
            )

    compiled.CompiledExecutor.compile = _plain_compile

    bundle = Path(arguments.bundle)
    problem = json.loads((bundle / "problem.json").read_text(encoding="utf-8"))
    invocation = problem["invocation"]
    limits = problem.get("limits", {})
    cases = json.loads((bundle / "cases.json").read_text(encoding="utf-8"))
    all_cases = cases.get("public", []) + cases.get("hidden", [])

    # Judge-assembly: the common library plus the bundle's provided/
    # sources compile/run with the submission, exactly as a live judge
    # job would assemble them.
    LANGUAGE_DIRECTORIES = {
        "python3": "python", "java": "java", "cpp": "cpp", "go": "go",
        "rust": "rust", "typescript": "typescript", "javascript": "javascript",
    }
    assembly: dict[str, dict[str, str]] = {"common": {}, "provided": {}}
    tools = next((c for c in TOOLS_CANDIDATES if (c / "scripts" / "gen_starters.py").exists()), None)
    # versioned common-harness contract: the checkout's declared version
    # must match what this image understands (see common/VERSION.json)
    if tools is not None:
        version_file = tools / "common" / "VERSION.json"
        if version_file.is_file():
            contract = json.loads(version_file.read_text(encoding="utf-8"))
            if contract.get("schema") != 1:
                raise SystemExit(
                    f"common harness schema {contract.get('schema')!r} is newer than this image understands; update the image"
                )
            print(f"common harness v{contract.get('version')}")
            # the per-bundle half: every problem.json declares the common
            # version it was authored against; it may not exceed the checkout's
            declared = problem.get("common_version")
            if not isinstance(declared, int) or isinstance(declared, bool) or declared < 1:
                raise SystemExit(
                    "problem.json must declare a positive integer 'common_version' "
                    "(the common-harness version it targets; see common/VERSION.json)"
                )
            if declared > contract["version"]:
                raise SystemExit(
                    f"bundle targets common harness v{declared}, "
                    f"this checkout ships v{contract['version']}"
                )
    common_root = tools / "common" if tools else None
    for name, directory in LANGUAGE_DIRECTORIES.items():
        common_dir = common_root / directory if common_root else None
        if common_dir and common_dir.is_dir():
            for path in sorted(common_dir.iterdir()):
                if path.is_file():
                    assembly["common"][path.name] = path.read_text(encoding="utf-8")
    for language, directory in LANGUAGE_DIRECTORIES.items():
        provided_dir = bundle / "provided" / directory
        if provided_dir.is_dir():
            for path in sorted(provided_dir.iterdir()):
                if path.is_file():
                    assembly["provided"][path.name] = path.read_text(encoding="utf-8")

    solutions = sorted(
        path for path in bundle.iterdir() if path.name.startswith("solution") and path.suffix != ".md"
    )
    if not solutions:
        print("no solution files found", file=sys.stderr)
        return 2

    failures = 0
    LANGUAGE_EXTENSIONS = {
        "python3": {"py"},
        "java": {"java"},
        "cpp": {"hpp", "cpp", "h", "cc"},
        "go": {"go"},
        "rust": {"rs"},
        "typescript": {"ts"},
        "javascript": {"js"},
        "sql": {"sql"},
    }
    EXTENSION_LANGUAGE = {
        "py": "python3", "js": "javascript", "ts": "typescript", "java": "java",
        "cpp": "cpp", "go": "go", "rs": "rust", "sql": "sql",
    }
    for solution in solutions:
        language = EXTENSION_LANGUAGE.get(solution.suffix.lstrip("."))
        if language is None:
            print(f"SKIP  {solution.name}: no executor for {solution.suffix}")
            continue
        executor = get_executor(language)
        code = solution.read_text(encoding="utf-8")
        work = Path(tempfile.mkdtemp(prefix="openoj-cli-"))
        try:
            work.chmod(0o777)
        except OSError:
            pass
        # The compiled executors fork sandboxed compilers with tight rlimits;
        # the authoring CLI gives them a plain writable HOME so toolchains
        # that insist on caching there (go, tsc) behave.
        os.environ.setdefault("HOME", "/tmp")
        for variable, value in (
            ("GOCACHE", "/tmp/openoj-gocache"),
            ("GOPATH", "/tmp/openoj-gopath"),
            ("GOMODCACHE", "/tmp/openoj-gomodcache"),
            ("GO111MODULE", "off"),
            ("PATH", "/usr/local/bin:" + os.environ.get("PATH", "/usr/bin:/bin")),
        ):
            os.environ[variable] = value
        scratch = work / "scratch"
        scratch.mkdir()
        passed = 0
        try:
            try:
                extensions = LANGUAGE_EXTENSIONS.get(language, set())
                per_language = {
                    part: {
                        name: content for name, content in files.items()
                        if name.rsplit(".", 1)[-1] in extensions
                    }
                    for part, files in assembly.items()
                }
                program = executor.prepare(work, scratch, code, invocation, limits, per_language)
            except ExecutorError as error:
                print(f"FAIL  {solution.name}: prepare/compile: {str(error)[-400:]}")
                failures += 1
                continue
            except Exception as error:  # noqa: BLE001 — report, don't crash the sweep
                print(f"FAIL  {solution.name}: prepare error: {error!r} ({type(error).__name__})")
                failures += 1
                continue
            for index, case in enumerate(all_cases):
                try:
                    if getattr(executor, "encode_case_with_limits", False):
                        payload = executor.encode_case(invocation, case["input"], limits)
                    else:
                        payload = executor.encode_case(invocation, case["input"])
                    process = subprocess.Popen(
                        list(program.command),
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        env=program.environment,
                    )
                    output, _ = process.communicate(
                        payload, timeout=limits.get("time_ms", 1500) / 1000 * 3 + 5
                    )
                except Exception as error:  # noqa: BLE001
                    print(f"FAIL  {solution.name}: case {index + 1}: {error}")
                    failures += 1
                    continue
                text = output.decode("utf-8", "replace")
                marker = "__OPENOJ_RESULT__"
                line = next((l for l in text.splitlines() if marker in l), "")
                verdict = json.loads(line[len(marker):]) if line else {"status": "no_output"}
                if verdict.get("status") == "completed":
                    passed += 1
                else:
                    print(
                        f"FAIL  {solution.name}: case {index + 1}: "
                        f"{verdict.get('status')}: {verdict.get('error', '')[:120]}"
                    )
                    failures += 1
        finally:
            shutil.rmtree(work, ignore_errors=True)
        print(f"{'OK  ' if passed == len(all_cases) else 'FAIL'} {solution.name}: {passed}/{len(all_cases)} cases")
    print(f"{len(all_cases) and 'judged' or 'no cases'}; {failures} case-level failure(s)")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="openoj", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    fmt = sub.add_parser("format", help="format files (or --check) with the pinned toolchain")
    fmt.add_argument("files", nargs="+", help="files or directories (dirs walk for formattable files)")
    fmt.add_argument("--check", action="store_true", help="report unformatted files, change nothing, exit 1")
    fmt.set_defaults(fn=cmd_format)

    gen = sub.add_parser("gen-starters", help="emit starter.* from problem.json")
    gen.add_argument("problem")
    gen.add_argument("--style", default="modern", choices=["modern", "legacy"])
    gen.set_defaults(fn=cmd_gen_starters)

    judge = sub.add_parser("judge", help="judge every solution in a bundle")
    judge.add_argument("bundle")
    judge.set_defaults(fn=cmd_judge)

    arguments = parser.parse_args()
    return arguments.fn(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
