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
// slab float inside the editor panel. Token colors are inherited from the
// built-in themes; only the chrome (background, line highlight, selection,
// gutter, line numbers, scrollbar) is recolored to match styles.css tokens.
monaco.editor.defineTheme("openoj-dark", {
  base: "vs-dark",
  inherit: true,
  rules: [],
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
  rules: [],
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
