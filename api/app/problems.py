import copy
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional


PROBLEMS_DIR = Path(os.environ.get("OPENOJ_PROBLEMS_DIR", "problems")).resolve()
REQUIRED_SECTIONS = (
    "Metadata",
    "Description",
    "Hints",
    "Invocation",
    "Limits",
    "Languages",
    "Starters",
    "Test Cases",
)
HEADING = re.compile(r"^(?P<marks>#{1,6})[ \t]+(?P<title>.+?)[ \t]*$")
TITLE = re.compile(r"^(?P<id>[1-9][0-9]*)\.[ \t]+(?P<title>\S(?:.*\S)?)$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PROBLEM_FILE = re.compile(
    r"^(?P<number>[0-9]{4,})_(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.md$"
)
FENCED_BLOCK = re.compile(
    r"```(?P<info>[^\n`]*)\n(?P<body>.*?)\n```[ \t]*",
    re.DOTALL,
)


class ProblemError(ValueError):
    pass


def _headings(markdown: str) -> list[tuple[int, str, int]]:
    headings = []
    in_fence = False
    for line_number, line in enumerate(markdown.splitlines(keepends=True)):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING.match(line.rstrip("\r\n"))
        if match:
            headings.append((len(match.group("marks")), match.group("title"), line_number))
    if in_fence:
        raise ProblemError("Markdown contains an unclosed fenced block")
    return headings


def _schema_sections(markdown: str) -> tuple[int, str, dict[str, str]]:
    lines = markdown.splitlines(keepends=True)
    headings = _headings(markdown)
    first_content = next(
        (index for index, line in enumerate(lines) if line.strip()),
        None,
    )
    h1 = [heading for heading in headings if heading[0] == 1]
    if len(h1) != 1 or first_content is None or h1[0][2] != first_content:
        raise ProblemError("Problem Markdown must begin with exactly one level-one title")
    title_match = TITLE.fullmatch(h1[0][1])
    if title_match is None:
        raise ProblemError("The title must use '# <positive id>. <title>'")

    h2 = [heading for heading in headings if heading[0] == 2]
    section_names = tuple(heading[1] for heading in h2)
    if section_names != REQUIRED_SECTIONS:
        expected = ", ".join(f"## {name}" for name in REQUIRED_SECTIONS)
        raise ProblemError(f"Required level-two headings must be exactly: {expected}")

    sections = {}
    for index, (_, name, line_number) in enumerate(h2):
        end = h2[index + 1][2] if index + 1 < len(h2) else len(lines)
        sections[name] = "".join(lines[line_number + 1:end]).strip("\n")
    return int(title_match.group("id")), title_match.group("title"), sections


def _fenced_payload(section: str, heading: str, info: Optional[str] = None) -> tuple[str, str]:
    match = FENCED_BLOCK.fullmatch(section.strip())
    if match is None:
        raise ProblemError(f"## {heading} must contain exactly one fenced block")
    block_info = match.group("info").strip()
    if info is not None and block_info != info:
        raise ProblemError(f"## {heading} must use a {info!r} fenced block")
    return block_info, match.group("body")


def _json_value(section: str, heading: str) -> Any:
    _, payload = _fenced_payload(section, heading, "json")
    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        raise ProblemError(f"## {heading} contains invalid JSON: {error.msg}") from error


def _json_object(section: str, heading: str) -> dict[str, Any]:
    value = _json_value(section, heading)
    if not isinstance(value, dict):
        raise ProblemError(f"## {heading} must contain a JSON object")
    return value


def _json_array(section: str, heading: str) -> list[Any]:
    value = _json_value(section, heading)
    if not isinstance(value, list):
        raise ProblemError(f"## {heading} must contain a JSON array")
    return value


def _subsections(section: str, parent: str) -> list[tuple[str, str]]:
    lines = section.splitlines(keepends=True)
    headings = _headings(section)
    if any(level != 3 for level, _, _ in headings):
        raise ProblemError(f"## {parent} may contain only level-three child headings")
    if not headings:
        raise ProblemError(f"## {parent} must contain level-three child headings")
    if "".join(lines[:headings[0][2]]).strip():
        raise ProblemError(f"## {parent} cannot contain text before its first child heading")

    result = []
    for index, (_, title, line_number) in enumerate(headings):
        end = headings[index + 1][2] if index + 1 < len(headings) else len(lines)
        result.append((title, "".join(lines[line_number + 1:end]).strip("\n")))
    titles = [title for title, _ in result]
    if len(titles) != len(set(titles)):
        raise ProblemError(f"## {parent} contains a duplicate child heading")
    return result


