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
            "    constructor(val = 0, next = null) { this.val = val; this.next = next; }\n"
            "}\n"
        )
        codecs += (
            "    linkedList() {\n"
            "        if (this.data[this.offset++] === 0) return null;\n"
            "        const length = this.uint32();\n"
            "        let head = null, current = null;\n"
            "        for (let index = 0; index < length; index++) {\n"
            "            const node = new ListNode(" + item_read + ");\n"
            "            if (current === null) head = node; else current.next = node;\n"
            "            current = node;\n"
            "        }\n"
            "        return head;\n"
            "    }\n"
            "    static listNodeJSON(head) {\n"
            "        const values = [];\n"
            "        for (let node = head; node; node = node.next) values.push(node.val);\n"
            "        return values;\n"
            "    }\n"
        )
    if "tree" in structs:
        prelude += (
            "class TreeNode {\n"
            "    constructor(val = 0, left = null, right = null) { this.val = val; this.left = left; this.right = right; }\n"
            "}\n"
        )
        codecs += (
            "    tree() {\n"
            "        const length = this.uint32();\n"
            "        const slots = [];\n"
            "        for (let index = 0; index < length; index++) {\n"
            "            slots.push(this.data[this.offset++] === 1 ? " + item_read + " : null);\n"
            "        }\n"
            "        if (length === 0 || slots[0] === null) return null;\n"
            "        const root = new TreeNode(slots[0]);\n"
            "        const queue = [root];\n"
            "        let index = 1;\n"
            "        while (queue.length > 0 && index < length) {\n"
            "            const node = queue.shift();\n"
            "            if (index < length) {\n"
            "                if (slots[index] !== null) { node.left = new TreeNode(slots[index]); queue.push(node.left); }\n"
            "                index++;\n"
            "            }\n"
            "            if (index < length) {\n"
            "                if (slots[index] !== null) { node.right = new TreeNode(slots[index]); queue.push(node.right); }\n"
            "                index++;\n"
            "            }\n"
            "        }\n"
            "        return root;\n"
            "    }\n"
            "    static treeNodeJSON(root) {\n"
            "        if (root === null) return [];\n"
            "        const values = [];\n"
            "        const queue = [root];\n"
            "        while (queue.length > 0) {\n"
            "            const node = queue.shift();\n"
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
                "function openojListNodeArrayJSON(values) {\n"
                "    return values.map(OpenOJReader.listNodeJSON);\n"
                "}\n"
            )
        if item_kind == "binary_tree" and "tree" in structs:
            prelude += (
                "function openojTreeNodeArrayJSON(values) {\n"
                "    return values.map(OpenOJReader.treeNodeJSON);\n"
                "}\n"
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


class JavaScriptExecutor(CompiledExecutor):
    """Node executor for plain JavaScript submissions; no compile step."""

    language = "javascript"
    address_space_overhead_mb = 1536
    max_processes = 32
    node_path = "/usr/local/bin/node"
    benchmark_command = (node_path, "/runner/benchmarks/javascript.js")
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
        struct_prelude, struct_codecs = _struct_prelude(invocation)
        result_wrapper = _result_wrapper(invocation)
        declarations = "\n".join(
            f"    const openojArg{index} = {_read_expression(spec)};"
            for index, spec in enumerate(parameters)
        )
        arguments = ", ".join(f"openojArg{index}" for index in range(len(parameters)))
        wrapper = textwrap.dedent(
            f"""
            class OpenOJReader {{
                constructor(data) {{ this.offset = 0; this.data = data; }}
                need(count) {{ if (this.offset + count > this.data.length) throw new Error("Truncated judge input"); }}
                uint32() {{ this.need(4); const value = this.data.readUInt32BE(this.offset); this.offset += 4; return value; }}
                int32() {{ this.need(4); const value = this.data.readInt32BE(this.offset); this.offset += 4; return value; }}
                int64() {{
                    this.need(8);
                    const value = Number(this.data.readBigInt64BE(this.offset));
                    this.offset += 8;
                    if (!Number.isSafeInteger(value)) throw new Error("64-bit input exceeds JavaScript's safe integer range");
                    return value;
                }}
                number() {{ this.need(8); const value = this.data.readDoubleBE(this.offset); this.offset += 8; return value; }}
                boolean() {{ this.need(1); const value = this.data[this.offset++]; if (value > 1) throw new Error("Invalid boolean input"); return value === 1; }}
                string() {{ const length = this.uint32(); this.need(length); const value = this.data.toString("utf8", this.offset, this.offset + length); this.offset += length; return value; }}
                array(read) {{ const length = this.uint32(); const values = []; for (let index = 0; index < length; index++) values.push(read()); return values; }}
{struct_codecs}                finished() {{ if (this.offset !== this.data.length) throw new Error("Trailing judge input"); }}
            }}
            function openojIdentity(value) {{ return value; }}

            (() => {{
                try {{
                    const openojReader = new OpenOJReader(require("fs").readFileSync(0));
            {declarations}
                    openojReader.finished();
                    const openojActual = {result_wrapper}({method}({arguments}));
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
        source_path = job_root / "main.js"
        source_path.write_text(struct_prelude + code + "\n" + wrapper, encoding="utf-8")
        source_path.chmod(0o444)
        return PreparedProgram(
            command=(
                self.node_path,
                "--disable-proto=throw",
                "--no-addons",
                "--max-old-space-size=192",
                "--stack-size=512",
                str(source_path),
            ),
            environment={
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": "/nonexistent",
                "TMPDIR": str(scratch),
            },
        )

    def encode_case(self, invocation: dict[str, Any], case_input: Any) -> bytes:
        return encode_case(invocation, case_input, self.language)
