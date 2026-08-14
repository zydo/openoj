import textwrap
from pathlib import Path
from typing import Any

from .base import PreparedProgram
from .compiled import CompiledExecutor
from .typed import encode_case, function_signature, rust_type


def _read_expression(spec: dict[str, Any], reader: str = "openoj_reader") -> str:
    kind = spec["kind"]
    if kind == "integer":
        return f"{reader}.i32()?" if spec.get("bits", 32) == 32 else f"{reader}.i64()?"
    if kind == "number":
        return f"{reader}.number()?"
    if kind == "boolean":
        return f"{reader}.boolean()?"
    if kind == "string":
        return f"{reader}.text()?"
    nested = _read_expression(spec["items"], "reader")
    return f"{reader}.array(|reader| Ok({nested}))?"


class RustExecutor(CompiledExecutor):
    language = "rust"
    address_space_overhead_mb = 0
    max_processes = 16
    compiler_memory_mb = 2048
    compiler_path = "/usr/bin/rustc"
    benchmark_command = ("/runner/benchmarks/rust",)
    reference_benchmark_ms = 18.0

    def prepare(
        self,
        job_root: Path,
        scratch: Path,
        code: str,
        invocation: dict[str, Any],
        limits: dict[str, Any],
    ) -> PreparedProgram:
        parameters, _, method = function_signature(invocation, self.language)
        declarations = "\n".join(
            f"    let openoj_arg_{index}: {rust_type(spec)} = {_read_expression(spec)};"
            for index, spec in enumerate(parameters)
        )
        arguments = ", ".join(f"openoj_arg_{index}" for index in range(len(parameters)))
        source = textwrap.dedent(
            f"""
            use std::fmt::Write as OpenOJFmtWrite;
            use std::io::Read as OpenOJIoRead;

            pub struct Solution;

            {code}

            struct OpenOJReader {{ data: Vec<u8>, offset: usize }}
            impl OpenOJReader {{
                fn take(&mut self, count: usize) -> Result<&[u8], String> {{
                    if count > self.data.len().saturating_sub(self.offset) {{ return Err("Truncated judge input".into()); }}
                    let start = self.offset;
                    self.offset += count;
                    Ok(&self.data[start..self.offset])
                }}
                fn u32(&mut self) -> Result<u32, String> {{ Ok(u32::from_be_bytes(self.take(4)?.try_into().unwrap())) }}
                fn i32(&mut self) -> Result<i32, String> {{ Ok(i32::from_be_bytes(self.take(4)?.try_into().unwrap())) }}
                fn i64(&mut self) -> Result<i64, String> {{ Ok(i64::from_be_bytes(self.take(8)?.try_into().unwrap())) }}
                fn number(&mut self) -> Result<f64, String> {{ Ok(f64::from_be_bytes(self.take(8)?.try_into().unwrap())) }}
                fn boolean(&mut self) -> Result<bool, String> {{ let value = self.take(1)?[0]; if value > 1 {{ return Err("Invalid boolean input".into()); }} Ok(value == 1) }}
                fn text(&mut self) -> Result<String, String> {{ let length = self.u32()? as usize; String::from_utf8(self.take(length)?.to_vec()).map_err(|_| "Invalid UTF-8 input".into()) }}
                fn array<T, F>(&mut self, mut read: F) -> Result<Vec<T>, String> where F: FnMut(&mut Self) -> Result<T, String> {{
                    let length = self.u32()? as usize;
                    let mut values = Vec::with_capacity(length);
                    for _ in 0..length {{ values.push(read(self)?); }}
                    Ok(values)
                }}
                fn finished(&self) -> Result<(), String> {{ if self.offset == self.data.len() {{ Ok(()) }} else {{ Err("Trailing judge input".into()) }} }}
            }}

            trait OpenOJToJson {{ fn openoj_json(&self) -> Result<String, String>; }}
            impl OpenOJToJson for i32 {{ fn openoj_json(&self) -> Result<String, String> {{ Ok(self.to_string()) }} }}
            impl OpenOJToJson for i64 {{ fn openoj_json(&self) -> Result<String, String> {{ Ok(self.to_string()) }} }}
            impl OpenOJToJson for bool {{ fn openoj_json(&self) -> Result<String, String> {{ Ok(self.to_string()) }} }}
            impl OpenOJToJson for f64 {{ fn openoj_json(&self) -> Result<String, String> {{ if self.is_finite() {{ Ok(self.to_string()) }} else {{ Err("Non-finite return value".into()) }} }} }}
            impl OpenOJToJson for String {{ fn openoj_json(&self) -> Result<String, String> {{ Ok(openoj_json_string(self)) }} }}
            impl<T: OpenOJToJson> OpenOJToJson for Vec<T> {{
                fn openoj_json(&self) -> Result<String, String> {{
                    let values: Result<Vec<String>, String> = self.iter().map(|value| value.openoj_json()).collect();
                    Ok(format!("[{{}}]", values?.join(",")))
                }}
            }}
            fn openoj_json_string(value: &str) -> String {{
                let mut output = String::from("\\\"");
                for character in value.chars() {{
                    match character {{
                        '\\"' => output.push_str("\\\\\\\""),
                        '\\\\' => output.push_str("\\\\\\\\"),
                        '\\n' => output.push_str("\\\\n"),
                        '\\r' => output.push_str("\\\\r"),
                        '\\t' => output.push_str("\\\\t"),
                        '\\u{{0008}}' => output.push_str("\\\\b"),
                        '\\u{{000c}}' => output.push_str("\\\\f"),
                        value if value < '\\u{{0020}}' => {{ let _ = write!(output, "\\\\u{{:04x}}", value as u32); }},
                        value => output.push(value),
                    }}
                }}
                output.push('\\"');
                output
            }}

            fn openoj_run() -> Result<String, String> {{
                let mut bytes = Vec::new();
                std::io::stdin().read_to_end(&mut bytes).map_err(|error| error.to_string())?;
                let mut openoj_reader = OpenOJReader {{ data: bytes, offset: 0 }};
            {declarations}
                openoj_reader.finished()?;
                let openoj_actual = Solution::{method}({arguments});
                openoj_actual.openoj_json()
            }}

            fn main() {{
                let response = std::panic::catch_unwind(openoj_run);
                match response {{
                    Ok(Ok(actual)) => println!("__OPENOJ_RESULT__{{{{\\\"status\\\":\\\"completed\\\",\\\"actual\\\":{{}}}}}}", actual),
                    Ok(Err(error)) => println!("__OPENOJ_RESULT__{{{{\\\"status\\\":\\\"runtime_error\\\",\\\"error\\\":{{}}}}}}", openoj_json_string(&error)),
                    Err(_) => println!("{{}}", "__OPENOJ_RESULT__{{\\\"status\\\":\\\"runtime_error\\\",\\\"error\\\":\\\"Solution panicked\\\"}}"),
                }}
            }}
            """
        ).lstrip()
        source_path = job_root / "main.rs"
        executable = job_root / "solution"
        source_path.write_text(source, encoding="utf-8")
        source_path.chmod(0o444)
        self.compile(
            job_root,
            (
                self.compiler_path,
                "--edition=2021",
                "-C",
                "opt-level=2",
                "-C",
                "debuginfo=0",
                "-C",
                "strip=symbols",
                "-o",
                str(executable),
                str(source_path),
            ),
            executable,
            {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "TMPDIR": "/tmp"},
        )
        return PreparedProgram(
            command=(str(executable),),
            environment={
                "PATH": "/usr/bin:/bin",
                "HOME": "/nonexistent",
                "TMPDIR": str(scratch),
                "RUST_BACKTRACE": "0",
            },
        )

    def encode_case(self, invocation: dict[str, Any], case_input: Any) -> bytes:
        return encode_case(invocation, case_input, self.language)
