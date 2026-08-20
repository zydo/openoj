"""Go wrapper generation for interactive problems.

Same contract as the C++ side (executors/cpp_interactive.py): one tagged
stream carries the whole case — a tagged value per oracle-construction
key, one per auxiliary method key, then the query budget. Go's
interface{} makes the generic layer trivial; the problem-provided oracle
(a `package main` source beside the wrapper) takes the construction
values as []any plus the budget, and the wrapper converts auxiliary
values to the method's typed parameters with generated converters.
Void methods are judged by the oracle's Verdict() any.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import ExecutorError, PreparedProgram
from .typed import go_type, type_spec

WRAPPER_HEAD = """\
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"unsafe"
)

func openojEmit(line string) {
	if channel := os.NewFile(63, "protocol"); channel != nil {
		if _, errorValue := channel.WriteString(line + "\\n"); errorValue == nil {
			return
		}
	}
	fmt.Println(line)
}

// The tagged generic reader: interactive case state arrives in this
// shape so no per-oracle schema lives in the judge.
type ojReader struct {
	bytes   []byte
	position int
}

func (r *ojReader) byte() byte {
	if r.position >= len(r.bytes) {
		panic("Truncated case payload")
	}
	value := r.bytes[r.position]
	r.position++
	return value
}

func (r *ojReader) u32() uint32 {
	var value uint32
	for i := 0; i < 4; i++ {
		value = (value << 8) | uint32(r.byte())
	}
	return value
}

func (r *ojReader) i64() int64 {
	var value uint64
	for i := 0; i < 8; i++ {
		value = (value << 8) | uint64(r.byte())
	}
	return int64(value)
}

func (r *ojReader) f64() float64 {
	bits := uint64(r.i64())
	return float64FromBits(bits)
}

func float64FromBits(bits uint64) float64 {
	return *(*float64)(unsafe.Pointer(&bits))
}

func (r *ojReader) str() string {
	length := r.u32()
	value := make([]byte, length)
	for i := range value {
		value[i] = r.byte()
	}
	return string(value)
}

