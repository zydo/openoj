"""Source formatting for the editor's Format button.

The runner already carries every language toolchain, so it is also the only
place the real formatters can live. Widths here are the same 120 columns the
problems repo formats its bundles at (`openoj-problems/.prettierrc.json`,
`ruff.toml`, `.clang-format`, `rustfmt.toml`) — a starter formatted in the
editor should come out byte-identical to the one the generator writes.

Formatting is pure text in, text out: no user code is executed, so this runs
directly rather than through the sandboxes the judge uses.
"""

from __future__ import annotations

import re
import shutil
import subprocess

FORMAT_TIMEOUT_SECONDS = 20
WIDTH = "120"

# Prettier v3 resolves plugins as ESM relative to the working directory, which
# the runner has none of, so the java plugin is named by absolute path rather
# than left to NODE_PATH (which ESM import ignores).
# The ESM entry point itself, not the package directory: directory imports
# are not resolvable under ESM.
_PRETTIER_JAVA_PLUGIN = "/usr/local/lib/node_modules/prettier-plugin-java/dist/index.mjs"

_PRETTIER = ["prettier", "--print-width", WIDTH, "--tab-width", "4", "--parser"]

_CLANG_STYLE = "{BasedOnStyle: LLVM, IndentWidth: 4, ColumnLimit: " + WIDTH + "}"

_COMMANDS: dict[str, list[str]] = {
    "python3": ["ruff", "format", "--line-length", WIDTH, "-"],
    "go": ["gofmt"],
    "rust": ["rustfmt", "--edition", "2021", "--config", f"max_width={WIDTH}", "--emit", "stdout"],
    "cpp": ["clang-format", f"--style={_CLANG_STYLE}", "--assume-filename=solution.cpp"],
    "java": [*_PRETTIER, "java", "--plugin", _PRETTIER_JAVA_PLUGIN],
    "typescript": [*_PRETTIER, "typescript"],
    "javascript": [*_PRETTIER, "babel"],
    # sql-formatter rather than prettier, matching how the problems repo
    # formats bundle SQL (`openoj-problems/scripts/format.py`).
    "sql": [
        "node",
        "-e",
        "const { format } = require('sql-formatter');"
        "process.stdout.write(format(require('fs').readFileSync(0, 'utf8'), { language: 'sqlite' }))",
    ],
}


class FormatError(RuntimeError):
    """A formatter refused the source, or is not installed."""


_GO_PACKAGE = re.compile(r"^\s*package\s+\w", re.MULTILINE)
_GO_PREAMBLE = "package openoj\n"


def _wrap_go(code: str) -> tuple[str, bool]:
    """Give Go source a package clause if it has none.

    Solutions and starters are fragments -- a bare `import` and `func`, with
    the package supplied by the executor's wrapper -- and gofmt parses whole
    files only, so without this every Go source fails to format.
    """
    if _GO_PACKAGE.match(code):
        return code, False
    return _GO_PREAMBLE + code, True


def _unwrap_go(formatted: str) -> str:
    body = formatted[len(_GO_PREAMBLE):] if formatted.startswith(_GO_PREAMBLE) else formatted
    # gofmt puts a blank line after the package clause that the fragment,
    # having never had a package clause, should not inherit.
    return body[1:] if body.startswith("\n") else body


def formattable_languages() -> tuple[str, ...]:
    return tuple(sorted(_COMMANDS))


def format_source(language: str, code: str) -> str:
    """Return `code` formatted for `language`.

    Raises FormatError when the language has no formatter, the tool is
    missing from the image, or the source does not parse — the caller turns
    that into a 4xx, because an unformattable draft is the user's to fix and
    not a judge failure.
    """
    command = _COMMANDS.get(language)
    if command is None:
        raise FormatError(f"No formatter is installed for {language!r}")
    if shutil.which(command[0]) is None:
        raise FormatError(f"The {command[0]} formatter is unavailable")
    source, wrapped = _wrap_go(code) if language == "go" else (code, False)
    try:
        completed = subprocess.run(
            command,
            input=source,
            capture_output=True,
            text=True,
            timeout=FORMAT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise FormatError("Formatting timed out") from error
    if completed.returncode != 0:
        # Formatters report a parse error on stderr; the first line of it is
        # what the user needs and the rest is tool noise.
        detail = (completed.stderr or "").strip().splitlines()
        raise FormatError(detail[0] if detail else "The source could not be formatted")
    if not completed.stdout:
        raise FormatError("The formatter returned nothing")
    return _unwrap_go(completed.stdout) if wrapped else completed.stdout
