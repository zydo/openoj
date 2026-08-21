"""Design-kind wrappers for JavaScript and TypeScript.

The design protocol (python_harness._invoke_design is the reference):
a case carries `actions` and `params`; params[0] constructs the
instance; each action names a method (or {"call", "repeat"} for a
randomized method judged by a frequency table over its repeated
results); a {"$prev"} argument pipes the previous raw result into the
next call. The whole case travels as one tagged stream
(design_interactive.encode_design_case). Dynamic values make the
replay loop a plain generated function here; the wrapper is written
per problem from the invocation's method table so method dispatch and
arity checks are compile-time where the language allows it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import ExecutorError, PreparedProgram

WRAPPER_HEAD = """\
function openojEmit(line) {
    const fs = require("fs");
    try {
        fs.writeSync(63, line + "\\n");
        return;
    } catch (problem) {
        // no protocol fd (local tooling): stdout is the fallback
    }
    process.stdout.write(line + "\\n");
}

class OjReader {
    constructor(buffer) { this.bytes = buffer; this.position = 0; }
    byte() {
        if (this.position >= this.bytes.length) throw new Error("Truncated case payload");
        return this.bytes[this.position++];
    }
    u32() {
        let value = 0;
        for (let i = 0; i < 4; i++) value = (value * 256) + this.byte();
        return value;
    }
    i64() {
        let value = 0n;
        for (let i = 0; i < 8; i++) value = (value << 8n) | BigInt(this.byte());
        return Number(BigInt.asIntN(64, value));
    }
    f64() {
        const buffer = new ArrayBuffer(8);
        const view = new DataView(buffer);
        for (let i = 0; i < 8; i++) view.setUint8(i, this.byte());
        return view.getFloat64(0);
    }
    str() {
        const length = this.u32();
        let value = "";
        for (let i = 0; i < length; i++) value += String.fromCharCode(this.byte());
        return value;
    }
    value() {
        const tag = this.byte();
        switch (tag) {
            case 0x00: return null;
            case 0x01: return false;
            case 0x02: return true;
            case 0x10: return Number(BigInt.asIntN(32, BigInt(this.u32())));
            case 0x11: return this.i64();
            case 0x12: return this.f64();
            case 0x13: return this.str();
            case 0x14: { const count = this.u32(); const items = []; for (let i = 0; i < count; i++) items.push(this.value()); return items; }
            case 0x15: { const count = this.u32(); const object = {}; for (let i = 0; i < count; i++) object[String(this.value())] = this.value(); return object; }
            default: throw new Error("Unknown tagged value");
        }
    }
}

function openojJSON(value) {
    return JSON.stringify(value, (_key, item) => {
        if (typeof item === "bigint") return Number(item);
        if (item === undefined) return null;
        return item;
    });
}
"""

CODEC_HELPERS = """\
// Codec-aware argument/result conversion, mirroring the harness's
// decode/encode (python_harness._invoke_design). Only the tree codecs
// transform; json is the identity.
function openojDecode(value, codec) {
    if (codec === "tree_node") {
        return openojTreeFromArray(value);
    }
    return value;
}

function openojEncode(value, codec) {
    if (value === undefined) {
        return null;
    }
    if (codec === "tree_node") {
        return openojTreeToArray(value);
    }
    return value;
}

// Level-order array (nulls for absent children) -> TreeNode tree, two
// slots consumed per queued node exactly like the harness's codec.
function openojTreeFromArray(slots) {
    if (!Array.isArray(slots) || slots.length === 0 || slots[0] === null) {
        return null;
    }
    const root = new TreeNode(slots[0]);
    const queue = [root];
    let index = 1;
    while (queue.length > 0 && index < slots.length) {
        const node = queue.shift();
        if (index < slots.length) {
            if (slots[index] !== null) {
                node.left = new TreeNode(slots[index]);
                queue.push(node.left);
            }
            index++;
        }
        if (index < slots.length) {
            if (slots[index] !== null) {
                node.right = new TreeNode(slots[index]);
                queue.push(node.right);
            }
            index++;
        }
    }
    return root;
}

