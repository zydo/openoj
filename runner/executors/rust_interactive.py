"""Rust wrapper generation for interactive problems.

Same contract as the C++ side (executors/cpp_interactive.py): one tagged
stream carries the whole case — a tagged value per oracle-construction
key, one per auxiliary method key, then the query budget. The wrapper
decodes them into an OjValue enum, converts auxiliary values to the
method's typed parameters with generated converters, and constructs the
problem-provided oracle (assembled into the same crate; its constructor
takes &[OjValue] slices plus the budget). Void methods are judged by the
oracle's verdict() OjValue.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .base import ExecutorError, PreparedProgram
from .typed import rust_type, type_spec

WRAPPER_HEAD = """\
use std::io::Read as OpenOJIoRead;

#[derive(Debug, Clone)]
pub enum OjValue {
    Null,
    Bool(bool),
    Int(i64),
    Double(f64),
    Str(String),
    Array(Vec<OjValue>),
    Object(Vec<(String, OjValue)>),
}

pub struct OjTaggedReader {
    bytes: Vec<u8>,
    position: usize,
}

impl OjTaggedReader {
    pub fn new(bytes: Vec<u8>) -> Self {
        OjTaggedReader { bytes, position: 0 }
    }
    fn byte(&mut self) -> Result<u8, String> {
        if self.position >= self.bytes.len() {
            return Err("Truncated case payload".to_string());
        }
        let value = self.bytes[self.position];
        self.position += 1;
        Ok(value)
    }
    fn u32(&mut self) -> Result<u32, String> {
        let mut value: u32 = 0;
        for _ in 0..4 {
            value = (value << 8) | self.byte()? as u32;
        }
        Ok(value)
    }
    fn i64(&mut self) -> Result<i64, String> {
        let mut value: u64 = 0;
        for _ in 0..8 {
            value = (value << 8) | self.byte()? as u64;
        }
        Ok(value as i64)
    }
    fn f64(&mut self) -> Result<f64, String> {
        let bits = self.i64()? as u64;
        Ok(f64::from_bits(bits))
    }
    fn str(&mut self) -> Result<String, String> {
        let length = self.u32()? as usize;
        let mut raw = Vec::with_capacity(length);
        for _ in 0..length {
            raw.push(self.byte()?);
        }
        Ok(String::from_utf8(raw).map_err(|_| "Invalid UTF-8 in case payload".to_string())?)
    }
    pub fn value(&mut self) -> Result<OjValue, String> {
        let tag = self.byte()?;
        match tag {
            0x00 => Ok(OjValue::Null),
            0x01 => Ok(OjValue::Bool(false)),
            0x02 => Ok(OjValue::Bool(true)),
            0x10 => Ok(OjValue::Int(self.u32()? as i32 as i64)),
            0x11 => Ok(OjValue::Int(self.i64()?)),
            0x12 => Ok(OjValue::Double(self.f64()?)),
            0x13 => Ok(OjValue::Str(self.str()?)),
            0x14 => {
                let count = self.u32()? as usize;
                let mut items = Vec::with_capacity(count);
                for _ in 0..count {
                    items.push(self.value()?);
                }
                Ok(OjValue::Array(items))
            }
            0x15 => {
                let count = self.u32()? as usize;
                let mut fields = Vec::with_capacity(count);
                for _ in 0..count {
                    let key = match self.value()? {
                        OjValue::Str(text) => text,
                        _ => return Err("Object keys must be strings".to_string()),
                    };
                    fields.push((key, self.value()?));
                }
                Ok(OjValue::Object(fields))
            }
            _ => Err("Unknown tagged value".to_string()),
        }
    }
}

