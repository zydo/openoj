import math
import struct
from typing import Any

from .base import ExecutorError


SUPPORTED_KINDS = {"integer", "number", "boolean", "string", "array"}


def type_spec(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("kind") not in SUPPORTED_KINDS:
        raise ExecutorError(f"{location} needs a supported value_type")
    kind = value["kind"]
    if kind == "integer" and value.get("bits", 32) not in {32, 64}:
        raise ExecutorError(f"{location} integer bits must be 32 or 64")
    if kind == "array":
        type_spec(value.get("items"), f"{location} array items")
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
        },
    )


def _render_type(spec: dict[str, Any], names: dict[str, str]) -> str:
    kind = spec["kind"]
    if kind == "integer":
        return names[f"integer{spec.get('bits', 32)}"]
    if kind == "array":
        return names["array"].format(item=_render_type(spec["items"], names))
    return names[kind]
