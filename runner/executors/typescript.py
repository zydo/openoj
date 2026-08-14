import textwrap
from pathlib import Path
from typing import Any

from .base import PreparedProgram
from .compiled import CompiledExecutor
from .typed import encode_case, function_signature


def _read_expression(spec: dict[str, Any]) -> str:
    kind = spec["kind"]
    if kind == "integer":
        return (
            "openojReader.int32()"
            if spec.get("bits", 32) == 32
            else "openojReader.int64()"
        )
    if kind == "number":
        return "openojReader.number()"
    if kind == "boolean":
        return "openojReader.boolean()"
    if kind == "string":
        return "openojReader.string()"
    return f"openojReader.array(() => {_read_expression(spec['items'])})"


class TypeScriptExecutor(CompiledExecutor):
    language = "typescript"
    address_space_overhead_mb = 1536
    max_processes = 32
    compiler_memory_mb = 2048
    compiler_path = "/usr/local/bin/tsc"
    node_path = "/usr/local/bin/node"
    benchmark_command = (node_path, "/runner/benchmarks/typescript.js")
    reference_benchmark_ms = 40.0

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
            f"    const openojArg{index} = {_read_expression(spec)};"
            for index, spec in enumerate(parameters)
        )
        arguments = ", ".join(f"openojArg{index}" for index in range(len(parameters)))
        wrapper = textwrap.dedent(
            f"""
            declare const require: (name: string) => any;
            declare const process: any;

            class OpenOJReader {{
                private offset = 0;
                constructor(private readonly data: any) {{}}
                private need(count: number): void {{
                    if (this.offset + count > this.data.length) throw new Error("Truncated judge input");
                }}
                uint32(): number {{ this.need(4); const value = this.data.readUInt32BE(this.offset); this.offset += 4; return value; }}
                int32(): number {{ this.need(4); const value = this.data.readInt32BE(this.offset); this.offset += 4; return value; }}
                int64(): number {{
                    this.need(8);
                    const value = Number(this.data.readBigInt64BE(this.offset));
                    this.offset += 8;
                    if (!Number.isSafeInteger(value)) throw new Error("64-bit input exceeds TypeScript's safe integer range");
                    return value;
                }}
                number(): number {{ this.need(8); const value = this.data.readDoubleBE(this.offset); this.offset += 8; return value; }}
                boolean(): boolean {{ this.need(1); const value = this.data[this.offset++]; if (value > 1) throw new Error("Invalid boolean input"); return value === 1; }}
                string(): string {{ const length = this.uint32(); this.need(length); const value = this.data.toString("utf8", this.offset, this.offset + length); this.offset += length; return value; }}
                array<T>(read: () => T): T[] {{ const length = this.uint32(); const values: T[] = []; for (let index = 0; index < length; index++) values.push(read()); return values; }}
                finished(): void {{ if (this.offset !== this.data.length) throw new Error("Trailing judge input"); }}
            }}

            (() => {{
                try {{
                    const openojReader = new OpenOJReader(require("fs").readFileSync(0));
            {declarations}
                    openojReader.finished();
                    const openojActual = {method}({arguments});
                    const openojEncoded = JSON.stringify(openojActual);
                    if (typeof openojEncoded !== "string") throw new Error("Return value is not JSON serializable");
                    process.stdout.write(`__OPENOJ_RESULT__{{"status":"completed","actual":${{openojEncoded}}}}\n`);
                }} catch (error) {{
                    const message = error instanceof Error ? `${{error.name}}: ${{error.message}}` : String(error);
                    process.stdout.write(`__OPENOJ_RESULT__{{"status":"runtime_error","error":${{JSON.stringify(message.slice(0, 4096))}}}}\n`);
                }}
            }})();
            """
        )
        source_path = job_root / "main.ts"
        output_path = job_root / "main.js"
        source_path.write_text(code + "\n" + wrapper, encoding="utf-8")
        source_path.chmod(0o444)
        self.compile(
            job_root,
            (
                self.compiler_path,
                "--target",
                "ES2022",
                "--module",
                "commonjs",
                "--lib",
                "ES2022,DOM",
                "--skipLibCheck",
                "--pretty",
                "false",
                "--outDir",
                str(job_root),
                str(source_path),
            ),
            output_path,
            {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": "/nonexistent",
                "TMPDIR": "/tmp",
            },
        )
        return PreparedProgram(
            command=(
                self.node_path,
                "--disable-proto=throw",
                "--no-addons",
                "--max-old-space-size=192",
                "--stack-size=512",
                str(output_path),
            ),
            environment={
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": "/nonexistent",
                "TMPDIR": str(scratch),
            },
        )

    def encode_case(self, invocation: dict[str, Any], case_input: Any) -> bytes:
        return encode_case(invocation, case_input, self.language)