fn openoj_json(value: &OjValue) -> String {
    match value {
        OjValue::Null => "null".to_string(),
        OjValue::Bool(v) => v.to_string(),
        OjValue::Int(v) => v.to_string(),
        OjValue::Double(v) => {
            if !v.is_finite() {
                panic!("Non-finite value");
            }
            format!("{}", v)
        }
        OjValue::Str(v) => {
            let mut out = String::with_capacity(v.len() + 2);
            out.push('"');
            for c in v.chars() {
                match c {
                    '"' => out.push_str("\\\\\\""),
                    '\\\\' => out.push_str("\\\\\\\\"),
                    c if (c as u32) < 0x20 => out.push_str(&format!("\\\\u{:04x}", c as u32)),
                    c => out.push(c),
                }
            }
            out.push('"');
            out
        }
        OjValue::Array(items) => {
            let parts: Vec<String> = items.iter().map(openoj_json).collect();
            format!("[{}]", parts.join(","))
        }
        OjValue::Object(fields) => {
            let parts: Vec<String> = fields
                .iter()
                .map(|(key, item)| format!("\\"{}\\":{}", key, openoj_json(item)))
                .collect();
            format!("{{{}}}", parts.join(","))
        }
    }
}

fn openojEmit(line: &str) {
    use std::io::Write;
    use std::os::unix::io::FromRawFd;
    let mut channel = unsafe { std::fs::File::from_raw_fd(63) };
    if write!(channel, "{}\n", line).is_ok() {
        return;
    }
    println!("{}", line);
}

fn openoj_json_i32(value: i32) -> String { value.to_string() }
fn openoj_json_i64(value: i64) -> String { value.to_string() }
fn openoj_json_f64(value: f64) -> String {
    if !value.is_finite() {
        panic!("Non-finite return value");
    }
    format!("{}", value)
}
fn openoj_json_str(value: &str) -> String { openoj_json(&OjValue::Str(value.to_string())) }
fn openoj_json_bool(value: bool) -> String { value.to_string() }
"""

MAIN_TEMPLATE = """\
fn openoj_run() -> Result<String, String> {
    let mut raw = Vec::new();
    std::io::stdin().read_to_end(&mut raw).map_err(|e| e.to_string())?;
    let mut tagged = OjTaggedReader::new(raw);
@VALUE_READS@
    let budget = match tagged.value()? {
        OjValue::Int(v) => v,
        _ => return Err("Budget must be an integer".to_string()),
    };
@CONVERT_LINES@
    let mut oracle = @ORACLE_CLASS@::new(&[@ORACLE_ARGS@], budget);
@CALL_BLOCK@
}

fn main() {
    let response = std::panic::catch_unwind(openoj_run);
    match response {
        Ok(Ok(actual)) => openojEmit(&format!("__OPENOJ_RESULT__{{\\"status\\":\\"completed\\",\\"actual\\":{}}}", actual)),
        Ok(Err(error)) => openojEmit(&format!("__OPENOJ_RESULT__{{\\"status\\":\\"runtime_error\\",\\"error\\":{}}}", openoj_json(&OjValue::Str(error)))),
        Err(_) => openojEmit("__OPENOJ_RESULT__{{\\"status\\":\\"runtime_error\\",\\"error\\":\\"Solution panicked\\"}}"),
    }
}
"""


def _rust_type(spec: dict[str, Any]) -> str:
    return rust_type(spec)


def _convert(spec: dict[str, Any], source: str) -> str:
    """Conversion expression turning a `&OjValue` (`source`) into the spec's
    Rust type. Matching a reference flips the default binding mode to by-ref,
    so `items` borrows and the `for item in items` loop hands the recursive
    call another `&OjValue` — any nesting depth works without moving out of
    the borrowed wrapper values."""
    kind = spec["kind"]
    if kind == "integer":
        bits = spec.get("bits", 32)
        target = "i64" if bits == 64 else "i32"
        return (
            f"(match {source} {{ OjValue::Int(v) => {target}::try_from(*v).map_err(|_| {{ \"Integer out of range\".to_string() }})?, "
            f"_ => return Err(\"Expected an integer\".to_string()) }})"
        )
    if kind == "number":
        return (
            f"(match {source} {{ OjValue::Double(v) => *v, OjValue::Int(v) => *v as f64, "
            f"_ => return Err(\"Expected a number\".to_string()) }})"
        )
    if kind == "boolean":
        return f"(match {source} {{ OjValue::Bool(v) => *v, _ => return Err(\"Expected a boolean\".to_string()) }})"
    if kind == "string":
        return (
            f"(match {source} {{ OjValue::Str(v) => v.clone(), _ => return Err(\"Expected a string\".to_string()) }})"
        )
    if kind == "array":
        inner = _convert(spec["items"], "item")
        return (
            f"(match {source} {{ OjValue::Array(items) => {{ let mut out: Vec<{_rust_type(spec['items'])}> = Vec::with_capacity(items.len()); "
            f"for item in items {{ out.push({inner}); }} out }}, "
            f"_ => return Err(\"Expected an array\".to_string()) }})"
        )
    raise ExecutorError(f"Interactive auxiliary type {kind} is not supported in Rust")


def prepare_interactive(executor, job_root: Path, scratch: Path, code: str,
                        invocation: dict[str, Any], assembly) -> PreparedProgram:
    provided = (invocation.get("provided") or {}).get("oracle")
    if not provided:
        raise ExecutorError("Interactive problems must carry invocation.provided.oracle")
    oracle_class = provided.get("class")
    method = (invocation.get("entrypoints", {}) or {}).get("rust", invocation.get("method"))
    if not isinstance(method, str) or not method.isidentifier():
        raise ExecutorError("Invalid Rust entry point")
    construct_keys = list(provided.get("construct", ()))
    auxiliary_keys = list(provided.get("auxiliary", ()))
    parameters = invocation.get("parameters") or []
    specs = {
        parameter.get("name"): parameter.get("value_type")
        for parameter in parameters
        if isinstance(parameter, dict)
    }

    value_reads = "\n".join(
        f"    let openoj_value_{index} = tagged.value()?;" for index in range(len(construct_keys) + len(auxiliary_keys))
    )
    convert_lines = []
    auxiliary_args = []
    for index, key in enumerate(auxiliary_keys):
        spec = specs.get(key)
        if spec is None:
            raise ExecutorError(f"Auxiliary key {key!r} has no invocation parameter type")
        spec = type_spec(spec, key)
        convert_lines.append(
            f"    let openoj_aux_{index}: {_rust_type(spec)} = {_convert(spec, f'&openoj_value_{len(construct_keys) + index}')};"
        )
        auxiliary_args.append(f"openoj_aux_{index}")

    oracle_args = ", ".join(
        f"openoj_value_{index}.clone()" for index in range(len(construct_keys))
    )
    call_arguments = ", ".join(["&mut oracle", *auxiliary_args])
    # A {"kind": "void"} return_type is a declared void, not a value: the
    # oracle's verdict() judges those (same rule as the python/java sides).
    has_return = bool(invocation.get("return_type")) and invocation["return_type"].get("kind") != "void"
    if has_return:
        call_block = (
            f"    let actual = Solution::{method}({call_arguments});\n"
            '    Ok(openoj_json_i32(actual))'
        )
    else:
        call_block = (
            f"    Solution::{method}({call_arguments});\n"
            '    Ok(openoj_json(&oracle.verdict()))'
        )

    provided_source = "".join(
        content + "\n"
        for part in ("common", "provided")
        for _, content in sorted((assembly or {}).get(part, {}).items())
        if _.endswith(".rs")
    )
    # The bank's Rust submissions are `impl Solution` blocks without a
    # struct declaration; the wrapper owns the unit struct.
    code = re.sub(r"^\s*pub struct Solution;\s*$\n?", "", code, flags=re.M)
    code = "pub struct Solution;\n" + code
    main_source = (
        MAIN_TEMPLATE
        .replace("@VALUE_READS@", value_reads)
        .replace("@CONVERT_LINES@", "\n".join(convert_lines))
        .replace("@ORACLE_CLASS@", oracle_class)
        .replace("@ORACLE_ARGS@", oracle_args)
        .replace("@CALL_BLOCK@", call_block)
    )
    source = WRAPPER_HEAD + "\n" + provided_source + code + "\n" + main_source
    source_path = job_root / "main.rs"
    executable = job_root / "solution"
    source_path.write_text(source, encoding="utf-8")
    source_path.chmod(0o444)
    executor.compile(
        job_root,
        (executor.compiler_path, "--edition=2021", "-C", "opt-level=2", "-C", "debuginfo=0",
         "-o", str(executable), str(source_path)),
        executable,
        {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "TMPDIR": "/tmp", "LANG": "C.UTF-8"},
    )
    return PreparedProgram(
        command=(str(executable),),
        environment={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "TMPDIR": str(scratch), "LANG": "C.UTF-8"},
    )
