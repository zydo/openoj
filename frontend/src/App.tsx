import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Braces,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clock3,
  Code2,
  FileText,
  Github,
  GripVertical,
  History,
  List,
  LoaderCircle,
  Play,
  Plus,
  RotateCcw,
  Send,
  Moon,
  Sun,
  TerminalSquare,
  X,
} from "lucide-react";
import { api } from "./api";
import type { JudgeResult, Problem, Submission } from "./types";

type ProblemSummary = Pick<Problem, "id" | "slug" | "title" | "difficulty" | "tags">;
type Theme = "light" | "dark";

const DEFAULT_SLUG = "two-sum";
const THEME_STORAGE_KEY = "openoj:theme";

function storedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function preferredTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function draftKey(slug: string, language: string) {
  return `openoj:${slug}:${language}`;
}

function readDraft(slug: string, language: string) {
  try {
    return localStorage.getItem(draftKey(slug, language));
  } catch {
    return null;
  }
}

function writeDraft(slug: string, language: string, code: string) {
  try {
    localStorage.setItem(draftKey(slug, language), code);
  } catch {
    /* Drafts are best-effort; judging works without them. */
  }
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    accepted: "Accepted",
    completed: "Finished",
    wrong_answer: "Wrong answer",
    runtime_error: "Runtime error",
    compile_error: "Compile error",
    time_limit_exceeded: "Time limit exceeded",
    memory_limit_exceeded: "Memory limit exceeded",
    system_error: "Judge error",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

function statusTone(status?: string) {
  if (!status) return "idle";
  if (status === "accepted" || status === "completed") return "success";
  if (status === "wrong_answer" || status === "compile_error") return "danger";
  return "warning";
}

function difficultyTone(difficulty: string) {
  const level = Number.parseInt(difficulty.replace(/[^0-9]/g, ""), 10);
  if (Number.isNaN(level)) return "easy";
  if (level <= 2) return "easy";
  if (level === 3) return "medium";
  return "hard";
}

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function App() {
  const [themeOverride, setThemeOverride] = useState<Theme | null>(storedTheme);
  const [systemTheme, setSystemTheme] = useState<Theme>(preferredTheme);
  const [problems, setProblems] = useState<ProblemSummary[] | null>(null);
  const [listError, setListError] = useState("");
  const [activeSlug, setActiveSlug] = useState<string | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [loadError, setLoadError] = useState("");
  const [language, setLanguage] = useState("python3");
  const [code, setCode] = useState("");
  const [drafts, setDrafts] = useState<Array<Record<string, string>>>([]);
  const [activeCase, setActiveCase] = useState(0);
  const [result, setResult] = useState<JudgeResult | null>(null);
  const [busy, setBusy] = useState<"run" | "submit" | null>(null);
  const [actionError, setActionError] = useState("");
  const [leftTab, setLeftTab] = useState<"description" | "submissions">("description");
  const [bottomTab, setBottomTab] = useState<"testcase" | "result">("testcase");
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [problemListOpen, setProblemListOpen] = useState(false);
  const [confirmRestore, setConfirmRestore] = useState(false);
  const [splitX, setSplitX] = useState(46);
  const [splitY, setSplitY] = useState(61);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const theme = themeOverride ?? systemTheme;

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setSystemTheme(media.matches ? "dark" : "light");
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute(
      "content",
      theme === "dark" ? "#0d1113" : "#f5f7f8",
    );
  }, [theme]);

  useEffect(() => {
    document.title = problem ? `OpenOJ — ${problem.title}` : "OpenOJ — Practice library";
  }, [problem]);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    try { localStorage.setItem(THEME_STORAGE_KEY, next); } catch { /* Theme still changes for this session. */ }
    setThemeOverride(next);
  };

  useEffect(() => {
    api.getProblems().then(setProblems).catch((error: Error) => setListError(error.message));
  }, []);

  const openProblem = useCallback((slug: string) => {
    setActiveSlug(slug);
    setProblem(null);
    setLoadError("");
    setResult(null);
    setActionError("");
    setActiveCase(0);
    setSubmissions([]);
    setBottomTab("testcase");
    api.getProblem(slug).then((loaded) => {
      setProblem(loaded);
      const initialLanguage = Object.keys(loaded.languages).find((key) => loaded.languages[key].enabled) ?? "python3";
      setLanguage(initialLanguage);
      const saved = readDraft(loaded.slug, initialLanguage);
      const initialCode = saved ?? loaded.languages[initialLanguage].starter;
      setCode(initialCode);
      writeDraft(loaded.slug, initialLanguage, initialCode);
      setDrafts(loaded.public_cases.map((test) =>
        Object.fromEntries(Object.entries(test.input).map(([key, value]) => [key, JSON.stringify(value)])),
      ));
    }).catch((error: Error) => setLoadError(error.message));
  }, []);

  const goHome = useCallback(() => {
    setActiveSlug(null);
    setProblem(null);
    setProblemListOpen(false);
  }, []);

  const refreshSubmissions = useCallback(() => {
    if (!problem) return;
    api.getSubmissions(problem.slug).then(setSubmissions).catch(() => undefined);
  }, [problem]);

  useEffect(() => {
    if (leftTab === "submissions") refreshSubmissions();
  }, [leftTab, refreshSubmissions]);

  const parsedCases = useMemo(() => {
    try {
      return drafts.map((test) => Object.fromEntries(
        Object.entries(test).map(([key, value]) => [key, JSON.parse(value)]),
      ));
    } catch {
      return null;
    }
  }, [drafts]);

  const execute = useCallback(async (mode: "run" | "submit") => {
    if (!problem || busy) return;
    if (mode === "run" && !parsedCases) {
      setActionError("A testcase value is not valid JSON. Check the highlighted input and run again.");
      setBottomTab("testcase");
      return;
    }
    setBusy(mode);
    setActionError("");
    setBottomTab("result");
    setResult(null);
    try {
      const response = mode === "run"
        ? await api.run(problem.slug, language, code, parsedCases!)
        : await api.submit(problem.slug, language, code);
      setResult(response);
      if (mode === "submit") refreshSubmissions();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "The judge could not complete this request.");
    } finally {
      setBusy(null);
    }
  }, [busy, code, language, parsedCases, problem, refreshSubmissions]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        void execute(event.shiftKey ? "submit" : "run");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [execute]);

  const changeLanguage = (key: string) => {
    if (!problem) return;
    const next = readDraft(problem.slug, key) ?? problem.languages[key].starter;
    setLanguage(key);
    setCode(next);
    writeDraft(problem.slug, key, next);
  };

  const dragHorizontal = (event: React.PointerEvent) => {
    const startX = event.clientX;
    const start = splitX;
    const width = workspaceRef.current?.clientWidth ?? 1;
    event.currentTarget.setPointerCapture(event.pointerId);
    const move = (moveEvent: PointerEvent) => setSplitX(Math.min(68, Math.max(30, start + ((moveEvent.clientX - startX) / width) * 100)));
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };

  const dragVertical = (event: React.PointerEvent) => {
    const startY = event.clientY;
    const start = splitY;
    const height = rightRef.current?.clientHeight ?? 1;
    event.currentTarget.setPointerCapture(event.pointerId);
    const move = (moveEvent: PointerEvent) => setSplitY(Math.min(78, Math.max(32, start + ((moveEvent.clientY - startY) / height) * 100)));
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };

  if (listError) return <FullPageMessage icon={<CircleAlert />} title="The problem set could not load" detail={listError} />;
  if (!problems) return <FullPageMessage icon={<LoaderCircle className="spin" />} title="Preparing the judge bench" detail="Loading the problem set…" />;
  if (loadError) return <FullPageMessage icon={<CircleAlert />} title="OpenOJ could not load" detail={loadError} />;
  if (activeSlug === null) return <Landing problems={problems} theme={theme} onToggleTheme={toggleTheme} onOpen={openProblem} />;

  const currentIndex = problems.findIndex((entry) => entry.slug === activeSlug);
  const prevSlug = currentIndex > 0 ? problems[currentIndex - 1].slug : null;
  const nextSlug = currentIndex >= 0 && currentIndex + 1 < problems.length ? problems[currentIndex + 1].slug : null;

  if (!problem) return <FullPageMessage icon={<LoaderCircle className="spin" />} title="Preparing the judge bench" detail="Loading problem resources…" />;

  const languageConfig = problem.languages[language];
  const verdictTone = statusTone(result?.status);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-left">
          <button className="brand" onClick={goHome} aria-label="Back to all problems">
            <span className="brand-mark"><Code2 size={18} strokeWidth={2.4} /></span>
            <span>OpenOJ</span>
          </button>
          <span className="topbar-divider" />
          <button className="problem-list-trigger" onClick={() => setProblemListOpen(true)}>
            <List size={16} /> Problem list
          </button>
          <button
            className="icon-button"
            title="Previous problem"
            aria-label="Previous problem"
            disabled={!prevSlug}
            onClick={() => prevSlug && openProblem(prevSlug)}
          ><ChevronLeft size={18} /></button>
          <button
            className="icon-button"
            title="Next problem"
            aria-label="Next problem"
            disabled={!nextSlug}
            onClick={() => nextSlug && openProblem(nextSlug)}
          ><ChevronRight size={18} /></button>
        </div>
        <div className="top-actions">
          <button className="run-button" onClick={() => void execute("run")} disabled={busy !== null} title="Run tests (Ctrl/⌘ + Enter)">
            {busy === "run" ? <LoaderCircle className="spin" size={16} /> : <Play size={16} fill="currentColor" />}
            Run
          </button>
          <button className="submit-button" onClick={() => void execute("submit")} disabled={busy !== null} title="Submit (Ctrl/⌘ + Shift + Enter)">
            {busy === "submit" ? <LoaderCircle className="spin" size={16} /> : <Send size={16} />}
            Submit
          </button>
        </div>
        <div className="topbar-right">
          <a
            className="icon-button github-link"
            href="https://github.com/zydo/openoj"
            target="_blank"
            rel="noopener noreferrer"
            title="OpenOJ on GitHub"
            aria-label="OpenOJ on GitHub"
          >
            <Github size={16} />
          </a>
          <button
            className="icon-button theme-toggle"
            onClick={toggleTheme}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>
      </header>

      <main className="workspace" ref={workspaceRef} style={{ "--left-pane": `${splitX}%` } as React.CSSProperties}>
        <section className="panel problem-panel">
          <div className="panel-tabs">
            <button className={leftTab === "description" ? "tab active" : "tab"} onClick={() => setLeftTab("description")}>
              <FileText size={15} /> Description
            </button>
            <button className={leftTab === "submissions" ? "tab active" : "tab"} onClick={() => setLeftTab("submissions")}>
              <History size={15} /> Submissions
            </button>
          </div>
          {leftTab === "description" ? (
            <article className="problem-scroll">
              <div className="problem-heading">
                <h1>{problem.title}</h1>
                <div className="problem-meta">
                  <span className={`difficulty ${difficultyTone(problem.difficulty)}`}>{problem.difficulty}</span>
                  {problem.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
                </div>
              </div>
              <div className="markdown-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{problem.description}</ReactMarkdown>
              </div>
              <section className="hints">
                <h2>Hints</h2>
                {problem.hints.map((hint, index) => (
                  <details key={hint}>
                    <summary>Hint {index + 1}<ChevronDown size={16} /></summary>
                    <p>{hint}</p>
                  </details>
                ))}
              </section>
            </article>
          ) : (
            <Submissions submissions={submissions} problem={problem} />
          )}
        </section>

        <button className="splitter splitter-x" onPointerDown={dragHorizontal} aria-label="Resize problem and editor panes">
          <GripVertical size={14} />
        </button>

        <section className="right-stack" ref={rightRef} style={{ "--editor-pane": `${splitY}%` } as React.CSSProperties}>
          <section className="panel editor-panel">
            <div className="panel-heading">
              <span className="panel-title"><Code2 size={16} /> Code</span>
              <div className="editor-tools">
                <LanguageMenu
                  value={language}
                  options={Object.entries(problem.languages).map(([key, config]) => ({
                    key,
                    label: config.display_name,
                    enabled: config.enabled,
                  }))}
                  onChange={changeLanguage}
                />
                <button className="icon-button" title="Restore starter code" onClick={() => setConfirmRestore(true)}>
                  <RotateCcw size={15} />
                </button>
              </div>
            </div>
            <div className="editor-wrap">
              <Editor
                height="100%"
                language={languageConfig.monaco_language}
                value={code}
                onChange={(value) => {
                  setCode(value ?? "");
                  writeDraft(problem.slug, language, value ?? "");
                }}
                theme={theme === "dark" ? "vs-dark" : "light"}
                loading={<div className="editor-loading"><LoaderCircle className="spin" size={18} /> Loading syntax engine…</div>}
                options={{
                  automaticLayout: true,
                  fontFamily: "JetBrains Mono, ui-monospace, monospace",
                  fontSize: 14,
                  fontLigatures: true,
                  lineHeight: 23,
                  minimap: { enabled: false },
                  padding: { top: 14 },
                  scrollBeyondLastLine: false,
                  smoothScrolling: true,
                  tabSize: 4,
                  renderLineHighlight: "line",
                  bracketPairColorization: { enabled: true },
                  guides: { bracketPairs: true, indentation: true },
                }}
              />
            </div>
            <div className="editor-status">
              <span><span className="saved-dot" /> Saved locally</span>
              <span>{problem.limits.time_ms / 1000}s · {problem.limits.memory_mb} MB</span>
            </div>
          </section>

          <button className="splitter splitter-y" onPointerDown={dragVertical} aria-label="Resize editor and results panes" />

          <section className={`panel console-panel verdict-${verdictTone}`}>
            <div className="verdict-rail" />
            <div className="panel-tabs console-tabs">
              <button className={bottomTab === "testcase" ? "tab active" : "tab"} onClick={() => setBottomTab("testcase")}>
                <Braces size={15} /> Testcase
              </button>
              <button className={bottomTab === "result" ? "tab active" : "tab"} onClick={() => setBottomTab("result")}>
                <TerminalSquare size={15} /> Test result
                {result && <span className={`result-dot ${verdictTone}`} />}
              </button>
            </div>
            <div className="console-body">
              {bottomTab === "testcase" ? (
                <Testcases
                  problem={problem}
                  drafts={drafts}
                  setDrafts={setDrafts}
                  activeCase={activeCase}
                  setActiveCase={setActiveCase}
                />
              ) : (
                <Results result={result} busy={busy} error={actionError} />
              )}
            </div>
          </section>
        </section>
      </main>

      {problemListOpen && (
        <ProblemDrawer
          problems={problems}
          activeSlug={activeSlug}
          onSelect={(slug) => {
            setProblemListOpen(false);
            if (slug !== activeSlug) openProblem(slug);
          }}
          onClose={() => setProblemListOpen(false)}
        />
      )}

      {confirmRestore && (
        <ConfirmDialog
          title="Restore starter code?"
          body="Your current draft will be replaced. Saved drafts for other languages are kept."
          confirmLabel="Restore starter"
          onConfirm={() => {
            setConfirmRestore(false);
            setCode(languageConfig.starter);
            writeDraft(problem.slug, language, languageConfig.starter);
          }}
          onClose={() => setConfirmRestore(false)}
        />
      )}
    </div>
  );
}

