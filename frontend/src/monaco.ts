import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
// The basic-languages bundles ship without type declarations; the Monarch
// grammar shape is all this file needs from it.
// @ts-expect-error -- untyped ESM module
import { language as pythonLanguage } from "monaco-editor/esm/vs/basic-languages/python/python.js";
import jsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";

self.MonacoEnvironment = {
  getWorker(_: string, label: string) {
    if (label === "json") return new jsonWorker();
    return new editorWorker();
  },
};

loader.config({ monaco });

// Blend Monaco into the app's surfaces instead of letting its default gray
// slab float inside the editor panel. Both themes carry LeetCode's palette:
// the light theme is sampled directly from its editor (purple keywords, blue
// types, tan functions), and the dark theme is the same hues with the dark
// values lifted for legibility on dark backgrounds (dark tan -> light
// yellow, dark navy -> sky blue), the way LeetCode's dark editor adapts it.
monaco.editor.defineTheme("openoj-dark", {
  base: "vs-dark",
  inherit: true,
  rules: [
    { token: "keyword", foreground: "b392f0" },
    { token: "keyword.flow", foreground: "b392f0" },
    { token: "keyword.control", foreground: "b392f0" },
    { token: "keyword.operator", foreground: "c9d1d9" },
    { token: "keyword.operator.logical", foreground: "79b8ff" },
    { token: "type.identifier", foreground: "79b8ff" },
    { token: "entity.name.type", foreground: "79b8ff" },
    { token: "support.class", foreground: "79b8ff" },
    { token: "support.type", foreground: "79b8ff" },
    { token: "keyword.type", foreground: "79b8ff" },
    { token: "entity.name.function", foreground: "dcdcaa" },
    { token: "support.function", foreground: "dcdcaa" },
    { token: "variable.language", foreground: "569cd6" },
    { token: "variable.parameter", foreground: "9cdcfe" },
    { token: "variable", foreground: "9cdcfe" },
    { token: "variable.other", foreground: "9cdcfe" },
    { token: "identifier", foreground: "9cdcfe" },
    { token: "number", foreground: "79b8ff" },
    { token: "string", foreground: "a5d6ff" },
    { token: "string.escape", foreground: "d2b8ff" },
    { token: "comment", foreground: "7ee787" },
    { token: "constant", foreground: "8b949e" },
    { token: "delimiter", foreground: "c9d1d9" },
  ],
  colors: {
    "editor.background": "#15191c",
    "editorGutter.background": "#15191c",
    "editor.lineHighlightBackground": "#1d2327",
    "editor.lineHighlightBorder": "#00000000",
    "editor.selectionBackground": "#2c3a44aa",
    "editor.inactiveSelectionBackground": "#2c3a4455",
    "editorLineNumber.foreground": "#65717b",
    "editorLineNumber.activeForeground": "#929ca5",
    "editorCursor.foreground": "#62b8ca",
    "editorIndentGuide.background": "#2b3237",
    "editorIndentGuide.activeBackground": "#3a444b",
    "editorScrollbarSlider.background": "#3a444b80",
    "editorScrollbarSlider.hoverBackground": "#46535b80",
    "editorWidget.background": "#1b2024",
    "editorWidget.border": "#3a444b",
    "editorSuggestWidget.background": "#1b2024",
    "editorSuggestWidget.selectedBackground": "#262d32",
    "editorSuggestWidget.border": "#3a444b",
    "input.background": "#1b2024",
    "input.border": "#3a444b",
  },
});

