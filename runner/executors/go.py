import re
import textwrap
from pathlib import Path
from typing import Any

from .base import PreparedProgram
from .compiled import CompiledExecutor
from .typed import (
    encode_case,
    function_signature,
    go_type,
    struct_item_spec,
    uses_struct_kinds,
)

# Submitted code may import stdlib packages; Go requires every import to sit
# in the file's import preamble, so user imports are lifted out of the code
# and merged with the wrapper's own.
GO_IMPORT_BLOCK = re.compile(
    r'^import \((?:\s*"[^"]+"\s*)+\)\s*\n|^import\s+"[^"]+"\s*\n', re.M
)
WRAPPER_IMPORTS = ("encoding/binary", "encoding/json", "fmt", "io", "math", "os")


def _merge_imports(code: str) -> tuple[str, str]:
    packages = set(WRAPPER_IMPORTS)
    remaining = code
    for match in GO_IMPORT_BLOCK.finditer(code):
        packages.update(re.findall(r'"([^"]+)"', match.group(0)))
        remaining = remaining.replace(match.group(0), "", 1)
    imports = "".join(f'\t\t\t"{package}"\n' for package in sorted(packages))
    return remaining.strip("\n"), imports


def _read_expression(spec: dict[str, Any], reader: str = "openojReader") -> str:
    kind = spec["kind"]
    if kind == "integer":
        return f"{reader}.int32()" if spec.get("bits", 32) == 32 else f"{reader}.int64()"
    if kind == "number":
        return f"{reader}.number()"
    if kind == "boolean":
        return f"{reader}.boolean()"
    if kind == "string":
        return f"{reader}.text()"
    if kind == "linked_list":
        return f"{reader}.linkedList()"
    if kind == "binary_tree":
        return f"{reader}.tree()"
    item_type = go_type(spec["items"])
    nested = _read_expression(spec["items"], "reader")
    return f"openojArray({reader}, func(reader *openojReaderType) {item_type} {{ return {nested} }})"