// TreeNode tree -> level-order array, trailing nulls trimmed, so results
// compare as plain JSON.
function openojTreeToArray(root) {
    if (root === null || root === undefined) {
        return [];
    }
    const output = [];
    const queue = [root];
    while (queue.length > 0) {
        const node = queue.shift();
        if (node === null) {
            output.push(null);
            continue;
        }
        output.push(node.val);
        queue.push(node.left);
        queue.push(node.right);
    }
    while (output.length > 0 && output[output.length - 1] === null) {
        output.pop();
    }
    return output;
}
"""

MAIN_TEMPLATE = """\
async function main() {
    const chunks = [];
    for (;;) {
        const chunk = await new Promise((resolve) => {
            process.stdin.once("readable", () => resolve(process.stdin.read()));
        });
        if (chunk === null) break;
        chunks.push(chunk);
    }
    const reader = new OjReader(Buffer.concat(chunks));
    const actions = reader.value();
    const params = reader.value();
    if (!Array.isArray(actions) || !Array.isArray(params) || actions.length !== params.length) {
        throw new Error("Design input requires equally sized actions and params");
    }
    const constructorCodecs = @CTOR_CODECS@;
    const methodCodecs = @METHOD_CODECS@;
    const returnCodecs = @RETURN_CODECS@;
    const constructorArguments = params[0].map((argument, index) => openojDecode(argument, constructorCodecs[index] || "json"));
    const solution = new @CLASS_NAME@(...constructorArguments);
    const outputs = [null];
    let previous = null;
    for (let step = 1; step < actions.length; step++) {
        let action = actions[step];
        let repeat = 1;
        if (action !== null && typeof action === "object" && !Array.isArray(action)) {
            repeat = Number(action.repeat || 1);
            action = action.call;
        }
        const rawArguments = params[step];
        const codecs = methodCodecs[action] || [];
        // A piped argument ({"$prev": ...}) crosses as the previous call's
        // live object, not its wire form; everything else decodes through
        // its parameter codec (python_harness._invoke_design).
        const decodedArguments = rawArguments.map((argument, index) => {
            if (argument !== null && typeof argument === "object" && !Array.isArray(argument)
                    && Object.keys(argument).length === 1 && "$prev" in argument) {
                return previous;
            }
            return openojDecode(argument, codecs[index] || "json");
        });
        const returnCodec = returnCodecs[action] || "json";
        if (repeat > 1) {
            const frequencies = new Map();
            let last = null;
            for (let trial = 0; trial < repeat; trial++) {
                last = solution[action](...decodedArguments);
                const key = openojJSON(openojEncode(last, returnCodec));
                frequencies.set(key, (frequencies.get(key) || 0) + 1);
            }
            const table = {};
            for (const [key, count] of frequencies) table[key] = count;
            outputs.push(table);
            previous = last;
        } else {
            const rawResult = solution[action](...decodedArguments);
            outputs.push(openojEncode(rawResult, returnCodec));
            previous = rawResult;
        }
    }
    openojEmit("__OPENOJ_RESULT__" + openojJSON({ status: "completed", actual: outputs }));
}

