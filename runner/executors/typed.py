import math
import re
import struct
from typing import Any, Optional

from .base import ExecutorError


SUPPORTED_KINDS = {
    "integer", "number", "boolean", "string", "array", "linked_list", "binary_tree",
    # Pointer-wired and recursive-union structures: every kind names a fixed
    # class the judge either emits (pre-assembly jobs) or assembles from the
    # bank's common library, plus a wire format in docs/CODECS.md.
    "nary_tree", "quad_tree", "nested", "next_tree", "circular_list",
    "doubly_circular", "multi_list", "alias_list", "graph", "random_list",
    "struct",
}


def type_spec(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("kind") not in SUPPORTED_KINDS:
        raise ExecutorError(f"{location} needs a supported value_type")
    kind = value["kind"]
    if kind == "integer" and value.get("bits", 32) not in {32, 64}:
        raise ExecutorError(f"{location} integer bits must be 32 or 64")
    if kind == "array":
        type_spec(value.get("items"), f"{location} array items")
    if kind in {"linked_list", "binary_tree", "nary_tree", "next_tree",
                "circular_list", "doubly_circular", "alias_list", "multi_list",
                "graph", "random_list"}:
        items = value.get("items")
        if items is None:
            # Node payloads are 32-bit integers throughout the judge's
            # common types; manifests may omit the implied items spec
            # (every codec-driven path — the harnesses — never needed it).
            items = {"kind": "integer", "bits": 32}
            value = {**value, "items": items}
        if not isinstance(items, dict) or items.get("kind") != "integer":
            raise ExecutorError(f"{location} {kind} items must be integers")
        type_spec(items, f"{location} {kind} items")
    if kind == "alias_list":
        alias = value.get("alias")
        if not isinstance(alias, int) or isinstance(alias, bool) or alias < 0:
            raise ExecutorError(f"{location} alias_list needs a non-negative 'alias' parameter index")
    if kind in {"graph", "random_list"} and value.get("class") is not None:
        class_name = value.get("class")
        if not isinstance(class_name, str) or not class_name.isidentifier():
            raise ExecutorError(f"{location} {kind} 'class' must be an identifier")
    if kind == "struct":
        class_name = value.get("class")
        if not isinstance(class_name, str) or not class_name.isidentifier():
            raise ExecutorError(f"{location} struct needs a 'class' identifier")
        fields = value.get("fields")
        if not isinstance(fields, list) or not fields:
            raise ExecutorError(f"{location} struct needs a non-empty 'fields' list")
        for index, field in enumerate(fields):
            if not isinstance(field, dict) or not isinstance(field.get("name"), str) or not field["name"].isidentifier():
                raise ExecutorError(f"{location} struct field {index + 1} needs an identifier name")
            type_spec(field.get("value_type"), f"{location} field {field['name']}")
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
    for index, spec in enumerate(parameter_types):
        if spec["kind"] != "alias_list":
            continue
        if spec["alias"] >= index:
            raise ExecutorError(f"Parameter {index + 1} alias_list must reference an earlier parameter")
        if parameter_types[spec["alias"]]["kind"] != "linked_list":
            raise ExecutorError(f"Parameter {index + 1} alias_list must splice into a linked_list parameter")
    return_type = type_spec(invocation.get("return_type"), "Return value")
    if return_type["kind"] == "struct":
        # Struct values never cross back (input-only wire for now); an
        # alias_list return is fine — the wrapper serializes the shared
        # tail from the node the solution returns.
        raise ExecutorError(f"{language} does not support struct return values")
    entrypoints = invocation.get("entrypoints", {})
    method = entrypoints.get(language, invocation.get("method"))
    if language == "rust" and "rust" not in entrypoints:
        # No declared Rust entrypoint: mirror the starter generator, which
        # renders the method in snake_case for the `impl Solution` fragment.
        method = re.sub(r"(?<!^)(?=[A-Z])", "_", str(method)).lower()
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
    if kind in {"nary_tree", "next_tree"}:
        # Level order with a separator entry after each node's children
        # (the LeetCode n-ary / next-connected display); the same slot bytes
        # as binary_tree, different decode semantics.
        if not isinstance(value, list) or len(value) > 0xFFFFFFFF:
            raise ExecutorError(f"{location} must be a display array")
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
    if kind == "quad_tree":
        # LC display wire: a flat preorder of [isLeaf, val] pairs. The
        # binary form carries the same preorder one flag per node, so the
        # encoder walks the pairs in order.
        if value is None:
            return b"\x00"
        if not isinstance(value, list):
            raise ExecutorError(f"{location} must be a display array")

        position = 0

        def encode_node() -> bytes:
            nonlocal position
            if position >= len(value):
                raise ExecutorError(f"{location} wire ended without a node")
            pair = value[position]
            position += 1
            if not isinstance(pair, list) or len(pair) != 2:
                raise ExecutorError(f"{location} node must be an [isLeaf, val] pair")
            is_leaf, node_val = pair
            # LC display writes 0/1; accept the numbers as the harnesses do.
            if is_leaf not in (True, False, 0, 1) or node_val not in (True, False, 0, 1):
                raise ExecutorError(f"{location} isLeaf/val must be booleans")
            is_leaf, node_val = bool(is_leaf), bool(node_val)
            chunks = [b"\x01", b"\x01" if is_leaf else b"\x00", b"\x01" if node_val else b"\x00"]
            if not is_leaf:
                for side in ("topLeft", "topRight", "bottomLeft", "bottomRight"):
                    chunks.append(encode_node())
            return b"".join(chunks)

        encoded = encode_node()
        if position != len(value):
            raise ExecutorError(f"{location} wire has trailing entries")
        return encoded
    if kind == "nested":
        # 0x01 + integer hold, or 0x02 + list hold.
        if isinstance(value, bool):
            raise ExecutorError(f"{location} must be an integer or a nested array")
        if isinstance(value, int):
            return b"\x01" + _encode_value(value, {"kind": "integer", "bits": 32}, location)
        if isinstance(value, list):
            if len(value) > 0xFFFFFFFF:
                raise ExecutorError(f"{location} is too large")
            return (
                b"\x02"
                + struct.pack(">I", len(value))
                + b"".join(
                    _encode_value(item, spec, f"{location}[{index}]")
                    for index, item in enumerate(value)
                )
            )
        raise ExecutorError(f"{location} must be an integer or a nested array")
    if kind in {"circular_list", "doubly_circular"}:
        if value is None:
            return struct.pack(">I", 0)
        if not isinstance(value, list) or len(value) > 0xFFFFFFFF:
            raise ExecutorError(f"{location} must be an array of values or null")
        return struct.pack(">I", len(value)) + b"".join(
            _encode_value(item, spec["items"], f"{location}[{index}]")
            for index, item in enumerate(value)
        )
    if kind == "alias_list":
        # Same value slots as linked_list for the prefix, then the splice
        # index: the tail continues at the aliased parameter's node
        # `splice_at` (the LC 160 wire).
        if (
            not isinstance(value, dict)
            or set(value) != {"values", "splice_at"}
        ):
            raise ExecutorError(
                f"{location} must be an object with values and splice_at"
            )
        prefix = value["values"]
        splice_at = value["splice_at"]
        if not isinstance(prefix, list) or len(prefix) > 0xFFFFFFFF:
            raise ExecutorError(f"{location}.values must be an array or null")
        if (
            isinstance(splice_at, bool)
            or not isinstance(splice_at, int)
            or not 0 <= splice_at <= 0xFFFFFFFF
        ):
            raise ExecutorError(f"{location}.splice_at must be a non-negative integer")
        return (
            struct.pack(">I", len(prefix))
            + b"".join(
                _encode_value(item, spec["items"], f"{location}.values[{index}]")
                for index, item in enumerate(prefix)
            )
            + struct.pack(">I", splice_at)
        )
    if kind == "multi_list":
        # A recursive chain object {"values": [...], "children": [null |
        # chain per slot]}: each child chain hangs off exactly one slot, so
        # the LC 430 multilevel structure is unambiguous. Wire: u32 n; per
        # node i32 val, u8 child flag, then the child chain when flagged.
        if not isinstance(value, dict) or set(value) != {"values", "children"}:
            raise ExecutorError(
                f"{location} must be an object with values and children"
            )
        values, children = value["values"], value["children"]
        if not isinstance(values, list) or len(values) > 0xFFFFFFFF:
            raise ExecutorError(f"{location}.values must be an array")
        if not isinstance(children, list) or len(children) != len(values):
            raise ExecutorError(
                f"{location}.children must match values slot for slot"
            )
        chunks = [struct.pack(">I", len(values))]
        item_spec = {"kind": "integer", "bits": 32}
        for index, (val, child) in enumerate(zip(values, children)):
            if isinstance(val, bool) or not isinstance(val, int):
                raise ExecutorError(f"{location}.values[{index}] must be an integer")
            chunks.append(struct.pack(">i", val))
            if child is None:
                chunks.append(b"\x00")
            else:
                chunks.append(b"\x01")
                chunks.append(
                    _encode_value(child, spec, f"{location}.children[{index}]")
                )
        return b"".join(chunks)
    if kind == "graph":
        # Adjacency rows indexed by node (node val = index + 1).
        if not isinstance(value, list) or len(value) > 0xFFFFFFFF:
            raise ExecutorError(f"{location} must be an adjacency array")
        chunks = [struct.pack(">I", len(value))]
        for index, row in enumerate(value):
            if not isinstance(row, list) or len(row) > 0xFFFFFFFF:
                raise ExecutorError(f"{location}[{index}] must be a neighbor array")
            chunks.append(struct.pack(">I", len(row)))
            for neighbor_index, neighbor in enumerate(row):
                if isinstance(neighbor, bool) or not isinstance(neighbor, int) or not 1 <= neighbor <= len(value):
                    raise ExecutorError(f"{location}[{index}][{neighbor_index}] must be a node index")
                chunks.append(_encode_value(neighbor - 1, spec["items"], f"{location}[{index}][{neighbor_index}]"))
        return b"".join(chunks)
    if kind == "random_list":
        # [val, random index or null] rows; the index is 0-based within the
        # same list.
        if not isinstance(value, list) or len(value) > 0xFFFFFFFF:
            raise ExecutorError(f"{location} must be an array of [val, random] rows")
        chunks = [struct.pack(">I", len(value))]
        for index, row in enumerate(value):
            if not isinstance(row, list) or len(row) != 2:
                raise ExecutorError(f"{location}[{index}] must be a [val, random] pair")
            node_val, random_index = row
            chunks.append(_encode_value(node_val, spec["items"], f"{location}[{index}]"))
            if random_index is None:
                chunks.append(struct.pack(">I", 0xFFFFFFFF))
            else:
                if isinstance(random_index, bool) or not isinstance(random_index, int) or not 0 <= random_index < len(value):
                    raise ExecutorError(f"{location}[{index}] random index must be null or within the list")
                chunks.append(struct.pack(">I", random_index))
        return b"".join(chunks)
    if kind == "struct":
        fields = spec.get("fields") or []
        if not isinstance(value, list) or len(value) != len(fields):
            raise ExecutorError(f"{location} must be a record of {len(fields)} field values")
        return b"".join(
            _encode_value(field_value, field["value_type"], f"{location}.{field['name']}")
            for field, field_value in zip(fields, value)
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
            "linked_list": "ListNode*",
            "binary_tree": "TreeNode*",
            "nary_tree": "Node*",
            "quad_tree": "QuadNode*",
            "nested": "NestedInteger",
            "next_tree": "NodeWithNext*",
            "circular_list": "ListNode*",
            "doubly_circular": "NodeWithNext*",
            "multi_list": "MultiListNode*",
            "alias_list": "ListNode*",
            "graph": "Node*",
            "random_list": "Node*",
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
            "nary_tree": "Node | null",
            "quad_tree": "QuadNode | null",
            "nested": "NestedInteger",
            "next_tree": "NodeWithNext | null",
            "circular_list": "ListNode | null",
            "doubly_circular": "NodeWithNext | null",
            "multi_list": "MultiListNode | null",
            "alias_list": "ListNode | null",
            "graph": "Node | null",
            "random_list": "Node | null",
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
            "nary_tree": "*Node",
            "quad_tree": "*QuadNode",
            "nested": "NestedInteger",
            "next_tree": "*NodeWithNext",
            "circular_list": "*ListNode",
            "doubly_circular": "*NodeWithNext",
            "multi_list": "*MultiListNode",
            "alias_list": "*ListNode",
            "graph": "*Node",
            "random_list": "*Node",
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
            "nary_tree": "Option<Box<Node>>",
            "quad_tree": "Option<Box<QuadNode>>",
            "nested": "NestedInteger",
            # Kinds whose wire carries sharing — a next/prev/random pointer
            # two owners reach, or a ring closed onto its own head — render
            # as Rc<RefCell<>>: Box's single owner cannot express them.
            # QuadNode trees and NestedInteger stay fully owned. The paths
            # are fully qualified: this renderer feeds the wrapper, which
            # must not depend on a submission's `use` lines (common.rs
            # carries none either; starters may import the short names).
            "next_tree": "Option<std::rc::Rc<std::cell::RefCell<NodeWithNext>>>",
            "circular_list": "Option<std::rc::Rc<std::cell::RefCell<SharedListNode>>>",
            "doubly_circular": "Option<std::rc::Rc<std::cell::RefCell<NodeWithNext>>>",
            "multi_list": "Option<std::rc::Rc<std::cell::RefCell<MultiListNode>>>",
            "alias_list": "Option<std::rc::Rc<std::cell::RefCell<SharedListNode>>>",
            "graph": "Option<std::rc::Rc<std::cell::RefCell<Node>>>",
            "random_list": "Option<std::rc::Rc<std::cell::RefCell<Node>>>",
        },
    )


