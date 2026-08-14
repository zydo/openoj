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

const SLUG = "two-sum";
const THEME_STORAGE_KEY = "openoj:theme";
type Theme = "light" | "dark";

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

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function App() {
  const [themeOverride, setThemeOverride] = useState<Theme | null>(storedTheme);
  const [systemTheme, setSystemTheme] = useState<Theme>(preferredTheme);
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

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    try { localStorage.setItem(THEME_STORAGE_KEY, next); } catch { /* Theme still changes for this session. */ }
    setThemeOverride(next);
  };

  useEffect(() => {
    api.getProblem(SLUG).then((loaded) => {
      setProblem(loaded);
      const initialLanguage = Object.keys(loaded.languages).find((key) => loaded.languages[key].enabled) ?? "python3";
      setLanguage(initialLanguage);
      const saved = localStorage.getItem(`openoj:${loaded.slug}:${initialLanguage}`);
      setCode(saved ?? loaded.languages[initialLanguage].starter);
      setDrafts(loaded.public_cases.map((test) =>
        Object.fromEntries(Object.entries(test.input).map(([key, value]) => [key, JSON.stringify(value)])),
      ));
    }).catch((error: Error) => setLoadError(error.message));
  }, []);

  useEffect(() => {
    if (problem && code) localStorage.setItem(`openoj:${problem.slug}:${language}`, code);
  }, [code, language, problem]);

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

  if (loadError) return <FullPageMessage icon={<CircleAlert />} title="OpenOJ could not load" detail={loadError} />;
  if (!problem) return <FullPageMessage icon={<LoaderCircle className="spin" />} title="Preparing the judge bench" detail="Loading problem resources…" />;

  const languageConfig = problem.languages[language];
  const verdictTone = statusTone(result?.status);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-left">
          <button className="brand" onClick={() => setProblemListOpen(true)} aria-label="Open problem list">
            <span className="brand-mark"><Code2 size={18} strokeWidth={2.4} /></span>
            <span>OpenOJ</span>
          </button>
          <span className="topbar-divider" />
          <button className="problem-list-trigger" onClick={() => setProblemListOpen(true)}>
            <List size={16} /> Problem list
          </button>
          <button className="icon-button" title="Previous problem" disabled><ChevronLeft size={18} /></button>
          <button className="icon-button" title="Next problem" disabled><ChevronRight size={18} /></button>
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
          <button
            className="icon-button theme-toggle"
            onClick={toggleTheme}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <div className="session-pill" title="Single-user workspace">
            <span className="session-dot" /> Local session
          </div>
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
                <div className="problem-kicker">Problem {String(problem.id).padStart(3, "0")}</div>
                <h1>{problem.id}. {problem.title}</h1>
                <div className="problem-meta">
                  <span className="difficulty">{problem.difficulty}</span>
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
              <footer className="problem-source">
                {problem.source && <>Demo adapted from <a href={problem.source.url} target="_blank" rel="noreferrer">{problem.source.label}</a>.</>}
              </footer>
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
                <label className="select-wrap">
                  <select value={language} onChange={(event) => {
                    const next = event.target.value;
                    setLanguage(next);
                    setCode(localStorage.getItem(`openoj:${problem.slug}:${next}`) ?? problem.languages[next].starter);
                  }} aria-label="Programming language">
                    {Object.entries(problem.languages).map(([key, config]) => (
                      <option key={key} value={key} disabled={!config.enabled}>
                        {config.display_name}{config.enabled ? "" : " — coming soon"}
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={14} />
                </label>
                <button className="icon-button" title="Restore starter code" onClick={() => {
                  if (window.confirm("Restore the starter code? Your current draft will be replaced.")) setCode(languageConfig.starter);
                }}><RotateCcw size={15} /></button>
              </div>
            </div>
            <div className="editor-wrap">
              <Editor
                height="100%"
                language={languageConfig.monaco_language}
                value={code}
                onChange={(value) => setCode(value ?? "")}
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

      {problemListOpen && <ProblemDrawer problem={problem} onClose={() => setProblemListOpen(false)} />}
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

function ProblemDrawer({ problem, onClose }: { problem: Problem; onClose: () => void }) {
  return (
    <div className="drawer-backdrop" onMouseDown={onClose}>
      <aside className="drawer" onMouseDown={(event) => event.stopPropagation()}>
        <div className="drawer-heading">
          <div><span>Problem set</span><strong>Practice library</strong></div>
          <button className="icon-button" onClick={onClose} aria-label="Close problem list"><X size={18} /></button>
        </div>
        <div className="drawer-search">1 problem sideloaded from <code>/problems</code></div>
        <button className="problem-row active" onClick={onClose}>
          <span className="problem-number">{String(problem.id).padStart(3, "0")}</span>
          <span><strong>{problem.title}</strong><small>{problem.tags.join(" · ")}</small></span>
          <span className="difficulty">{problem.difficulty}</span>
        </button>
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
