import math
import struct
from typing import Any, Optional

from .base import ExecutorError


SUPPORTED_KINDS = {
    "integer", "number", "boolean", "string", "array", "linked_list", "binary_tree",
}


def type_spec(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("kind") not in SUPPORTED_KINDS:
        raise ExecutorError(f"{location} needs a supported value_type")
    kind = value["kind"]
    if kind == "integer" and value.get("bits", 32) not in {32, 64}:
        raise ExecutorError(f"{location} integer bits must be 32 or 64")
    if kind == "array":
        type_spec(value.get("items"), f"{location} array items")
    if kind in {"linked_list", "binary_tree"}:
        items = value.get("items")
        if not isinstance(items, dict) or items.get("kind") != "integer":
            raise ExecutorError(f"{location} {kind} items must be integers")
        type_spec(items, f"{location} {kind} items")
    return value


def function_signature(
    invocation: dict[str, Any], language: str
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    if invocation.get("type", "function") != "function":
        raise ExecutorError(f"{language} currently supports function problems only")
    parameters = invocation.get("parameters")
    if not isinstance(parameters, list):
        raise ExecutorError("Invocation parameters must be a list")
    parameter_types = [
        type_spec(parameter.get("value_type"), f"Parameter {index + 1}")
        for index, parameter in enumerate(parameters)
        if isinstance(parameter, dict)
    ]
    if len(parameter_types) != len(parameters):
        raise ExecutorError("Every invocation parameter must be an object")
    return_type = type_spec(invocation.get("return_type"), "Return value")
    entrypoints = invocation.get("entrypoints", {})
    method = entrypoints.get(language, invocation.get("method"))
    if not isinstance(method, str) or not method.isidentifier():
        raise ExecutorError(f"Invalid {language} entry point")
    return parameter_types, return_type, method


# --- interactive case transport -------------------------------------------
#
# Interactive cases are dict-shaped (oracle construction state, auxiliary
# method data), which the positional typed protocol above cannot express.
# They travel as a tagged stream: one byte of kind, then the value, so the
# per-language wrappers decode them with a generic reader and construct the
# problem-provided oracle (see docs/CODECS.md, invocation.provided.oracle).
TAG_NULL, TAG_FALSE, TAG_TRUE = 0x00, 0x01, 0x02
TAG_INT32, TAG_INT64, TAG_DOUBLE, TAG_STRING, TAG_ARRAY, TAG_OBJECT = 0x10, 0x11, 0x12, 0x13, 0x14, 0x15


def encode_tagged(value: Any, location: str = "value") -> bytes:
    if value is None:
        return bytes([TAG_NULL])
    if isinstance(value, bool):
        return bytes([TAG_TRUE if value else TAG_FALSE])
    if isinstance(value, int):
        if -(2 ** 31) <= value < 2 ** 31:
            return bytes([TAG_INT32]) + struct.pack(">i", value)
        if -(2 ** 63) <= value < 2 ** 63:
            return bytes([TAG_INT64]) + struct.pack(">q", value)
        raise ExecutorError(f"{location} exceeds the 64-bit range")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ExecutorError(f"{location} must be finite")
        return bytes([TAG_DOUBLE]) + struct.pack(">d", value)
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        return bytes([TAG_STRING]) + struct.pack(">I", len(encoded)) + encoded
    if isinstance(value, list):
        if len(value) > 0xFFFFFFFF:
            raise ExecutorError(f"{location} is too large")
        return (
            bytes([TAG_ARRAY])
            + struct.pack(">I", len(value))
            + b"".join(encode_tagged(item, f"{location}[{index}]") for index, item in enumerate(value))
        )
    if isinstance(value, dict):
        if len(value) > 0xFFFFFFFF:
            raise ExecutorError(f"{location} is too large")
        chunks = [bytes([TAG_OBJECT]), struct.pack(">I", len(value))]
        for key, item in value.items():
            if not isinstance(key, str):
                raise ExecutorError(f"{location} object keys must be strings")
            chunks.append(encode_tagged(key, f"{location} key"))
            chunks.append(encode_tagged(item, f"{location}[{key!r}]"))
        return b"".join(chunks)
    raise ExecutorError(f"{location} has unsupported type {type(value).__name__}")


def encode_interactive_case(
    invocation: dict[str, Any], case_input: Any
) -> bytes:
    """Encode one interactive case: each manifest key's value, tagged, in
    construct-then-auxiliary order, then the query budget as int64."""
    provided = (invocation.get("provided") or {}).get("oracle")
    if not isinstance(case_input, dict):
        raise ExecutorError("Interactive input must be an object")
    if not isinstance(provided, dict):
        raise ExecutorError("Interactive problems must carry invocation.provided.oracle")
    budget = int(invocation.get("query_limit", 1_000_000))
    chunks = []
    for key in [*provided.get("construct", ()), *provided.get("auxiliary", ())]:
        if key not in case_input:
            raise ExecutorError(f"Interactive input needs {key!r}")
        chunks.append(encode_tagged(case_input[key], key))
    chunks.append(encode_tagged(budget, "query budget"))
    return b"".join(chunks)


def encode_case(invocation: dict[str, Any], case_input: Any, language: str) -> bytes:
    parameter_types, _, _ = function_signature(invocation, language)
    if not isinstance(case_input, list) or len(case_input) != len(parameter_types):
        raise ExecutorError("Function input does not match the typed signature")
    return b"".join(
        _encode_value(value, spec, f"Argument {index + 1}")
        for index, (value, spec) in enumerate(
            zip(case_input, parameter_types, strict=True)
        )
    )


def _encode_value(value: Any, spec: dict[str, Any], location: str) -> bytes:
    kind = spec["kind"]
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ExecutorError(f"{location} must be an integer")
        bits = int(spec.get("bits", 32))
        minimum = -(2 ** (bits - 1))
        maximum = 2 ** (bits - 1) - 1
        if not minimum <= value <= maximum:
            raise ExecutorError(f"{location} exceeds the signed {bits}-bit range")
        return struct.pack(">i" if bits == 32 else ">q", value)
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ExecutorError(f"{location} must be a number")
        converted = float(value)
        if not math.isfinite(converted):
            raise ExecutorError(f"{location} must be finite")
        return struct.pack(">d", converted)
    if kind == "boolean":
        if not isinstance(value, bool):
            raise ExecutorError(f"{location} must be a boolean")
        return b"\x01" if value else b"\x00"
    if kind == "string":
        if not isinstance(value, str):
            raise ExecutorError(f"{location} must be a string")
        encoded = value.encode("utf-8")
        if len(encoded) > 0xFFFFFFFF:
            raise ExecutorError(f"{location} is too large")
        return struct.pack(">I", len(encoded)) + encoded
    if kind == "array":
        if not isinstance(value, list) or len(value) > 0xFFFFFFFF:
            raise ExecutorError(f"{location} must be an array")
        return struct.pack(">I", len(value)) + b"".join(
            _encode_value(item, spec["items"], f"{location}[{index}]")
            for index, item in enumerate(value)
        )
    if kind == "linked_list":
        if value is None:
            return b"\x00"
        if not isinstance(value, list) or len(value) > 0xFFFFFFFF:
            raise ExecutorError(f"{location} must be an array or null")
        return (
            b"\x01"
            + struct.pack(">I", len(value))
            + b"".join(
                _encode_value(item, spec["items"], f"{location}[{index}]")
                for index, item in enumerate(value)
            )
        )
    if kind == "binary_tree":
        if not isinstance(value, list) or len(value) > 0xFFFFFFFF:
            raise ExecutorError(f"{location} must be a level-order array")
        chunks = [struct.pack(">I", len(value))]
        for index, item in enumerate(value):
            if item is None:
                chunks.append(b"\x00")
            else:
                chunks.append(b"\x01")
                chunks.append(
                    _encode_value(item, spec["items"], f"{location}[{index}]")
                )
        return b"".join(chunks)
    raise ExecutorError(f"Unsupported type at {location}")


def cpp_type(spec: dict[str, Any]) -> str:
    return _render_type(
        spec,
        {
            "integer32": "int",
            "integer64": "long long",
            "number": "double",
            "boolean": "bool",
            "string": "std::string",
            "array": "std::vector<{item}>",
            "linked_list": "ListNode*",
            "binary_tree": "TreeNode*",
        },
    )


def typescript_type(spec: dict[str, Any]) -> str:
    return _render_type(
        spec,
        {
            "integer32": "number",
            "integer64": "number",
            "number": "number",
            "boolean": "boolean",
            "string": "string",
            "array": "Array<{item}>",
            "linked_list": "ListNode | null",
            "binary_tree": "TreeNode | null",
        },
    )


def go_type(spec: dict[str, Any]) -> str:
    return _render_type(
        spec,
        {
            "integer32": "int",
            "integer64": "int64",
            "number": "float64",
            "boolean": "bool",
            "string": "string",
            "array": "[]{item}",
            "linked_list": "*ListNode",
            "binary_tree": "*TreeNode",
        },
    )


def rust_type(spec: dict[str, Any]) -> str:
    return _render_type(
        spec,
        {
            "integer32": "i32",
            "integer64": "i64",
            "number": "f64",
            "boolean": "bool",
            "string": "String",
            "array": "Vec<{item}>",
            "linked_list": "Option<Box<ListNode>>",
            "binary_tree": "Option<Box<TreeNode>>",
        },
    )


def uses_struct_kinds(invocation: dict[str, Any]) -> set[str]:
    """Report which LeetCode structures an invocation needs defined."""
    specs = [parameter.get("value_type") for parameter in invocation.get("parameters", [])]
    specs.append(invocation.get("return_type"))
    found = set()

    def walk(spec: Any) -> None:
        if not isinstance(spec, dict):
            return
        if spec.get("kind") == "linked_list":
            found.add("list")
        elif spec.get("kind") == "binary_tree":
            found.add("tree")
        elif spec.get("kind") == "array":
            walk(spec.get("items"))

    for spec in specs:
        walk(spec)
    return found


def struct_item_spec(invocation: dict[str, Any]) -> dict[str, Any]:
    """Return the integer item spec shared by the invocation's struct kinds."""
    specs = [parameter.get("value_type") for parameter in invocation.get("parameters", [])]
    specs.append(invocation.get("return_type"))

    def walk(spec: Any) -> Optional[dict[str, Any]]:
        if not isinstance(spec, dict):
            return None
        if spec.get("kind") in {"linked_list", "binary_tree"}:
            return spec.get("items")
        if spec.get("kind") == "array":
            return walk(spec.get("items"))
        return None

    for spec in specs:
        items = walk(spec)
        if items is not None:
            return items
    return {"kind": "integer", "bits": 32}


def _render_type(spec: dict[str, Any], names: dict[str, str]) -> str:
    kind = spec["kind"]
    if kind == "integer":
        return names[f"integer{spec.get('bits', 32)}"]
    if kind == "array":
        return names["array"].format(item=_render_type(spec["items"], names))
    return names[kind]
