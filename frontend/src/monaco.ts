import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import jsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";

self.MonacoEnvironment = {
  getWorker(_: string, label: string) {
    if (label === "json") return new jsonWorker();
    return new editorWorker();
  },
};

loader.config({ monaco });

// Blend Monaco into the app's surfaces instead of letting its default gray
// slab float inside the editor panel. Token rules apply the classic VS Dark+
// palette (the scheme LeetCode, GitHub, and VS Code all made familiar) so
// every language reads with full color variety: keywords, types, functions,
// parameters, numbers, strings, and comments each get their own hue.
monaco.editor.defineTheme("openoj-dark", {
  base: "vs-dark",
  inherit: true,
  rules: [
    { token: "keyword", foreground: "c586c0" },
    { token: "keyword.flow", foreground: "c586c0" },
    { token: "keyword.control", foreground: "c586c0" },
    { token: "keyword.operator", foreground: "d4d4d4" },
    { token: "keyword.operator.logical", foreground: "569cd6" },
    { token: "type.identifier", foreground: "4ec9b0" },
    { token: "entity.name.type", foreground: "4ec9b0" },
    { token: "support.class", foreground: "4ec9b0" },
    { token: "support.type", foreground: "4ec9b0" },
    { token: "keyword.type", foreground: "4ec9b0" },
    { token: "entity.name.function", foreground: "dcdcaa" },
    { token: "support.function", foreground: "dcdcaa" },
    { token: "variable.parameter", foreground: "9cdcfe" },
    { token: "variable", foreground: "9cdcfe" },
    { token: "variable.other", foreground: "9cdcfe" },
    { token: "identifier", foreground: "9cdcfe" },
    { token: "number", foreground: "b5cea8" },
    { token: "string", foreground: "ce9178" },
    { token: "string.escape", foreground: "d7ba7d" },
    { token: "comment", foreground: "6a9955" },
    { token: "constant", foreground: "4fc1ff" },
    { token: "delimiter", foreground: "d4d4d4" },
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
    { token: "keyword", foreground: "af00db" },
    { token: "keyword.flow", foreground: "af00db" },
    { token: "keyword.control", foreground: "af00db" },
    { token: "keyword.operator", foreground: "000000" },
    { token: "type.identifier", foreground: "267f99" },
    { token: "entity.name.type", foreground: "267f99" },
    { token: "support.class", foreground: "267f99" },
    { token: "support.type", foreground: "267f99" },
    { token: "keyword.type", foreground: "267f99" },
    { token: "entity.name.function", foreground: "795e26" },
    { token: "support.function", foreground: "795e26" },
    { token: "variable.parameter", foreground: "001080" },
    { token: "variable", foreground: "001080" },
    { token: "variable.other", foreground: "001080" },
    { token: "identifier", foreground: "001080" },
    { token: "number", foreground: "098658" },
    { token: "string", foreground: "a31515" },
    { token: "comment", foreground: "008000" },
    { token: "constant", foreground: "0070c1" },
    { token: "delimiter", foreground: "000000" },
  ],
  colors: {
    "editor.background": "#ffffff",
    "editorGutter.background": "#ffffff",
    "editor.lineHighlightBackground": "#f1f4f5",
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