monaco.editor.defineTheme("openoj-light", {
  base: "vs",
  inherit: true,
  rules: [
    // LeetCode's light editor palette (sampled from its screenshots):
    // purple keywords, blue types, tan function names, near-black text.
    { token: "keyword", foreground: "6f42c1" },
    { token: "keyword.flow", foreground: "6f42c1" },
    { token: "keyword.control", foreground: "6f42c1" },
    { token: "keyword.operator", foreground: "24292e" },
    { token: "type.identifier", foreground: "2b6cb0" },
    { token: "entity.name.type", foreground: "2b6cb0" },
    { token: "support.class", foreground: "2b6cb0" },
    { token: "support.type", foreground: "2b6cb0" },
    { token: "keyword.type", foreground: "2b6cb0" },
    { token: "entity.name.function", foreground: "b07d62" },
    { token: "support.function", foreground: "b07d62" },
    { token: "variable.language", foreground: "0000ff" },
    { token: "variable.parameter", foreground: "001080" },
    { token: "variable", foreground: "001080" },
    { token: "variable.other", foreground: "001080" },
    { token: "identifier", foreground: "001080" },
    { token: "number", foreground: "005cc5" },
    { token: "string", foreground: "0a3069" },
    { token: "string.escape", foreground: "032f62" },
    { token: "comment", foreground: "22863a" },
    { token: "constant", foreground: "6a737d" },
    { token: "delimiter", foreground: "24292e" },
  ],
  colors: {
    "editor.background": "#f8f9fa",
    "editorGutter.background": "#f8f9fa",
    "editor.lineHighlightBackground": "#eef1f2",
    "editor.lineHighlightBorder": "#00000000",
    "editor.selectionBackground": "#cfe3e9aa",
    "editor.inactiveSelectionBackground": "#cfe3e955",
    "editorLineNumber.foreground": "#7b8891",
    "editorLineNumber.activeForeground": "#596771",
    "editorCursor.foreground": "#16738a",
    "editorIndentGuide.background": "#d8e0e4",
    "editorIndentGuide.activeBackground": "#c3ced4",
    "editorScrollbarSlider.background": "#c3ced480",
    "editorScrollbarSlider.hoverBackground": "#aab8c080",
    "editorWidget.background": "#ffffff",
    "editorWidget.border": "#c3ced4",
    "editorSuggestWidget.background": "#ffffff",
    "editorSuggestWidget.selectedBackground": "#e8edef",
    "editorSuggestWidget.border": "#c3ced4",
    "input.background": "#ffffff",
    "input.border": "#c3ced4",
  },
});

// Monaco's Python tokenizer labels every name `identifier`, so a class name,
// a function name, and a parameter would all land on one color. Extend the
// grammar with rules for `class X`, `def f`, call sites, and the built-in
// type names, so Python reads with the same distinctions the other languages
// get from their richer tokenizers.
const PYTHON_TYPES = [
  "int", "float", "str", "bool", "bytes", "complex", "list", "tuple", "dict",
  "set", "frozenset", "object", "type", "List", "Dict", "Set", "Tuple",
  "Optional", "Iterable", "Iterator", "Sequence", "Mapping", "Any", "Union",
  "Callable", "Deque", "Counter", "DefaultDict", "TreeNode", "ListNode",
  "Node", "NestedInteger", "GridMaster",
];

const pythonGrammar = {
  ...pythonLanguage,
  types: PYTHON_TYPES,
  selfNames: ["self", "cls"],
  tokenizer: {
    ...pythonLanguage.tokenizer,
    root: [
      [/(class)(\s+)([A-Za-z_]\w*)/, ["keyword", "white", "type.identifier"]],
      [/(def)(\s+)([A-Za-z_]\w*)/, ["keyword", "white", "entity.name.function"]],
      [
        /[a-zA-Z_]\w*(?=\s*\()/,
        {
          cases: {
            "@types": "keyword.type",
            "@keywords": "keyword",
            "@default": "support.function",
          },
        },
      ],
      [
        /[a-zA-Z_]\w*/,
        {
          cases: {
            "@types": "keyword.type",
            "@selfNames": "variable.language",
            "@keywords": "keyword",
            "@default": "identifier",
          },
        },
      ],
      ...pythonLanguage.tokenizer.root,
    ],
  },
} as monaco.languages.IMonarchLanguage;

monaco.languages.setMonarchTokensProvider("python", pythonGrammar);