class GoExecutor(CompiledExecutor):
    language = "go"
    # Go reserves a large virtual arena while resident memory remains bounded
    # by GOMEMLIMIT and the container cgroup.
    address_space_overhead_mb = 2048
    max_processes = 32
    compiler_memory_mb = 2048
    # A cold GOCACHE (fresh container, or stdlib packages the warm build does
    # not cover) makes `go build` compile standard-library packages on the
    # spot — 10s is not enough on a small VM. Compile time is wall clock
    # outside the judged runtime, so the generous budget costs nothing.
    compiler_timeout_seconds = 60
    compiler_path = "/usr/bin/go"
    benchmark_command = ("/runner/benchmarks/go",)
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
        item_type = go_type(struct_item_spec(invocation))
        struct_decls = ""
        struct_codecs = ""
        result_conversion = "openojIdentity"
        if "list" in structs:
            struct_decls += (
                f"type ListNode struct {{\n\tVal  {item_type}\n\tNext *ListNode\n}}\n\n"
            )
        if "tree" in structs:
            struct_decls += (
                f"type TreeNode struct {{\n\tVal   {item_type}\n\tLeft  *TreeNode\n\tRight *TreeNode\n}}\n\n"
            )
        if "list" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                func (reader *openojReaderType) linkedList() *ListNode {{
                    if reader.take(1)[0] == 0 {{ return nil }}
                    length := int(reader.uint32())
                    var head, current *ListNode
                    for index := 0; index < length; index++ {{
                        node := &ListNode{{Val: {_read_expression(struct_item_spec(invocation), 'reader')}}}
                        if current == nil {{ head = node }} else {{ current.Next = node }}
                        current = node
                    }}
                    return head
                }}
                func openojListNodeJSON(head *ListNode) []any {{
                    values := []any{{}}
                    for node := head; node != nil; node = node.Next {{
                        values = append(values, node.Val)
                    }}
                    return values
                }}
                func openojListNodeArrayJSON(heads []*ListNode) []any {{
                    values := make([]any, len(heads))
                    for index, head := range heads {{
                        values[index] = openojListNodeJSON(head)
                    }}
                    return values
                }}
                """
            )
            if return_type.get("kind") == "linked_list":
                result_conversion = "openojListNodeJSON"
            if (return_type.get("kind") == "array"
                    and (return_type.get("items") or {}).get("kind") == "linked_list"):
                result_conversion = "openojListNodeArrayJSON"
        if "tree" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                func (reader *openojReaderType) tree() *TreeNode {{
                    length := int(reader.uint32())
                    type slot struct {{
                        present bool
                        value   {item_type}
                    }}
                    slots := make([]slot, length)
                    for index := 0; index < length; index++ {{
                        if reader.take(1)[0] == 1 {{
                            slots[index] = slot{{present: true, value: {_read_expression(struct_item_spec(invocation), 'reader')}}}
                        }}
                    }}
                    if length == 0 || !slots[0].present {{ return nil }}
                    root := &TreeNode{{Val: slots[0].value}}
                    queue := []*TreeNode{{root}}
                    index := 1
                    for len(queue) > 0 && index < length {{
                        node := queue[0]
                        queue = queue[1:]
                        if index < length {{
                            if slots[index].present {{
                                node.Left = &TreeNode{{Val: slots[index].value}}
                                queue = append(queue, node.Left)
                            }}
                            index++
                        }}
                        if index < length {{
                            if slots[index].present {{
                                node.Right = &TreeNode{{Val: slots[index].value}}
                                queue = append(queue, node.Right)
                            }}
                            index++
                        }}
                    }}
                    return root
                }}
                func openojTreeNodeJSON(root *TreeNode) []any {{
                    if root == nil {{ return []any{{}} }}
                    values := []any{{}}
                    queue := []*TreeNode{{root}}
                    for len(queue) > 0 {{
                        node := queue[0]
                        queue = queue[1:]
                        if node == nil {{
                            values = append(values, nil)
                            continue
                        }}
                        values = append(values, node.Val)
                        queue = append(queue, node.Left, node.Right)
                    }}
                    for len(values) > 0 && values[len(values)-1] == nil {{
                        values = values[:len(values)-1]
                    }}
                    return values
                }}
                func openojTreeNodeArrayJSON(roots []*TreeNode) []any {{
                    values := make([]any, len(roots))
                    for index, root := range roots {{
                        values[index] = openojTreeNodeJSON(root)
                    }}
                    return values
                }}
                """
            )
            if return_type.get("kind") == "binary_tree":
                result_conversion = "openojTreeNodeJSON"
            if (return_type.get("kind") == "array"
                    and (return_type.get("items") or {}).get("kind") == "binary_tree"):
                result_conversion = "openojTreeNodeArrayJSON"

        declarations = "\n".join(
            f"\topenojArg{index} := {_read_expression(spec)}"
            for index, spec in enumerate(parameters)
        )
        arguments = ", ".join(f"openojArg{index}" for index in range(len(parameters)))
        code, merged_imports = _merge_imports(code)
        source = textwrap.dedent(
            f"""
            package main

            import (
            {merged_imports}            )

            {struct_decls}{code}

            type openojReaderType struct {{
                data []byte
                offset int
            }}

            func (reader *openojReaderType) take(count int) []byte {{
                if count < 0 || count > len(reader.data)-reader.offset {{ panic("truncated judge input") }}
                value := reader.data[reader.offset:reader.offset+count]
                reader.offset += count
                return value
            }}
            func (reader *openojReaderType) uint32() uint32 {{ return binary.BigEndian.Uint32(reader.take(4)) }}
            func (reader *openojReaderType) int32() int {{ return int(int32(reader.uint32())) }}
            func (reader *openojReaderType) int64() int64 {{ return int64(binary.BigEndian.Uint64(reader.take(8))) }}
            func (reader *openojReaderType) number() float64 {{ return math.Float64frombits(binary.BigEndian.Uint64(reader.take(8))) }}
            func (reader *openojReaderType) boolean() bool {{ value := reader.take(1)[0]; if value > 1 {{ panic("invalid boolean input") }}; return value == 1 }}
            func (reader *openojReaderType) text() string {{ return string(reader.take(int(reader.uint32()))) }}
            func (reader *openojReaderType) finished() {{ if reader.offset != len(reader.data) {{ panic("trailing judge input") }} }}
            func openojArray[T any](reader *openojReaderType, read func(*openojReaderType) T) []T {{
                length := int(reader.uint32())
                values := make([]T, length)
                for index := range values {{ values[index] = read(reader) }}
                return values
            }}
            func openojIdentity(value any) any {{ return value }}
{struct_codecs}
            func openojExecute() (response map[string]any) {{
                defer func() {{
                    if recovered := recover(); recovered != nil {{
                        response = map[string]any{{"status": "runtime_error", "error": fmt.Sprint(recovered)}}
                    }}
                }}()
                bytes, errorValue := io.ReadAll(os.Stdin)
                if errorValue != nil {{ panic(errorValue) }}
                openojReader := &openojReaderType{{data: bytes}}
            {declarations}
                openojReader.finished()
                openojRaw := {method}({arguments})
                openojActual := {result_conversion}(openojRaw)
                return map[string]any{{"status": "completed", "actual": openojActual}}
            }}

            func openojEmit(line string) {{
                // Judge protocol prefers the dedicated fd so submission code
                // cannot forge verdicts on stdout; stdout is the fallback.
                if channel := os.NewFile(63, "protocol"); channel != nil {{
                    if _, errorValue := channel.WriteString(line + "\\n"); errorValue == nil {{
                        return
                    }}
                }}
                fmt.Println(line)
            }}

            func main() {{
                response := openojExecute()
                encoded, errorValue := json.Marshal(response)
                if errorValue != nil {{ encoded, _ = json.Marshal(map[string]any{{"status": "runtime_error", "error": errorValue.Error()}}) }}
                openojEmit("__OPENOJ_RESULT__" + string(encoded))
            }}
            """
        ).lstrip()
        source_path = job_root / "main.go"
        executable = job_root / "solution"
        source_path.write_text(source, encoding="utf-8")
        source_path.chmod(0o444)
        self.compile(
            job_root,
            (
                self.compiler_path,
                "build",
                "-trimpath",
                "-ldflags=-s -w",
                "-o",
                str(executable),
                str(source_path),
            ),
            executable,
            {
                "PATH": "/usr/bin:/bin",
                "HOME": "/nonexistent",
                "TMPDIR": "/tmp",
                # One shared build cache across submissions: a per-job cache
                # would force every compile to rebuild the standard library.
                "GOCACHE": "/tmp/openoj-gocache",
                "GOENV": "off",
                "GOPROXY": "off",
                "CGO_ENABLED": "0",
                "GOMAXPROCS": "1",
            },
        )
        return PreparedProgram(
            command=(str(executable),),
            environment={
                "PATH": "/usr/bin:/bin",
                "HOME": "/nonexistent",
                "TMPDIR": str(scratch),
                "GOMAXPROCS": "1",
                "GOMEMLIMIT": "192MiB",
                "GOTRACEBACK": "none",
            },
        )

    def encode_case(self, invocation: dict[str, Any], case_input: Any) -> bytes:
        return encode_case(invocation, case_input, self.language)
