import contextlib
import importlib.util
import io
import json
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

# The harness also runs with Python isolated mode. Only trusted modules baked
# into the read-only runner image are added; the submission directory is never
# placed on the import path.
sys.path.insert(0, "/runner")

from interactive_oracles import (
    ArrayReader,
    BinaryMatrix,
    InfiniteStream,
    Master,
    MountainArray,
    Robot,
)
from leetcode_types import (
    HtmlParser,
    ListNode,
    NestedInteger,
    Node,
    TreeNode,
    decode,
    emit_protocol,
    encode,
)


PROTOCOL_PREFIX = "__OPENOJ_RESULT__"
MAX_CAPTURED_OUTPUT = 16_384
SCHEDULE_STACK_BYTES = 512 * 1024


class BoundedText(io.StringIO):
    def write(self, value: str) -> int:
        remaining = MAX_CAPTURED_OUTPUT - self.tell()
        if remaining > 0:
            super().write(value[:remaining])
        return len(value)


def _json_safe(value: Any, output_limit: int = 65_536) -> Any:
    encoded = json.dumps(value, allow_nan=False, separators=(",", ":"))
    if len(encoded) > output_limit:
        raise ValueError(f"Return value exceeds the {output_limit // 1024} KiB output limit")
    return json.loads(encoded)


def _load_solution(solution_path: Path):
    spec = importlib.util.spec_from_file_location("openoj_solution", solution_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load solution")
    module = importlib.util.module_from_spec(spec)
    # LeetCode supplies these names to submitted source automatically.
    module.__dict__.update(
        {
            "ListNode": ListNode,
            "TreeNode": TreeNode,
            "Node": Node,
            "NestedInteger": NestedInteger,
            "HtmlParser": HtmlParser,
            "GridMaster": GridMaster,
            "Robot": Robot,
            "Master": Master,
            "MountainArray": MountainArray,
            "BinaryMatrix": BinaryMatrix,
            "ArrayReader": ArrayReader,
            "InfiniteStream": InfiniteStream,
        }
    )
    spec.loader.exec_module(module)
    return module


def _invoke_function(module, invocation: dict[str, Any], raw_input: Any) -> Any:
    if not isinstance(raw_input, list):
        raise ValueError("Function input must be a positional argument list")
    parameters = invocation.get("parameters", [])
    if len(raw_input) != len(parameters):
        raise ValueError(
            f"Expected {len(parameters)} arguments, received {len(raw_input)}"
        )
    arguments = [
        decode(value, parameter.get("codec", "json"))
        for value, parameter in zip(raw_input, parameters)
    ]
    instance = getattr(module, invocation["class_name"])()
    actual = getattr(instance, invocation["method"])(*arguments)
    return encode(actual, invocation.get("return_codec", "json"))


def _canonical_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _method_codecs(invocation: dict[str, Any]) -> dict[str, tuple[list[str], str]]:
    """Per-method (parameter codecs, return codec) from the manifest, so a
    design method can take or return a ListNode/TreeNode just like a
    function-invocation problem does."""
    table: dict[str, tuple[list[str], str]] = {}
    for method in invocation.get("methods", []):
        parameter_codecs = [
            parameter.get("codec", "json") for parameter in method.get("parameters", [])
        ]
        table[method["name"]] = (parameter_codecs, method.get("return_codec", "json"))
    return table


def _resolve_pipe(value: Any, output: list[Any]) -> Any:
    """{"$prev": i} feeds action i's own return value straight back in, so a
    round-trip pair (serialize then deserialize) can be judged without
    pinning the intermediate format."""
    if isinstance(value, dict) and set(value) == {"$prev"}:
        return output[int(value["$prev"])]
    return value


def _invoke_design(module, invocation: dict[str, Any], raw_input: Any) -> Any:
    actions = raw_input["actions"]
    params = raw_input["params"]
    if not actions or len(actions) != len(params):
        raise ValueError("Design input requires equally sized actions and params")
    codecs = _method_codecs(invocation)
    constructor_codecs = [
        parameter.get("codec", "json")
        for parameter in invocation.get("constructor", {}).get("parameters", [])
    ]
    constructor_arguments = [
        decode(value, constructor_codecs[index] if index < len(constructor_codecs) else "json")
        for index, value in enumerate(params[0])
    ]
    instance = getattr(module, invocation["class_name"])(*constructor_arguments)
    output = [None]
    # Raw (undecoded, unencoded) returns feed piped arguments, so a piped
    # value crosses methods as the live object rather than its wire form.
    raw_output: list[Any] = [None]
    for action, arguments in zip(actions[1:], params[1:]):
        # A repeated action ({"call": name, "repeat": K}) is a randomized
        # method under statistical judging: the harness invokes it K times
        # and reports a frequency table keyed by the canonical JSON of each
        # returned value, which the judge compares against the expected
        # distribution.
        repeat = 1
        if isinstance(action, dict):
            repeat = int(action.get("repeat", 1))
            action = action["call"]
        parameter_codecs, return_codec = codecs.get(action, ([], "json"))
        decoded = [
            _resolve_pipe(argument, raw_output)
            if isinstance(argument, dict) and set(argument) == {"$prev"}
            else decode(argument, parameter_codecs[index] if index < len(parameter_codecs) else "json")
            for index, argument in enumerate(arguments)
        ]
        if repeat <= 1:
            value = getattr(instance, action)(*decoded)
            raw_output.append(value)
            output.append(encode(value, return_codec))
            continue
        counts: dict[str, int] = {}
        last = None
        for _ in range(repeat):
            last = getattr(instance, action)(*decoded)
            key = _canonical_key(encode(last, return_codec))
            counts[key] = counts.get(key, 0) + 1
        raw_output.append(last)
        output.append(counts)
    return output


class GridMaster:
    """Interactive oracle for hidden-grid problems (invocation type
    "interactive"). Mirrors runner/java/GridMaster.java exactly."""

    DELTAS = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}

    def __init__(self, grid: list[list[int]], start: list[int], target: list[int], budget: int):
        self.cost = grid
        self.rows, self.cols = len(grid), len(grid[0]) if grid else 0
        self.row, self.col = start
        self.target_row, self.target_col = target
        self.budget = budget

    def _spend(self) -> None:
        if self.budget <= 0:
            raise RuntimeError("GridMaster query budget exhausted")
        self.budget -= 1

    def _enterable(self, row: int, col: int) -> bool:
        return 0 <= row < self.rows and 0 <= col < self.cols and self.cost[row][col] > 0

    def canMove(self, direction: str) -> bool:  # noqa: N802 — LeetCode API
        self._spend()
        delta_row, delta_col = self.DELTAS[direction]
        return self._enterable(self.row + delta_row, self.col + delta_col)

    def move(self, direction: str) -> int:
        self._spend()
        delta_row, delta_col = self.DELTAS[direction]
        row, col = self.row + delta_row, self.col + delta_col
        if not self._enterable(row, col):
            return -1
        self.row, self.col = row, col
        return self.cost[row][col]

    def isTarget(self) -> bool:  # noqa: N802 — LeetCode API
        self._spend()
        return (self.row, self.col) == (self.target_row, self.target_col)


