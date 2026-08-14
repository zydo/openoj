import textwrap
from pathlib import Path
from typing import Any

from .base import PreparedProgram
from .compiled import CompiledExecutor
from .typed import encode_case, function_signature, go_type


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
        parameters, _, method = function_signature(invocation, self.language)
        declarations = "\n".join(
            f"\topenojArg{index} := {_read_expression(spec)}"
            for index, spec in enumerate(parameters)
        )
        arguments = ", ".join(f"openojArg{index}" for index in range(len(parameters)))
        source = textwrap.dedent(
            f"""
            package main

            import (
                "encoding/binary"
                "encoding/json"
                "fmt"
                "io"
                "math"
                "os"
            )

            {code}

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
                openojActual := {method}({arguments})
                return map[string]any{{"status": "completed", "actual": openojActual}}
            }}

            func main() {{
                response := openojExecute()
                encoded, errorValue := json.Marshal(response)
                if errorValue != nil {{ encoded, _ = json.Marshal(map[string]any{{"status": "runtime_error", "error": errorValue.Error()}}) }}
                fmt.Println("__OPENOJ_RESULT__" + string(encoded))
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
                "GOCACHE": str(job_root / ".gocache"),
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