main().catch((problem) => {
    openojEmit("__OPENOJ_RESULT__" + openojJSON({ status: "runtime_error", error: String(problem && problem.message ? problem.message : problem) }));
});
"""


def prepare_design(executor, job_root: Path, scratch: Path, code: str,
                   invocation: dict[str, Any], assembly,
                   is_typescript: bool = False) -> PreparedProgram:
    class_name = invocation.get("class_name", "Solution")
    if not isinstance(class_name, str) or not class_name.isidentifier():
        raise ExecutorError("Invalid design entry class")

    # Codec tables (python_harness._invoke_design's per-method codec map):
    # each argument is decoded from its wire form, each result encoded back.
    constructor = invocation.get("constructor", {}).get("parameters", [])
    constructor_codecs = [p.get("codec", "json") for p in constructor if isinstance(p, dict)]
    method_codecs: dict[str, list[str]] = {}
    return_codecs: dict[str, str] = {}
    for method in invocation.get("methods", []):
        if not isinstance(method, dict) or not isinstance(method.get("name"), str):
            continue
        method_codecs[method["name"]] = [
            p.get("codec", "json") for p in method.get("parameters", []) if isinstance(p, dict)
        ]
        return_codecs[method["name"]] = method.get("return_codec", "json")

    provided_source = "".join(
        content + "\n"
        for part in ("common", "provided")
        for _, content in sorted((assembly or {}).get(part, {}).items())
    )
    main_source = (
        MAIN_TEMPLATE
        .replace("@CLASS_NAME@", class_name)
        .replace("@CTOR_CODECS@", json.dumps(constructor_codecs))
        .replace("@METHOD_CODECS@", json.dumps(method_codecs))
        .replace("@RETURN_CODECS@", json.dumps(return_codecs))
    )
    if not is_typescript:
        main_source = main_source.replace("...(constructorArguments as any[]))", "...constructorArguments)")
        main_source = main_source.replace("(solution[action] as any)", "solution[action]")
    else:
        main_source = main_source.replace(
            f"new {class_name}(...constructorArguments);",
            f"new ({class_name} as any)(...constructorArguments);",
        )
        main_source = main_source.replace(".map((argument, index) => {", ".map((argument: any, index: number) => {")
        main_source = main_source.replace("solution[action](...decodedArguments)", "(solution[action] as any)(...decodedArguments)")
    if is_typescript:
        # The codec helpers reference ListNode/TreeNode, whose real
        # classes live in common/typescript/types.ts — the common source
        # must precede the wrapper for those references to resolve.
        source = provided_source + "\n" + WRAPPER_HEAD + "\n" + CODEC_HELPERS + "\n" + code + "\n" + main_source
    else:
        source = WRAPPER_HEAD + "\n" + CODEC_HELPERS + "\n" + provided_source + code + "\n" + main_source
    if is_typescript:
        source = (
            'declare const require: (name: string) => any;\n'
            'declare const process: any;\n'
            'declare const Buffer: any;\n'
            + source
        )
        source = source.replace(
            'class OjReader {\n    constructor(buffer) {',
            'class OjReader {\n    bytes: any; position = 0;\n    constructor(buffer: any) {',
        )
        source = source.replace(
            '    const actions = reader.value();',
            '    const actions: any = reader.value();',
        ).replace(
            '    const params = reader.value();',
            '    const params: any = reader.value();',
        ).replace(
            '        let action = actions[step];',
            '        let action: any = actions[step];',
        ).replace(
            '        const rawArguments = params[step];',
            '        const rawArguments: any[] = params[step];',
        ).replace(
            '        const constructorArguments = params[0];',
            '        const constructorArguments: any[] = params[0];',
        )

    suffix = "ts" if is_typescript else "js"
    source_path = job_root / f"main.{suffix}"
    source_path.write_text(source, encoding="utf-8")
    source_path.chmod(0o444)

    if is_typescript:
        javascript_path = job_root / "main.js"
        executor.compile(
            job_root,
            (
                executor.compiler_path, "--target", "ES2022", "--module", "commonjs",
                "--lib", "ES2022", "--skipLibCheck", "--pretty", "false",
                "--outDir", str(job_root), str(source_path),
            ),
            javascript_path,
            {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "TMPDIR": "/tmp", "LANG": "C.UTF-8"},
        )
        run_path = javascript_path
    else:
        run_path = source_path

    return PreparedProgram(
        command=(str(executor.node_path), str(run_path)),
        environment={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "NODE_OPTIONS": "--disable-proto=throw --no-addons", "TMPDIR": str(scratch), "LANG": "C.UTF-8"},
    )
