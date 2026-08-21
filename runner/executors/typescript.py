import textwrap
from pathlib import Path
from typing import Any

from .base import PreparedProgram
from .compiled import CompiledExecutor
from .typed import encode_case, function_signature, struct_item_spec, uses_struct_kinds


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
    if kind == "linked_list":
        return "openojReader.linkedList()"
    if kind == "binary_tree":
        return "openojReader.tree()"
    return f"openojReader.array(() => {_read_expression(spec['items'])})"


def _struct_prelude(invocation: dict[str, Any]) -> tuple[str, str]:
    """Return (prelude classes, reader codecs) for struct kinds."""
    structs = uses_struct_kinds(invocation)
    item_read = "this.int64()" if struct_item_spec(invocation).get("bits", 32) == 64 else "this.int32()"
    prelude = ""
    codecs = ""
    if "list" in structs:
        prelude += (
            "class ListNode {\n"
            "    val: number;\n"
            "    next: ListNode | null;\n"
            "    constructor(val?: number, next?: ListNode | null) { this.val = val ?? 0; this.next = next ?? null; }\n"
            "}\n\n"
        )
        codecs += (
            "    linkedList(): ListNode | null {\n"
            "        if (this.data[this.offset++] === 0) return null;\n"
            "        const length = this.uint32();\n"
            "        let head: ListNode | null = null, current: ListNode | null = null;\n"
            "        for (let index = 0; index < length; index++) {\n"
            "            const node = new ListNode(" + item_read + ");\n"
            "            if (current === null) head = node; else current.next = node;\n"
            "            current = node;\n"
            "        }\n"
            "        return head;\n"
            "    }\n"
            "    static listNodeJSON(head: ListNode | null): number[] {\n"
            "        const values: number[] = [];\n"
            "        for (let node = head; node; node = node.next) values.push(node.val);\n"
            "        return values;\n"
            "    }\n"
        )
    if "tree" in structs:
        prelude += (
            "class TreeNode {\n"
            "    val: number;\n"
            "    left: TreeNode | null;\n"
            "    right: TreeNode | null;\n"
            "    constructor(val?: number, left?: TreeNode | null, right?: TreeNode | null) {\n"
            "        this.val = val ?? 0; this.left = left ?? null; this.right = right ?? null;\n"
            "    }\n"
            "}\n\n"
        )
        codecs += (
            "    tree(): TreeNode | null {\n"
            "        const length = this.uint32();\n"
            "        const slots: Array<number | null> = [];\n"
            "        for (let index = 0; index < length; index++) {\n"
            "            slots.push(this.data[this.offset++] === 1 ? " + item_read + " : null);\n"
            "        }\n"
            "        if (length === 0 || slots[0] === null) return null;\n"
            "        const root = new TreeNode(slots[0]!);\n"
            "        const queue: TreeNode[] = [root];\n"
            "        let index = 1;\n"
            "        while (queue.length > 0 && index < length) {\n"
            "            const node = queue.shift()!;\n"
            "            if (index < length) {\n"
            "                if (slots[index] !== null) { node.left = new TreeNode(slots[index]!); queue.push(node.left); }\n"
            "                index++;\n"
            "            }\n"
            "            if (index < length) {\n"
            "                if (slots[index] !== null) { node.right = new TreeNode(slots[index]!); queue.push(node.right); }\n"
            "                index++;\n"
            "            }\n"
            "        }\n"
            "        return root;\n"
            "    }\n"
            "    static treeNodeJSON(root: TreeNode | null): Array<number | null> {\n"
            "        if (root === null) return [];\n"
            "        const values: Array<number | null> = [];\n"
            "        const queue: Array<TreeNode | null> = [root];\n"
            "        while (queue.length > 0) {\n"
            "            const node = queue.shift()!;\n"
            "            if (node === null) { values.push(null); continue; }\n"
            "            values.push(node.val);\n"
            "            queue.push(node.left, node.right);\n"
            "        }\n"
            "        while (values.length > 0 && values[values.length - 1] === null) values.pop();\n"
            "        return values;\n"
            "    }\n"
        )
    return_type = invocation.get("return_type", {})
    if return_type.get("kind") == "array":
        item_kind = (return_type.get("items") or {}).get("kind")
        if item_kind == "linked_list" and "list" in structs:
            prelude += (
                "function openojListNodeArrayJSON(values: Array<ListNode | null>): Array<Array<number>> {\n"
                "    return values.map((value) => OpenOJReader.listNodeJSON(value));\n"
                "}\n\n"
            )
        if item_kind == "binary_tree" and "tree" in structs:
            prelude += (
                "function openojTreeNodeArrayJSON(values: Array<TreeNode | null>): Array<Array<number | null>> {\n"
                "    return values.map((value) => OpenOJReader.treeNodeJSON(value));\n"
                "}\n\n"
            )
    return prelude, codecs


