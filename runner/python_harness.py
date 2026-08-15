import contextlib
import importlib.util
import io
import json
import sys
import traceback
from pathlib import Path
from typing import Any

# The harness also runs with Python isolated mode. Only trusted modules baked
# into the read-only runner image are added; the submission directory is never
# placed on the import path.
sys.path.insert(0, "/runner")

from leetcode_types import (
    HtmlParser,
    ListNode,
    NestedInteger,
    Node,
    TreeNode,
    decode,
    encode,
)


PROTOCOL_PREFIX = "__OPENOJ_RESULT__"
MAX_CAPTURED_OUTPUT = 16_384


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


def _invoke_design(module, invocation: dict[str, Any], raw_input: Any) -> Any:
    actions = raw_input["actions"]
    params = raw_input["params"]
    if not actions or len(actions) != len(params):
        raise ValueError("Design input requires equally sized actions and params")
    instance = getattr(module, invocation["class_name"])(*params[0])
    output = [None]
    for action, arguments in zip(actions[1:], params[1:]):
        output.append(getattr(instance, action)(*arguments))
    return output


def _invoke(module, invocation: dict[str, Any], raw_input: Any) -> Any:
    invocation_type = invocation.get("type", "function")
    if invocation_type == "function":
        return _invoke_function(module, invocation, raw_input)
    if invocation_type == "design":
        return _invoke_design(module, invocation, raw_input)
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
    print(
        PROTOCOL_PREFIX + json.dumps(response, allow_nan=False, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
