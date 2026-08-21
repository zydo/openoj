"""Design-kind wrapper generation for Rust.

Same protocol as js_design.py (reference: python_harness._invoke_design):
actions + params, instance from params[0], $prev piping, randomized
actions as frequency tables. The case travels as one tagged stream. The
wrapper decodes into the OjValue enum and replays through a generated
dispatch match calling typed methods, with per-spec converters identical
to the interactive module's. The submission's design class is a plain
struct with an inherent `new` constructor; the wrapper constructs it
from converted row values.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import ExecutorError, PreparedProgram
from .typed import rust_type, type_spec
from .rust_interactive import WRAPPER_HEAD, _convert, _rust_type

MAIN_TEMPLATE = """\
fn openoj_run() -> Result<String, String> {
    let mut raw = Vec::new();
    std::io::stdin().read_to_end(&mut raw).map_err(|e| e.to_string())?;
    let mut tagged = OjTaggedReader::new(raw);
    let actions_value = tagged.value()?;
    let params_value = tagged.value()?;
    let actions = match actions_value { OjValue::Array(v) => v, _ => return Err("Design actions must be a list".to_string()) };
    let params = match params_value { OjValue::Array(v) => v, _ => return Err("Design params must be a list".to_string()) };
    if actions.is_empty() || actions.len() != params.len() {
        return Err("Design input requires equally sized actions and params".to_string());
    }
    let constructor_row = match &params[0] { OjValue::Array(v) => v.clone(), _ => vec![] };
@CONSTRUCTOR_CONVERT@
    let mut solution = @CLASS_NAME@::new(@CONSTRUCTOR_ARGS@);
    let mut outputs: Vec<OjValue> = vec![OjValue::Null];
    let mut previous = OjValue::Null;
    for step in 1..actions.len() {
        let (name, repeat) = match &actions[step] {
            OjValue::Str(v) => (v.clone(), 1i64),
            OjValue::Object(fields) => {
                let mut call = String::new();
                let mut count = 1i64;
                for (key, item) in fields {
                    if key == "call" {
                        if let OjValue::Str(v) = item { call = v.clone(); }
                    }
                    if key == "repeat" {
                        if let OjValue::Int(v) = item { count = *v; }
                    }
                }
                (call, count)
            }
            _ => return Err("Design action must be a string".to_string()),
        };
        let raw_arguments = match &params[step] { OjValue::Array(v) => v.clone(), _ => vec![] };
        let mut call_arguments: Vec<OjValue> = Vec::with_capacity(raw_arguments.len());
        for argument in &raw_arguments {
            if let OjValue::Object(fields) = argument {
                if fields.len() == 1 && fields[0].0 == "$prev" {
                    call_arguments.push(previous.clone());
                    continue;
                }
            }
            call_arguments.push(argument.clone());
        }
        if repeat > 1 {
            let mut frequencies: std::collections::BTreeMap<String, i64> = std::collections::BTreeMap::new();
            for _trial in 0..repeat {
                let result = dispatch_@CLASS_NAME@(&mut solution, &name, &call_arguments)?;
                *frequencies.entry(openoj_json(&result)).or_insert(0) += 1;
            }
            let table = OjValue::Object(frequencies.into_iter().map(|(key, count)| {
                (key, OjValue::Int(count))
            }).collect());
            outputs.push(table.clone());
            previous = table;
        } else {
            let result = dispatch_@CLASS_NAME@(&mut solution, &name, &call_arguments)?;
            outputs.push(result.clone());
            previous = result;
        }
    }
    Ok(openoj_json(&OjValue::Array(outputs)))
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


def prepare_design(executor, job_root: Path, scratch: Path, code: str,
                   invocation: dict[str, Any], assembly) -> PreparedProgram:
    class_name = invocation.get("class_name", "Solution")
    if not isinstance(class_name, str) or not class_name.isidentifier():
        raise ExecutorError("Invalid design entry class")
    entrypoints = invocation.get("entrypoints") or {}
    constructor = invocation.get("constructor", {}).get("parameters", [])
    constructor_specs = [
        type_spec(p.get("value_type"), f"Constructor parameter {index + 1}")
        for index, p in enumerate(constructor)
    ]

    constructor_convert = []
    for index, spec in enumerate(constructor_specs):
        constructor_convert.append(
            f"    let openoj_ctor_{index}: {_rust_type(spec)} = {_convert(spec, f'&constructor_row[{index}]')};"
        )
    constructor_args = ", ".join(f"openoj_ctor_{index}" for index in range(len(constructor_specs)))

    dispatch_arms = []
    for method in invocation.get("methods", []):
        name = method.get("name")
        rust_name = entrypoints.get(f"rust.{name}", name)
        specs = [
            type_spec(p.get("value_type"), f"{name} parameter {index + 1}")
            for index, p in enumerate(method.get("parameters", []))
        ]
        args = ", ".join(
            _convert(spec, f"&call_arguments[{index}]") for index, spec in enumerate(specs)
        )
        dispatch_arms.append(f'        "{name}" => Ok(OjValue::oj_from(solution.{rust_name}({args}))),')
    dispatch = (
        f"fn dispatch_{class_name}(solution: &mut {class_name}, name: &str, call_arguments: &[OjValue]) -> Result<OjValue, String> {{\n"
        "    match name {\n"
        + "\n".join(dispatch_arms)
        + f'\n        _ => Err(format!("Unknown design method: {{}}", name)),\n    }}\n}}\n'
    )

    # Rust has no overloading: one trait, one generic call site
    oj_from = """
trait OjFrom<T> { fn oj_from(value: T) -> OjValue; }
impl OjFrom<i32> for OjValue { fn oj_from(value: i32) -> OjValue { OjValue::Int(value as i64) } }
impl OjFrom<i64> for OjValue { fn oj_from(value: i64) -> OjValue { OjValue::Int(value) } }
impl OjFrom<f64> for OjValue { fn oj_from(value: f64) -> OjValue { OjValue::Double(value) } }
impl OjFrom<bool> for OjValue { fn oj_from(value: bool) -> OjValue { OjValue::Bool(value) } }
impl OjFrom<String> for OjValue { fn oj_from(value: String) -> OjValue { OjValue::Str(value) } }
impl OjFrom<&str> for OjValue { fn oj_from(value: &str) -> OjValue { OjValue::Str(value.to_string()) } }
impl OjFrom<()> for OjValue { fn oj_from(_value: ()) -> OjValue { OjValue::Null } }
impl OjFrom<Vec<i32>> for OjValue { fn oj_from(values: Vec<i32>) -> OjValue { OjValue::Array(values.into_iter().map(|v| OjValue::Int(v as i64)).collect()) } }
impl OjFrom<Vec<i64>> for OjValue { fn oj_from(values: Vec<i64>) -> OjValue { OjValue::Array(values.into_iter().map(OjValue::Int).collect()) } }
impl OjFrom<Vec<String>> for OjValue { fn oj_from(values: Vec<String>) -> OjValue { OjValue::Array(values.into_iter().map(OjValue::Str).collect()) } }
"""

    provided_source = "".join(
        content + "\n"
        for part in ("common", "provided")
        for _, content in sorted((assembly or {}).get(part, {}).items())
        if _.endswith(".rs")
    )
    code = re.sub(r"^\s*(?:pub )?struct Solution;\s*$\n?", "", code, flags=re.M)

    source = (
        WRAPPER_HEAD + "\n" + oj_from + "\n" + provided_source + code + "\n"
        + dispatch + "\n"
        + (MAIN_TEMPLATE
           .replace("@CONSTRUCTOR_CONVERT@", "\n".join(constructor_convert))
           .replace("@CONSTRUCTOR_ARGS@", constructor_args)
           .replace("@CLASS_NAME@", class_name))
    )
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