def _build_oracle(name: str, raw_input: dict[str, Any], budget: int) -> Any:
    if name == "GridMaster":
        return GridMaster(raw_input["grid"], raw_input["start"], raw_input["target"], budget)
    if name == "Robot":
        return Robot(raw_input["room"], raw_input["start"], budget)
    if name == "Master":
        return Master(raw_input["wordlist"], raw_input["secret"], budget)
    if name == "MountainArray":
        return MountainArray(raw_input["mountain"], budget)
    if name == "BinaryMatrix":
        return BinaryMatrix(raw_input["matrix"], budget)
    if name == "ArrayReader":
        return ArrayReader(raw_input["arr"], budget)
    if name == "InfiniteStream":
        return InfiniteStream(raw_input["bits"], budget)
    raise ValueError(f"Unsupported interactive oracle: {name}")


# Some oracles pair with auxiliary case data the solution method also
# needs — LeetCode's two-argument signatures (guess-the-word's wordlist,
# mountain-array's target, ...). The case key listed here is passed to the
# method as a second argument, after the oracle.
ORACLE_AUXILIARY = {
    "Master": "wordlist",
    "MountainArray": "target",
    "ArrayReader": "target",
    "InfiniteStream": "pattern",
}


def _invoke_interactive(module, invocation: dict[str, Any], raw_input: Any) -> Any:
    oracle_name = invocation.get("oracle", "GridMaster")
    if not isinstance(raw_input, dict):
        raise ValueError("Interactive input must be an object")
    budget = int(invocation.get("query_limit", 1_000_000))
    oracle = _build_oracle(oracle_name, raw_input, budget)
    instance = getattr(module, invocation["class_name"])()
    arguments = [oracle]
    if oracle_name in ORACLE_AUXILIARY:
        key = ORACLE_AUXILIARY[oracle_name]
        if key not in raw_input:
            raise ValueError(f"Interactive input for {oracle_name} needs {key!r}")
        arguments.append(raw_input[key])
    result = getattr(instance, invocation["method"])(*arguments)
    # Void-method oracles are judged by their own final state — e.g. the
    # robot's exact set of cleaned cells.
    if result is None and hasattr(oracle, "verdict"):
        return oracle.verdict()
    return result