def _result_wrapper(invocation: dict[str, Any]) -> str:
    return_type = invocation.get("return_type", {})
    if return_type.get("kind") == "linked_list":
        return "OpenOJReader.listNodeJSON"
    if return_type.get("kind") == "binary_tree":
        return "OpenOJReader.treeNodeJSON"
    if return_type.get("kind") == "array":
        item_kind = (return_type.get("items") or {}).get("kind")
        if item_kind == "linked_list":
            return "openojListNodeArrayJSON"
        if item_kind == "binary_tree":
            return "openojTreeNodeArrayJSON"
    return "openojIdentity"


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
        assembly: dict[str, dict[str, str]] | None = None,
    ) -> PreparedProgram:
        if invocation.get("type") == "design":
            from .js_design import prepare_design
            return prepare_design(self, job_root, scratch, code, invocation, assembly, is_typescript=True)
        if invocation.get("type") == "interactive":
            from .js_interactive import prepare_interactive
            return prepare_interactive(self, job_root, scratch, code, invocation, assembly, is_typescript=True)
        parameters, _, method = function_signature(invocation, self.language)
        # With the assembled common library the type declarations arrive as
        # source ahead of the submission; the per-invocation prelude below
        # still covers pre-assembly jobs.
        assembly_prelude = "".join(
            content + "\n"
            for part in ("common", "provided")
            for _, content in sorted((assembly or {}).get(part, {}).items())
        )
        struct_prelude, struct_codecs = _struct_prelude(invocation)
        if assembly_prelude:
            struct_prelude = ""
        result_wrapper = _result_wrapper(invocation)
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
{struct_codecs}                finished(): void {{ if (this.offset !== this.data.length) throw new Error("Trailing judge input"); }}
            }}
            function openojIdentity(value: any) {{ return value; }}
            // JSON.stringify renders integer doubles beyond 2^53 in exponent
            // notation ("4.611686018427388e+18"), which loses the exact value
            // when the judge parses it back. Emit such integers as exact
            // decimal digits instead — BigInt(value) is exact whenever the
            // double is an integer (Number.isInteger above guarantees it).
            function openojSerialize(value: any): string {{
                if (value === undefined) return "null";
                if (typeof value === "number") {{
                    if (Number.isInteger(value) && !Number.isSafeInteger(value)) return BigInt(value).toString();
                    return JSON.stringify(value);
                }}
                if (value !== null && typeof value === "object") {{
                    if (Array.isArray(value)) return "[" + value.map(openojSerialize).join(",") + "]";
                    const entries = Object.entries(value).map(([key, item]) => JSON.stringify(key) + ":" + openojSerialize(item));
                    return "{{" + entries.join(",") + "}}";
                }}
                return JSON.stringify(value);
            }}

            function openojEmit(line: string) {{
                try {{ require("fs").writeSync(63, line + "\\n"); }}
                catch (error) {{ process.stdout.write(line + "\\n"); }}
            }}
            (() => {{
                try {{
                    const openojReader = new OpenOJReader(require("fs").readFileSync(0));
            {declarations}
                    openojReader.finished();
                    const openojActual = {result_wrapper}({method}({arguments}));
                    const openojEncoded = openojSerialize(openojActual);
                    if (typeof openojEncoded !== "string") throw new Error("Return value is not JSON serializable");
                    openojEmit(`__OPENOJ_RESULT__{{"status":"completed","actual":${{openojEncoded}}}}`);
                }} catch (error) {{
                    const message = error instanceof Error ? `${{error.name}}: ${{error.message}}` : String(error);
                    openojEmit(`__OPENOJ_RESULT__{{"status":"runtime_error","error":${{JSON.stringify(message.slice(0, 4096))}}}}`);
                }}
            }})();
            """
        )
        source_path = job_root / "main.ts"
        output_path = job_root / "main.js"
        source_path.write_text(assembly_prelude + struct_prelude + code + "\n" + wrapper, encoding="utf-8")
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
        if invocation.get("type") == "interactive":
            from .typed import encode_interactive_case
            return encode_interactive_case(invocation, case_input)
        if invocation.get("type") == "design":
            from .design_interactive import encode_design_case
            return encode_design_case(invocation, case_input)
        return encode_case(invocation, case_input, self.language)