func (r *ojReader) value() any {
	tag := r.byte()
	switch tag {
	case 0x00:
		return nil
	case 0x01:
		return false
	case 0x02:
		return true
	case 0x10:
		return int64(int32(r.u32()))
	case 0x11:
		return r.i64()
	case 0x12:
		return r.f64()
	case 0x13:
		return r.str()
	case 0x14:
		count := r.u32()
		items := make([]any, 0, count)
		for i := uint32(0); i < count; i++ {
			items = append(items, r.value())
		}
		return items
	case 0x15:
		count := r.u32()
		object := make(map[string]any, count)
		for i := uint32(0); i < count; i++ {
			key := r.value().(string)
			object[key] = r.value()
		}
		return object
	default:
		panic("Unknown tagged value")
	}
}
"""

MAIN_TEMPLATE = """\
func main() {
	defer func() {
		if problem := recover(); problem != nil {
			openojEmit("__OPENOJ_RESULT__" + fmt.Sprintf(`{"status":"runtime_error","error":"%v"}`, problem))
		}
	}()
	bytes_ := make([]byte, 0, 4096)
	buffer := make([]byte, 4096)
	for {
		n, errorValue := os.Stdin.Read(buffer)
		bytes_ = append(bytes_, buffer[:n]...)
		if errorValue != nil {
			break
		}
	}
	reader := &ojReader{bytes: bytes_}
@VALUE_READS@
	budgetValue := reader.value()
	budget, budgetOk := budgetValue.(int64)
	if !budgetOk {
		panic("Budget must be an integer")
	}
@CONVERT_LINES@
	solution := &@CLASS_NAME@{}
	oracle := New@ORACLE_CLASS@([]any{@ORACLE_ARGS@}, budget)
@CALL_BLOCK@
}
"""

JSON_HELPER = """\
func openojJSON(value any) string {
	encoded, errorValue := json.Marshal(value)
	if errorValue != nil {
		panic(errorValue)
	}
	return string(encoded)
}
"""


def strip_package(source: str) -> str:
    """The submission arrives as its own `package main` file; inside the
    assembled wrapper the package clause is dropped."""
    lines = [line for line in source.splitlines() if not line.strip().startswith("package ")]
    return "\n".join(lines)


def _go_type(spec: dict[str, Any]) -> str:
    return go_type(spec)


def _convert(spec: dict[str, Any], source: str) -> str:
    kind = spec["kind"]
    if kind == "integer":
        bits = spec.get("bits", 32)
        if bits == 64:
            return f'(func() int64 {{ v, ok := {source}.(int64); if !ok {{ panic("Expected an integer") }}; return v }})()'
        return f'(func() int {{ v, ok := {source}.(int64); if !ok {{ panic("Expected an integer") }}; return int(v) }})()'
    if kind == "number":
        return f'(func() float64 {{ switch v := {source}.(type) {{ case float64: return v; case int64: return float64(v); default: panic("Expected a number") }} }})()'
    if kind == "boolean":
        return f'(func() bool {{ v, ok := {source}.(bool); if !ok {{ panic("Expected a boolean") }}; return v }})()'
    if kind == "string":
        return f'(func() string {{ v, ok := {source}.(string); if !ok {{ panic("Expected a string") }}; return v }})()'
    if kind == "array":
        inner = _convert(spec["items"], "item")
        return (
            f'(func() []{_go_type(spec["items"])} {{ source, ok := {source}.([]any); if !ok {{ panic("Expected an array") }}; '
            f'out := make([]{_go_type(spec["items"])}, 0, len(source)); '
            f'for _, item := range source {{ out = append(out, {inner}) }}; return out }})()'
        )
    raise ExecutorError(f"Interactive auxiliary type {kind} is not supported in Go")


def prepare_interactive(executor, job_root: Path, scratch: Path, code: str,
                        invocation: dict[str, Any], assembly) -> PreparedProgram:
    provided = (invocation.get("provided") or {}).get("oracle")
    if not provided:
        raise ExecutorError("Interactive problems must carry invocation.provided.oracle")
    oracle_class = provided.get("class")
    method = (invocation.get("entrypoints", {}) or {}).get("go", invocation.get("method"))
    if not isinstance(method, str) or not method.isidentifier():
        raise ExecutorError("Invalid Go entry point")
    construct_keys = list(provided.get("construct", ()))
    auxiliary_keys = list(provided.get("auxiliary", ()))
    parameters = invocation.get("parameters") or []
    specs = {
        parameter.get("name"): parameter.get("value_type")
        for parameter in parameters
        if isinstance(parameter, dict)
    }

    value_reads = "\n".join(
        f"\topenojValue{index} := reader.value()" for index in range(len(construct_keys) + len(auxiliary_keys))
    )
    convert_lines = []
    auxiliary_args = []
    for index, key in enumerate(auxiliary_keys):
        spec = specs.get(key)
        if spec is None:
            raise ExecutorError(f"Auxiliary key {key!r} has no invocation parameter type")
        spec = type_spec(spec, key)
        convert_lines.append(
            f"\topenojAux{index} := {_convert(spec, f'openojValue{len(construct_keys) + index}')}"
        )
        auxiliary_args.append(f"openojAux{index}")

    oracle_args = ", ".join(
        [f"openojValue{index}" for index in range(len(construct_keys))]
    )
    call_arguments = ", ".join(["oracle", *auxiliary_args])
    has_return = bool(invocation.get("return_type"))
    if has_return:
        call_block = (
            f"\tactual := solution.{method}({call_arguments})\n"
            '\topenojEmit("__OPENOJ_RESULT__" + fmt.Sprintf(`{"status":"completed","actual":%s}`, openojJSON(actual)))'
        )
    else:
        call_block = (
            f"\tsolution.{method}({call_arguments})\n"
            '\topenojEmit("__OPENOJ_RESULT__" + fmt.Sprintf(`{"status":"completed","actual":%s}`, openojJSON(oracle.Verdict())))'
        )

    provided_files = []
    for part in ("common", "provided"):
        for name, content in sorted((assembly or {}).get(part, {}).items()):
            if name.endswith(".go"):
                provided_files.append((name, content))

    main_source = (
        MAIN_TEMPLATE
        .replace("@VALUE_READS@", value_reads)
        .replace("@CONVERT_LINES@", "\n".join(convert_lines))
        .replace("@CLASS_NAME@", invocation.get("class_name", "Solution"))
        .replace("@ORACLE_CLASS@", oracle_class)
        .replace("@ORACLE_ARGS@", oracle_args)
        .replace("@CALL_BLOCK@", call_block)
    )

    wrapper = job_root / "main.go"
    wrapper.write_text(
        WRAPPER_HEAD + "\n" + JSON_HELPER + "\n" + strip_package(code) + "\n" + main_source,
        encoding="utf-8",
    )
    wrapper.chmod(0o444)
    for name, content in provided_files:
        part_path = job_root / f"assembly_{name}"
        part_path.write_text(content, encoding="utf-8")
        part_path.chmod(0o444)

    executable = job_root / "solution"
    executor.compile(
        job_root,
        (executor.compiler_path, "build", "-trimpath", "-ldflags=-s -w", "-o", str(executable), str(wrapper),
         *[str(job_root / f"assembly_{name}") for name, _ in provided_files]),
        executable,
        {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "TMPDIR": "/tmp", "LANG": "C.UTF-8", "GOCACHE": "/tmp/gocache", "GOPATH": "/tmp/gopath", "GOMODCACHE": "/tmp/gomodcache", "GOFLAGS": "-mod=mod", "GO111MODULE": "off"},
    )
    return PreparedProgram(
        command=(str(executable),),
        environment={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "TMPDIR": str(scratch), "LANG": "C.UTF-8"},
    )