def rust_parameter_type(invocation: dict[str, Any], index: int, spec: dict[str, Any]) -> str:
    """The Rust type of one function parameter: an aliased linked_list
    renders as the shared-ownership node, since the alias_list reader
    splices real nodes between the lists."""
    if spec.get("kind") == "linked_list":
        aliased = set()
        for parameter in invocation.get("parameters", []):
            if not isinstance(parameter, dict):
                continue
            # Parameters appear raw ({name, value_type}) on the invocation
            # and flattened (kind/alias hoisted) once type_spec has run;
            # read the alias target from either shape.
            value_type = parameter.get("value_type")
            nested = value_type if isinstance(value_type, dict) else {}
            if parameter.get("kind", nested.get("kind")) == "alias_list":
                aliased.add(parameter.get("alias", nested.get("alias")))
        if index in aliased:
            return "Option<std::rc::Rc<std::cell::RefCell<SharedListNode>>>"
    return rust_type(spec)


def uses_struct_kinds(invocation: dict[str, Any]) -> set[str]:
    """Report which LeetCode structures an invocation needs defined."""
    specs = [parameter.get("value_type") for parameter in invocation.get("parameters", [])]
    specs.append(invocation.get("return_type"))
    found = set()

    def walk(spec: Any) -> None:
        if not isinstance(spec, dict):
            return
        kind = spec.get("kind")
        if kind == "linked_list":
            found.add("list")
        elif kind == "binary_tree":
            found.add("tree")
        elif kind in {
            "nary_tree", "quad_tree", "nested", "next_tree", "circular_list",
            "doubly_circular", "multi_list", "alias_list", "graph",
            "random_list", "struct",
        }:
            found.add(kind)
        elif kind == "array":
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


