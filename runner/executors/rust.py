import textwrap
from pathlib import Path
from typing import Any

from .base import PreparedProgram
from .compiled import CompiledExecutor
from .typed import (
    encode_case,
    function_signature,
    rust_type,
    struct_item_spec,
    uses_struct_kinds,
)


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
    if kind == "linked_list":
        return f"{reader}.linked_list()?"
    if kind == "binary_tree":
        return f"{reader}.binary_tree()?"
    nested = _read_expression(spec["items"], "reader")
    return f"{reader}.array(|reader| Ok({nested}))?"


class RustExecutor(CompiledExecutor):
    language = "rust"
    address_space_overhead_mb = 0
    max_processes = 16
    compiler_memory_mb = 2048
    # rustc's first link on a cold page cache easily exceeds the shared
    # 10-second budget; the worker pre-warms the toolchain at startup so this
    # only covers genuinely large submissions.
    compiler_timeout_seconds = 25
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
        parameters, return_type, method = function_signature(invocation, self.language)
        structs = uses_struct_kinds(invocation)
        item_read = _read_expression(struct_item_spec(invocation), "self")
        struct_codecs = ""
        result_expression = "openoj_actual.openoj_json()"
        if "list" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                impl OpenOJReader {{
                    fn linked_list(&mut self) -> Result<Option<Box<ListNode>>, String> {{
                        if self.take(1)?[0] == 0 {{ return Ok(None); }}
                        let length = self.u32()? as usize;
                        let mut nodes: Vec<ListNode> = Vec::with_capacity(length);
                        for _ in 0..length {{ nodes.push(ListNode {{ val: {item_read}, next: None }}); }}
                        let mut head: Option<Box<ListNode>> = None;
                        for node in nodes.into_iter().rev() {{
                            head = Some(Box::new(ListNode {{ val: node.val, next: head }}));
                        }}
                        Ok(head)
                    }}
                }}
                fn openoj_list_node_json(head: &Option<Box<ListNode>>) -> String {{
                    let mut output = String::from("[");
                    let mut current = head.as_deref();
                    let mut first = true;
                    while let Some(node) = current {{
                        if !first {{ output.push(','); }}
                        first = false;
                        let _ = write!(output, "{{}}", node.val);
                        current = node.next.as_deref();
                    }}
                    output.push(']');
                    output
                }}
                """
            )
            if return_type.get("kind") == "linked_list":
                result_expression = "Ok(openoj_list_node_json(&openoj_actual))"
        if "tree" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                impl OpenOJReader {{
                    fn binary_tree(&mut self) -> Result<Option<Box<TreeNode>>, String> {{
                        let length = self.u32()? as usize;
                        let mut pool: Vec<Option<Box<TreeNode>>> = Vec::with_capacity(length);
                        for _ in 0..length {{
                            if self.take(1)?[0] == 1 {{
                                pool.push(Some(Box::new(TreeNode {{ val: {item_read}, left: None, right: None }})));
                            }} else {{
                                pool.push(None);
                            }}
                        }}
                        if pool.is_empty() || pool[0].is_none() {{ return Ok(None); }}
                        let mut root = pool[0].take();
                        let mut queue: std::collections::VecDeque<*mut TreeNode> = std::collections::VecDeque::new();
                        queue.push_back(root.as_mut().unwrap().as_mut());
                        let mut index = 1usize;
                        while let Some(node_pointer) = queue.pop_front() {{
                            for side in 0..2 {{
                                if index >= pool.len() {{ break; }}
                                if pool[index].is_some() {{
                                    let mut child = pool[index].take().unwrap();
                                    queue.push_back(child.as_mut() as *mut TreeNode);
                                    unsafe {{
                                        if side == 0 {{ (*node_pointer).left = Some(child); }}
                                        else {{ (*node_pointer).right = Some(child); }}
                                    }}
                                }}
                                index += 1;
                            }}
                        }}
                        Ok(root)
                    }}
                }}
                fn openoj_tree_node_json(root: &Option<Box<TreeNode>>) -> String {{
                    let mut items: Vec<String> = Vec::new();
                    let mut queue: std::collections::VecDeque<Option<&TreeNode>> = std::collections::VecDeque::new();
                    if root.is_some() {{ queue.push_back(root.as_deref()); }}
                    while let Some(entry) = queue.pop_front() {{
                        match entry {{
                            None => items.push("null".to_string()),
                            Some(node) => {{
                                items.push(node.val.to_string());
                                queue.push_back(node.left.as_deref());
                                queue.push_back(node.right.as_deref());
                            }}
                        }}
                    }}
                    while items.last().map_or(false, |value| value == "null") {{ items.pop(); }}
                    format!("[{{}}]", items.join(","))
                }}
                """
            )
            if return_type.get("kind") == "binary_tree":
                result_expression = "Ok(openoj_tree_node_json(&openoj_actual))"
            if return_type.get("kind") == "array" and return_type.get("items", {}).get("kind") == "binary_tree":
                result_expression = (
                    "Ok(format!(\"[{}]\", openoj_actual.iter()"
                    ".map(|tree| openoj_tree_node_json(tree))"
                    ".collect::<Vec<String>>().join(\",\")))"
                )

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
{struct_codecs}
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
                {result_expression}
            }}

            fn openoj_emit(line: &str) {{
                // Judge protocol prefers the dedicated fd so submission code
                // cannot forge verdicts on stdout; stdout is the fallback.
                use std::io::Write;
                use std::os::unix::io::FromRawFd;
                let mut channel = unsafe {{ std::fs::File::from_raw_fd(63) }};
                if write!(channel, "{{}}\\n", line).is_ok() {{
                    return;
                }}
                println!("{{}}", line);
            }}

            fn main() {{
                let response = std::panic::catch_unwind(openoj_run);
                match response {{
                    Ok(Ok(actual)) => openoj_emit(&format!("__OPENOJ_RESULT__{{{{\\\"status\\\":\\\"completed\\\",\\\"actual\\\":{{}}}}}}", actual)),
                    Ok(Err(error)) => openoj_emit(&format!("__OPENOJ_RESULT__{{{{\\\"status\\\":\\\"runtime_error\\\",\\\"error\\\":{{}}}}}}", openoj_json_string(&error))),
                    Err(_) => openoj_emit("__OPENOJ_RESULT__{{{{\\\"status\\\":\\\"runtime_error\\\",\\\"error\\\":\\\"Solution panicked\\\"}}}}"),
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