function LanguageMenu({ value, options, onChange }: {
  value: string;
  options: Array<{ key: string; label: string; enabled: boolean }>;
  onChange: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const selected = options.find((option) => option.key === value);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  useEffect(() => {
    if (open) listRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    document.getElementById(`language-option-${activeIndex}`)?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, open]);

  const enabledIndexes = options.map((option, index) => (option.enabled ? index : -1)).filter((index) => index >= 0);

  const openMenu = () => {
    const current = options.findIndex((option) => option.key === value && option.enabled);
    setActiveIndex(current >= 0 ? current : (enabledIndexes[0] ?? 0));
    setOpen(true);
  };

  const close = (focusButton = true) => {
    setOpen(false);
    if (focusButton) buttonRef.current?.focus();
  };

  const select = (index: number) => {
    const option = options[index];
    if (!option?.enabled) return;
    onChange(option.key);
    close();
  };

  const move = (direction: 1 | -1) => {
    if (!enabledIndexes.length) return;
    const position = enabledIndexes.indexOf(activeIndex);
    const next = position === -1
      ? (direction === 1 ? enabledIndexes[0] : enabledIndexes[enabledIndexes.length - 1])
      : enabledIndexes[(position + direction + enabledIndexes.length) % enabledIndexes.length];
    setActiveIndex(next);
  };

  return (
    <div className="select-menu" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="select-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => (open ? close() : openMenu())}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            openMenu();
          }
        }}
      >
        {selected?.label ?? value}
        <ChevronDown size={14} className={open ? "select-chevron flipped" : "select-chevron"} />
      </button>
      {open && (
        <ul
          ref={listRef}
          className="select-popup"
          role="listbox"
          aria-label="Programming language"
          aria-activedescendant={`language-option-${activeIndex}`}
          tabIndex={-1}
          onKeyDown={(event) => {
          if (event.key === "ArrowDown") { event.preventDefault(); move(1); }
          else if (event.key === "ArrowUp") { event.preventDefault(); move(-1); }
          else if (event.key === "Home") { event.preventDefault(); if (enabledIndexes.length) setActiveIndex(enabledIndexes[0]); }
          else if (event.key === "End") { event.preventDefault(); if (enabledIndexes.length) setActiveIndex(enabledIndexes[enabledIndexes.length - 1]); }
          else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(activeIndex); }
          else if (event.key === "Escape") { event.preventDefault(); close(); }
          else if (event.key === "Tab") close(false);
        }}>
          {options.map((option, index) => (
            <li
              key={option.key}
              id={`language-option-${index}`}
              role="option"
              aria-selected={option.key === value}
              aria-disabled={!option.enabled}
              className={[
                "select-option",
                index === activeIndex ? "active" : "",
                option.key === value ? "selected" : "",
                option.enabled ? "" : "disabled",
              ].filter(Boolean).join(" ")}
              onMouseEnter={() => option.enabled && setActiveIndex(index)}
              onClick={() => select(index)}
            >
              <span>{option.label}{option.enabled ? "" : " — coming soon"}</span>
              {option.key === value && <Check size={13} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ConfirmDialog({ title, body, confirmLabel, cancelLabel = "Cancel", onConfirm, onClose }: {
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    dialog.querySelector<HTMLElement>("button")?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusables = Array.from(dialog.querySelectorAll<HTMLElement>("button:not(:disabled)"));
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    dialog.addEventListener("keydown", onKeyDown);
    return () => dialog.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="dialog-backdrop" onMouseDown={onClose}>
      <div
        ref={dialogRef}
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        aria-describedby="dialog-body"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h2 id="dialog-title">{title}</h2>
        <p id="dialog-body">{body}</p>
        <div className="dialog-actions">
          <button type="button" className="dialog-cancel" onClick={onClose}>{cancelLabel}</button>
          <button type="button" className="dialog-confirm" onClick={onConfirm} autoFocus>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

function Landing({ problems, theme, onToggleTheme, onOpen }: {
  problems: ProblemSummary[];
  theme: Theme;
  onToggleTheme: () => void;
  onOpen: (slug: string) => void;
}) {
  const featured = problems.find((entry) => entry.slug === DEFAULT_SLUG);
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-left">
          <button className="brand" aria-label="OpenOJ home">
            <span className="brand-mark"><Code2 size={18} strokeWidth={2.4} /></span>
            <span>OpenOJ</span>
          </button>
        </div>
        <div className="topbar-right">
          <a
            className="icon-button github-link"
            href="https://github.com/zydo/openoj"
            target="_blank"
            rel="noopener noreferrer"
            title="OpenOJ on GitHub"
            aria-label="OpenOJ on GitHub"
          >
            <Github size={16} />
          </a>
          <button
            className="icon-button theme-toggle"
            onClick={onToggleTheme}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>
      </header>
      <main className="landing">
        <div className="landing-inner">
          {featured && (
            <section className="hero-card panel">
              <div className="hero-main">
                <div className="problem-kicker">Featured problem</div>
                <h1>{featured.title}</h1>
                <div className="problem-meta">
                  <span className={`difficulty ${difficultyTone(featured.difficulty)}`}>{featured.difficulty}</span>
                  {featured.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
                </div>
                <p>Return the indices of the two numbers in the array that add up to the target — the classic opener, and the fastest way to see the judge at work.</p>
              </div>
              <button className="hero-cta" onClick={() => onOpen(featured.slug)}>
                <Play size={15} fill="currentColor" />
                Open {featured.title}
              </button>
            </section>
          )}
          <section className="landing-index">
            <header className="index-header">
              <h2>All problems</h2>
              <span>{problems.length} {problems.length === 1 ? "problem" : "problems"} · sorted alphabetically</span>
            </header>
            <div className="landing-list">
              {problems.map((entry) => (
                <button
                  key={entry.slug}
                  className="problem-row"
                  onClick={() => onOpen(entry.slug)}
                >
                  <span className="problem-row-main">
                    <strong>{entry.title}</strong>
                    <small>{entry.tags.join(" · ")}</small>
                  </span>
                  <span className={`difficulty ${difficultyTone(entry.difficulty)}`}>{entry.difficulty}</span>
                </button>
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

function Testcases({ problem, drafts, setDrafts, activeCase, setActiveCase }: {
  problem: Problem;
  drafts: Array<Record<string, string>>;
  setDrafts: React.Dispatch<React.SetStateAction<Array<Record<string, string>>>>;
  activeCase: number;
  setActiveCase: (index: number) => void;
}) {
  const current = drafts[activeCase];
  if (!current) return null;
  return (
    <div className="testcase-view">
      <div className="case-tabs">
        {drafts.map((_, index) => (
          <button key={index} className={index === activeCase ? "case-tab active" : "case-tab"} onClick={() => setActiveCase(index)}>
            Case {index + 1}
            {drafts.length > 1 && index === activeCase && (
              <span className="remove-case" role="button" aria-label={`Remove case ${index + 1}`} onClick={(event) => {
                event.stopPropagation();
                setDrafts((items) => items.filter((_, itemIndex) => itemIndex !== index));
                setActiveCase(Math.max(0, index - 1));
              }}><X size={12} /></span>
            )}
          </button>
        ))}
        <button className="add-case" title="Add testcase" onClick={() => {
          const blank = Object.fromEntries(problem.invocation.parameters.map(({ name }) => [name, name === "nums" ? "[]" : "0"]));
          setDrafts((items) => [...items, blank]);
          setActiveCase(drafts.length);
        }}><Plus size={15} /></button>
      </div>
      <div className="case-fields">
        {problem.invocation.parameters.map(({ name: parameter }) => {
          let valid = true;
          try { JSON.parse(current[parameter]); } catch { valid = false; }
          return (
            <label className="case-field" key={parameter}>
              <span>{parameter} =</span>
              <textarea
                value={current[parameter] ?? ""}
                className={valid ? "" : "invalid"}
                spellCheck={false}
                rows={parameter === "nums" ? 2 : 1}
                onChange={(event) => setDrafts((items) => items.map((item, index) =>
                  index === activeCase ? { ...item, [parameter]: event.target.value } : item,
                ))}
              />
            </label>
          );
        })}
      </div>
    </div>
  );
}

function Results({ result, busy, error }: { result: JudgeResult | null; busy: string | null; error: string }) {
  const [openCase, setOpenCase] = useState(0);
  useEffect(() => setOpenCase(0), [result]);
  if (busy) return <ConsoleEmpty icon={<LoaderCircle className="spin" />} title={busy === "submit" ? "Judging every case" : "Running testcases"} detail="Code is executing inside the isolated language runner." />;
  if (error) return <ConsoleEmpty icon={<CircleAlert />} title="Execution stopped" detail={error} tone="danger" />;
  if (!result) return <ConsoleEmpty icon={<TerminalSquare />} title="No results yet" detail="Run your code against visible cases, or submit it to the full judge." />;
  const active = result.results[openCase];
  const tone = statusTone(result.status);
  return (
    <div className="results-view">
      <div className={`result-summary ${tone}`}>
        <div className="verdict-icon">{tone === "success" ? <Check size={20} /> : <X size={20} />}</div>
        <div>
          <strong>{statusLabel(result.status)}</strong>
          <span>{result.passed} of {result.total} cases passed</span>
        </div>
        <div className="runtime"><Clock3 size={14} /> {result.runtime_ms} ms</div>
        {result.reference_runtime_ms != null && result.reference_runtime_ms > 0 && (
          <div
            className="runtime"
            title={`Reference solution: ${result.reference_runtime_ms} ms on the same judge and cases`}
          >
            <Clock3 size={14} /> {Math.round((result.runtime_ms / result.reference_runtime_ms) * 100)}% of reference
          </div>
        )}
      </div>
      <div className="result-layout">
        <div className="result-case-list">
          {result.results.map((test, index) => (
            <button key={`${test.name}-${index}`} className={openCase === index ? "result-case active" : "result-case"} onClick={() => setOpenCase(index)}>
              <span className={`case-status ${statusTone(test.status)}`}>{statusTone(test.status) === "success" ? <Check size={12} /> : <X size={12} />}</span>
              <span>{test.name}</span>
              <small>{test.runtime_ms === undefined ? "Hidden" : `${test.runtime_ms} ms`}</small>
            </button>
          ))}
        </div>
        {active && (
          <div className="result-detail">
            <div className="detail-heading">
              <span className={`status-text ${statusTone(active.status)}`}>{statusLabel(active.status)}</span>
              <span>{active.runtime_ms === undefined
                ? "Timing hidden"
                : `${active.runtime_ms} ms${active.timeout_ms ? ` / ${active.timeout_ms} ms limit` : ""}`}</span>
            </div>
            {active.error && <div className="error-box">{active.error}</div>}
            {active.input !== undefined ? (
              <>
                <ResultValue label="Input" value={active.input} />
                {active.actual !== undefined && <ResultValue label="Output" value={active.actual} />}
                {active.expected !== undefined && <ResultValue label="Expected" value={active.expected} />}
                {active.stdout && <ResultValue label="Stdout" value={active.stdout} raw />}
              </>
            ) : <p className="hidden-copy">Hidden testcase details stay sealed inside the judge.</p>}
          </div>
        )}
      </div>
    </div>
  );
}

function ResultValue({ label, value, raw = false }: { label: string; value: unknown; raw?: boolean }) {
  return <div className="result-value"><span>{label}</span><pre>{raw ? String(value) : formatJson(value)}</pre></div>;
}

function Submissions({ submissions, problem }: { submissions: Submission[]; problem: Problem }) {
  if (!submissions.length) return <ConsoleEmpty icon={<History />} title="No submissions yet" detail="Submit a solution and its verdict will be saved here." />;
  return (
    <div className="submission-list">
      <div className="submission-header"><span>Verdict</span><span>Language</span><span>Runtime</span><span>Submitted</span></div>
      {submissions.map((submission) => (
        <div className="submission-row" key={submission.id}>
          <span className={`status-text ${statusTone(submission.status)}`}>{statusLabel(submission.status)}</span>
          <span>{problem.languages[submission.language]?.display_name ?? submission.language}</span>
          <span>{submission.runtime_ms} ms</span>
          <time>{new Date(submission.created_at).toLocaleString()}</time>
        </div>
      ))}
    </div>
  );
}

function ProblemDrawer({ problems, activeSlug, onSelect, onClose }: {
  problems: ProblemSummary[];
  activeSlug: string;
  onSelect: (slug: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const filterRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    filterRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const normalized = query.trim().toLowerCase();
  const filtered = normalized
    ? problems.filter((entry) =>
        entry.title.toLowerCase().includes(normalized)
        || entry.slug.includes(normalized)
        || entry.tags.some((tag) => tag.toLowerCase().includes(normalized)),
      )
    : problems;

  return (
    <div className="drawer-backdrop" onMouseDown={onClose}>
      <aside className="drawer" onMouseDown={(event) => event.stopPropagation()}>
        <div className="drawer-heading">
          <div><span>Problem set</span><strong>Practice library</strong></div>
          <button className="icon-button" onClick={onClose} aria-label="Close problem list"><X size={18} /></button>
        </div>
        <div className="drawer-tools">
          <input
            ref={filterRef}
            className="drawer-filter"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter by title, slug, or tag"
            aria-label="Filter problems"
          />
          <span className="drawer-count">{filtered.length} of {problems.length} problems</span>
        </div>
        <div className="drawer-list">
          {filtered.length ? filtered.map((entry) => (
            <button
              key={entry.slug}
              className={entry.slug === activeSlug ? "problem-row active" : "problem-row"}
              onClick={() => onSelect(entry.slug)}
            >
              <span className="problem-row-main">
                <strong>{entry.title}</strong>
                <small>{entry.tags.join(" · ")}</small>
              </span>
              <span className={`difficulty ${difficultyTone(entry.difficulty)}`}>{entry.difficulty}</span>
            </button>
          )) : <p className="drawer-empty">No problems match “{query.trim()}”.</p>}
        </div>
      </aside>
    </div>
  );
}

function ConsoleEmpty({ icon, title, detail, tone = "" }: { icon: React.ReactNode; title: string; detail: string; tone?: string }) {
  return <div className={`console-empty ${tone}`}><span>{icon}</span><strong>{title}</strong><p>{detail}</p></div>;
}

function FullPageMessage({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) {
  return <main className="full-page-message"><span>{icon}</span><h1>{title}</h1><p>{detail}</p></main>;
}

export default App;