def _require_exact_keys(value: dict[str, Any], keys: set[str], heading: str) -> None:
    if set(value) != keys:
        raise ProblemError(f"## {heading} must contain exactly: {', '.join(sorted(keys))}")


def _validate_cases(value: list[Any], heading: str) -> list[dict[str, Any]]:
    cases = []
    for index, case in enumerate(value, start=1):
        if not isinstance(case, dict) or set(case) != {"input", "expected"}:
            raise ProblemError(
                f"{heading} testcase {index} must contain exactly 'input' and 'expected'"
            )
        cases.append(case)
    return cases


def parse_problem_markdown(
    markdown: str,
    source_path: Optional[Path] = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    """Parse one complete problem document using the required heading schema."""
    problem_id, title, sections = _schema_sections(markdown)

    metadata = _json_object(sections["Metadata"], "Metadata")
    _require_exact_keys(
        metadata,
        {"schema_version", "slug", "difficulty", "tags", "source"},
        "Metadata",
    )
    if metadata["schema_version"] != 1:
        raise ProblemError("Unsupported problem Markdown schema version")
    slug = metadata["slug"]
    if not isinstance(slug, str) or SLUG.fullmatch(slug) is None:
        raise ProblemError("Metadata slug must be lowercase kebab-case")
    if not isinstance(metadata["difficulty"], str) or not metadata["difficulty"]:
        raise ProblemError("Metadata difficulty must be a non-empty string")
    if not isinstance(metadata["tags"], list) or not all(
        isinstance(tag, str) and tag for tag in metadata["tags"]
    ):
        raise ProblemError("Metadata tags must be an array of non-empty strings")
    source = metadata["source"]
    if not isinstance(source, dict):
        raise ProblemError("Metadata source must be an object")
    _require_exact_keys(source, {"label", "url"}, "Metadata source")
    if not all(isinstance(source[key], str) and source[key] for key in source):
        raise ProblemError("Metadata source values must be non-empty strings")

    if source_path is not None:
        filename = PROBLEM_FILE.fullmatch(source_path.name)
        if filename is None:
            raise ProblemError("Problem filename must use '<zero-padded id>_<slug>.md'")
        if filename.group("slug") != slug or int(filename.group("number")) != problem_id:
            raise ProblemError("Problem filename id and slug must match its document data")

    description = sections["Description"].strip()
    if not description:
        raise ProblemError("## Description cannot be empty")

    hints = _json_array(sections["Hints"], "Hints")
    if not all(isinstance(hint, str) and hint for hint in hints):
        raise ProblemError("## Hints must contain only non-empty strings")

    invocation = _json_object(sections["Invocation"], "Invocation")
    limits = _json_object(sections["Limits"], "Limits")
    _require_exact_keys(limits, {"time_ms", "memory_mb", "output_kb"}, "Limits")
    if not all(isinstance(value, int) and value > 0 for value in limits.values()):
        raise ProblemError("## Limits values must be positive integers")

    languages = _json_object(sections["Languages"], "Languages")
    if not languages:
        raise ProblemError("## Languages cannot be empty")
    language_keys = {"display_name", "monaco_language", "version", "enabled"}
    for language, config in languages.items():
        if not isinstance(language, str) or SLUG.fullmatch(language) is None:
            raise ProblemError("Language keys must be lowercase identifiers")
        if not isinstance(config, dict):
            raise ProblemError(f"Language {language!r} configuration must be an object")
        _require_exact_keys(config, language_keys, f"Languages/{language}")
        if not all(
            isinstance(config[key], str) and config[key]
            for key in ("display_name", "monaco_language", "version")
        ) or not isinstance(config["enabled"], bool):
            raise ProblemError(f"Language {language!r} has invalid configuration values")

    starter_sections = _subsections(sections["Starters"], "Starters")
    starter_names = [name for name, _ in starter_sections]
    if starter_names != list(languages):
        raise ProblemError("### starter headings must match ## Languages keys and order")
    for language, starter_section in starter_sections:
        _, starter = _fenced_payload(starter_section, f"Starters/{language}")
        if not starter.strip():
            raise ProblemError(f"Starter for {language!r} cannot be empty")
        languages[language]["starter"] = starter.rstrip("\n") + "\n"

    testcase_sections = _subsections(sections["Test Cases"], "Test Cases")
    if [name for name, _ in testcase_sections] != ["Public", "Hidden"]:
        raise ProblemError("## Test Cases requires ordered ### Public and ### Hidden headings")
    public = _validate_cases(
        _json_array(testcase_sections[0][1], "Test Cases/Public"),
        "Public",
    )
    hidden = _validate_cases(
        _json_array(testcase_sections[1][1], "Test Cases/Hidden"),
        "Hidden",
    )
    if not public:
        raise ProblemError("At least one public testcase is required")

    problem = {
        "schema_version": metadata["schema_version"],
        "id": problem_id,
        "slug": slug,
        "title": title,
        "difficulty": metadata["difficulty"],
        "tags": metadata["tags"],
        "source": source,
        "description": description + "\n",
        "hints": hints,
        "invocation": invocation,
        "limits": limits,
        "languages": languages,
    }
    return problem, public + hidden, len(public)


@lru_cache(maxsize=256)
def _cached_problem(
    path_string: str,
    modified_ns: int,
    size: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    del modified_ns, size
    path = Path(path_string)
    return parse_problem_markdown(path.read_text(encoding="utf-8"), path)


def _load_path(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    stat = path.stat()
    return copy.deepcopy(_cached_problem(str(path), stat.st_mtime_ns, stat.st_size))


def _safe_problem_path(slug: str) -> Path:
    if SLUG.fullmatch(slug) is None:
        raise ProblemError("Invalid problem slug")
    matches = []
    for candidate in PROBLEMS_DIR.glob(f"*_{slug}.md"):
        path = candidate.resolve()
        if path.parent != PROBLEMS_DIR or PROBLEM_FILE.fullmatch(path.name) is None:
            continue
        problem, _, _ = _load_path(path)
        if problem["slug"] == slug:
            matches.append(path)
    if len(matches) != 1:
        raise ProblemError("Problem not found" if not matches else "Duplicate problem slug")
    return matches[0]


def load_problem(slug: str) -> dict[str, Any]:
    problem, cases, public_count = _load_path(_safe_problem_path(slug))
    problem["public_cases"] = [
        {**case, "name": case.get("name", f"Example {index + 1}")}
        for index, case in enumerate(cases[:public_count])
    ]
    return problem


def load_all_cases(slug: str) -> tuple[list[dict[str, Any]], int]:
    _, cases, public_count = _load_path(_safe_problem_path(slug))
    named_cases = [
        {
            **case,
            "name": case.get(
                "name",
                f"Example {index + 1}"
                if index < public_count
                else f"Hidden case {index - public_count + 1}",
            ),
        }
        for index, case in enumerate(cases)
    ]
    return named_cases, public_count


def list_problems() -> list[dict[str, Any]]:
    problems = []
    if not PROBLEMS_DIR.exists():
        return problems
    for markdown_path in sorted(PROBLEMS_DIR.glob("*.md")):
        try:
            path = markdown_path.resolve()
            if path.parent != PROBLEMS_DIR or PROBLEM_FILE.fullmatch(path.name) is None:
                continue
            data, _, _ = _load_path(path)
            problems.append(
                {key: data[key] for key in ("id", "slug", "title", "difficulty", "tags")}
            )
        except (ProblemError, OSError, ValueError, json.JSONDecodeError):
            continue
    return sorted(problems, key=lambda item: item["id"])


def public_problem(problem: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "id", "slug", "title", "difficulty", "tags", "description", "hints",
        "invocation", "limits", "languages", "public_cases", "source",
    }
    result = {key: value for key, value in problem.items() if key in allowed}
    result["languages"] = {
        key: copy.deepcopy(config)
        for key, config in result["languages"].items()
    }
    invocation = result["invocation"]
    public_cases = []
    for index, case in enumerate(result["public_cases"]):
        raw_input = case["input"]
        if invocation.get("type", "function") == "function":
            names = [parameter["name"] for parameter in invocation.get("parameters", [])]
            display_input = dict(zip(names, raw_input))
        else:
            display_input = raw_input
        public_cases.append(
            {"name": case.get("name", f"Case {index + 1}"), "input": display_input}
        )
    result["public_cases"] = public_cases
    return result