def provided_node_class(invocation: dict[str, Any], kind: str, default: str = "Node") -> str:
    """The class a graph or random_list value names in the wrapper and the
    starters: the using problem's provided/ source (LC 133/138 ship their
    own node class — the shared vocabulary deliberately does not carry
    one), falling back to the generic Node for legacy manifests."""
    specs = [parameter.get("value_type") for parameter in invocation.get("parameters", [])]
    specs.append(invocation.get("return_type"))
    for spec in specs:
        if isinstance(spec, dict) and spec.get("kind") == kind:
            class_name = spec.get("class")
            if isinstance(class_name, str) and class_name:
                return class_name
    return default


def _render_type(spec: dict[str, Any], names: dict[str, str]) -> str:
    kind = spec["kind"]
    if kind == "integer":
        return names[f"integer{spec.get('bits', 32)}"]
    if kind == "array":
        return names["array"].format(item=_render_type(spec["items"], names))
    if kind == "struct":
        # The class is the using problem's provided/ source; its bare name
        # is the type in every language.
        return str(spec["class"])
    if kind in {"graph", "random_list"} and isinstance(spec.get("class"), str) and spec["class"]:
        # Re-decorate the language's rendering around the provided name so
        # every pointer/reference wrapper keeps its shape.
        return names[kind].replace("Node", spec["class"])
    return names[kind]