# glibc's malloc gives each thread its own arena, reserving 64 MiB of
# address space apiece — a schedule's worth of threads blows past the
# sandbox's allowance and pthread_create fails with "can't start new
# thread". MALLOC_ARENA_MAX cannot carry this: glibc scrubs MALLOC_* from
# the environment after the sandbox drops privileges, so the cap is set
# in-process instead. M_ARENA_MAX is mallopt parameter -8.
M_ARENA_MAX = -8


def _cap_allocator_arenas() -> None:
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").mallopt(M_ARENA_MAX, 1)
    except Exception:  # noqa: BLE001 — musl and friends have no mallopt
        pass


def _invoke_concurrent(module, invocation: dict[str, Any], raw_input: Any) -> Any:
    """Run a schedule of calls on real threads and report what happened.

    Each entry in the schedule becomes one thread. A call that LeetCode
    hands a release callback declares `emits`: the harness passes a
    callback that appends that token to the shared log, so the log is the
    interleaving the solution actually produced. A call that returns a
    value declares `records`, and its return value is appended when it
    completes. The judge compares the log — order-insensitively, or
    against the problem's structural invariant — because a correct
    concurrent program has many valid interleavings.
    """
    if not isinstance(raw_input, dict):
        raise ValueError("Concurrent input must be an object")
    schedule = raw_input.get("threads")
    if not isinstance(schedule, list) or not schedule:
        raise ValueError("Concurrent input needs a non-empty threads list")
    instance = getattr(module, invocation["class_name"])(*raw_input.get("constructor", []))
    events: list[Any] = []
    lock = threading.Lock()
    failures: list[str] = []

    def record(value: Any) -> None:
        with lock:
            events.append(value)

    def runner(call: str, arguments: list[Any], emits: Any, records: bool):
        def run() -> None:
            try:
                method = getattr(instance, call)
                if emits is not None:
                    method(*arguments, lambda: record(emits))
                elif records:
                    record(method(*arguments))
                else:
                    method(*arguments)
            except BaseException as error:  # noqa: BLE001 — reported as a verdict
                with lock:
                    failures.append(f"{type(error).__name__}: {error}")
        return run

    _cap_allocator_arenas()
    # Each thread reserves its stack from the sandbox's address-space
    # allowance, and the default 8 MiB times a schedule's worth of threads
    # exceeds it outright — pthread_create then fails with "can't start new
    # thread". A schedule thread runs one short method, so a small stack is
    # ample.
    # The stack size has to still be in effect when a thread *starts* — that
    # is when the stack is reserved — not merely when it is constructed.
    previous_stack = threading.stack_size()
    threading.stack_size(SCHEDULE_STACK_BYTES)
    try:
        threads = [
            threading.Thread(
                target=runner(
                    spec["call"],
                    list(spec.get("args", [])),
                    spec.get("emits"),
                    bool(spec.get("records")),
                ),
                daemon=True,
            )
            for spec in schedule
        ]
        for thread in threads:
            thread.start()
    finally:
        threading.stack_size(previous_stack)
    # The outer judge timeout is the deadlock detector: a schedule that
    # never completes simply never returns, and the case times out.
    for thread in threads:
        thread.join()
    if failures:
        raise RuntimeError(failures[0])
    return events


def _invoke(module, invocation: dict[str, Any], raw_input: Any) -> Any:
    invocation_type = invocation.get("type", "function")
    if invocation_type == "function":
        return _invoke_function(module, invocation, raw_input)
    if invocation_type == "design":
        return _invoke_design(module, invocation, raw_input)
    if invocation_type == "interactive":
        return _invoke_interactive(module, invocation, raw_input)
    if invocation_type == "concurrent":
        return _invoke_concurrent(module, invocation, raw_input)
    raise ValueError(f"Unsupported invocation type: {invocation_type}")


def main() -> None:
    response: dict[str, Any]
    captured = BoundedText()
    try:
        payload = json.load(sys.stdin)
        invocation = payload["invocation"]
        output_limit = int(payload.get("limits", {}).get("output_kb", 64)) * 1024
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            module = _load_solution(Path(sys.argv[1]))
            actual = _invoke(module, invocation, payload["input"])
        response = {
            "status": "completed",
            "actual": _json_safe(actual, output_limit),
            "stdout": captured.getvalue(),
        }
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            error = RuntimeError("Solution interrupted execution")
        response = {
            "status": "runtime_error",
            "error": f"{type(error).__name__}: {error}"[:1000],
            "stdout": captured.getvalue(),
            "traceback": "".join(traceback.format_exception_only(type(error), error))[
                -2000:
            ],
        }
    emit_protocol(
        PROTOCOL_PREFIX + json.dumps(response, allow_nan=False, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
