import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Braces,
  Check,
  ChevronDown,
  Copy,
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
import { api, onUnauthorized } from "./api";
import type { JudgeResult, Problem, ProblemSummary, SolutionsContent, Submission } from "./types";

type Theme = "light" | "dark";

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

// The active problem lives in the URL (/problems/:slug) so each problem is a
// page, browser back returns to the list, and links are shareable.
function slugFromPath(): string | null {
  const match = window.location.pathname.match(/^\/problems\/([a-z0-9]+(?:-[a-z0-9]+)*)\/?$/);
  return match ? match[1] : null;
}

// The last chosen language carries across problems within the session; each
// problem still keeps its own per-language server-side draft.
const LANGUAGE_STORAGE_KEY = "openoj:language";

function storedLanguage(): string {
  try {
    return sessionStorage.getItem(LANGUAGE_STORAGE_KEY) ?? "python3";
  } catch {
    return "python3";
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

// The judge's own short-hand for a verdict — what competitive programmers
// read at a glance (AC, WA, TLE…). Stamped on the result seal.
function verdictCode(status: string) {
  const codes: Record<string, string> = {
    accepted: "AC",
    completed: "OK",
    wrong_answer: "WA",
    compile_error: "CE",
    runtime_error: "RE",
    time_limit_exceeded: "TLE",
    memory_limit_exceeded: "MLE",
    system_error: "JE",
  };
  return codes[status] ?? status.replaceAll("_", " ").split(" ").map((word) => word[0]?.toUpperCase() ?? "").join("").slice(0, 3);
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

// The curated problem set grades difficulty on a five-level scale (H1–H5);
// display the levels as words rather than raw labels.
const DIFFICULTY_LABELS: Record<string, string> = {
  H1: "Very Easy",
  H2: "Easy",
  H3: "Medium",
  H4: "Hard",
  H5: "Very Hard",
};

function difficultyLabel(difficulty: string) {
  return DIFFICULTY_LABELS[difficulty] ?? difficulty;
}

// Search normalization: case-insensitive and blind to punctuation, so
// "two-sum" is found by "two sum" or "two+sum".
function searchText(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function matchesFilter(entry: ProblemSummary, normalizedQuery: string) {
  return searchText(entry.title).includes(normalizedQuery)
    || entry.tags.some((tag) => searchText(tag).includes(normalizedQuery));
}

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function formatTolerance(tolerance: number | undefined) {
  const value = tolerance ?? 1e-9;
  return value >= 0.001 ? String(value) : `1e${Math.round(Math.log10(value))}`;
}

function App() {
  const [themeOverride, setThemeOverride] = useState<Theme | null>(storedTheme);
  const [systemTheme, setSystemTheme] = useState<Theme>(preferredTheme);
  // Guest-session gate: "checking" while the session cookie is validated,
  // "gate" shows the Continue-as-guest entrance (the only way in until
  // accounts exist), "active" runs the app. An idle-expired session mid-use
  // returns to the gate with a notice.
  const [sessionPhase, setSessionPhase] = useState<"checking" | "gate" | "active">("checking");
  const [sessionExpired, setSessionExpired] = useState(false);
  const [gateError, setGateError] = useState("");
  // Full problem list, fetched lazily only when the editor opens (prev/next
  // navigation and the drawer need the whole ordering). The landing page
  // fetches its own paginated slice instead.
  const [allProblems, setAllProblems] = useState<ProblemSummary[] | null>(null);
  const [problemsError, setProblemsError] = useState("");
  const [activeSlug, setActiveSlug] = useState<string | null>(slugFromPath);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [loadError, setLoadError] = useState("");
  const [language, setLanguage] = useState<string>(storedLanguage);
  const [code, setCode] = useState("");
  const [drafts, setDrafts] = useState<Array<Record<string, string>>>([]);
  const [activeCase, setActiveCase] = useState(0);
  const [result, setResult] = useState<JudgeResult | null>(null);
  const [busy, setBusy] = useState<"run" | "submit" | null>(null);
  const [actionError, setActionError] = useState("");
  const [leftTab, setLeftTab] = useState<"description" | "submissions" | "solutions">("description");
  const [bottomTab, setBottomTab] = useState<"testcase" | "result">("testcase");
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [problemListOpen, setProblemListOpen] = useState(false);
  const [confirmRestore, setConfirmRestore] = useState(false);
  const [splitX, setSplitX] = useState(46);
  const [splitY, setSplitY] = useState(61);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const theme = themeOverride ?? systemTheme;

  // Server-side drafts (session-scoped): loaded per problem, cached locally
  // for instant language switches, and flushed to the server on a short
  // debounce so editor state survives refreshes and idle-expiry clears it.
  const draftCache = useRef(new Map<string, string>());
  const pendingDrafts = useRef(new Map<string, { slug: string; language: string; code: string }>());
  const draftTimer = useRef<number | null>(null);
  const flushDrafts = useCallback(() => {
    if (draftTimer.current !== null) {
      window.clearTimeout(draftTimer.current);
      draftTimer.current = null;
    }
    const pending = [...pendingDrafts.current.values()];
    pendingDrafts.current.clear();
    for (const draft of pending) {
      api.putDraft(draft.slug, draft.language, draft.code).catch(() => undefined);
    }
  }, []);
  const saveDraft = useCallback((slug: string, language: string, code: string) => {
    draftCache.current.set(`${slug}:${language}`, code);
    pendingDrafts.current.set(`${slug}:${language}`, { slug, language, code });
    if (draftTimer.current === null) {
      draftTimer.current = window.setTimeout(flushDrafts, 700);
    }
  }, [flushDrafts]);

  useEffect(() => {
    api.sessionStatus()
      .then(() => setSessionPhase("active"))
      .catch(() => setSessionPhase("gate"))
      .finally(() => {
        // Registered after the boot probe so the expected first-visit 401
        // does not read as "your session expired". Any later 401 (idle
        // expiry mid-use) routes back to the gate with the notice.
        onUnauthorized(() => {
          flushDrafts();
          draftCache.current.clear();
          pendingDrafts.current.clear();
          setSessionPhase("gate");
          setSessionExpired(true);
        });
      });
    const onHide = () => {
      if (document.visibilityState === "hidden") flushDrafts();
    };
    document.addEventListener("visibilitychange", onHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      flushDrafts();
    };
  }, [flushDrafts]);

  const enterAsGuest = useCallback(() => {
    api.startSession()
      .then(() => {
        setSessionExpired(false);
        setGateError("");
        setSessionPhase("active");
      })
      .catch(() => setGateError("Could not start a session — check the connection and try again."));
  }, []);

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

  const problemsRequested = useRef(false);
  const ensureProblems = useCallback(() => {
    if (problemsRequested.current) return;
    problemsRequested.current = true;
    api.getProblems().then((page) => {
      setAllProblems(page.items);
    }).catch((error: Error) => {
      problemsRequested.current = false; // allow a retry on the next open
      setProblemsError(error.message);
    });
  }, []);

  // Keep activeSlug in sync with the URL when the user navigates back/forward.
  useEffect(() => {
    const onPopState = () => {
      setActiveSlug(slugFromPath());
      setProblemListOpen(false);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const openProblem = useCallback((slug: string) => {
    if (slug === activeSlug) return;
    window.history.pushState(null, "", `/problems/${slug}`);
    setActiveSlug(slug);
  }, [activeSlug]);

  const goHome = useCallback(() => {
    if (activeSlug === null) return;
    window.history.pushState(null, "", "/");
    setActiveSlug(null);
    setProblemListOpen(false);
  }, [activeSlug]);

  // Load the active problem. Keyed on the URL-derived activeSlug, so opening a
  // problem, deep-linking to one, and back/forward navigation all go through
  // the same path.
  useEffect(() => {
    if (!activeSlug) {
      setProblem(null);
      setProblemListOpen(false);
      return;
    }
    ensureProblems();
    setProblem(null);
    setLoadError("");
    setResult(null);
    setActionError("");
    setActiveCase(0);
    setSubmissions([]);
    setBottomTab("testcase");
    let cancelled = false;
    Promise.all([
      api.getProblem(activeSlug),
      api.getDrafts(activeSlug).catch(() => []),
    ]).then(([loaded, draftRows]) => {
      if (cancelled) return;
      setProblem(loaded);
      for (const row of draftRows) {
        const key = `${loaded.slug}:${row.language}`;
        // A locally pending save is newer than whatever the server returned.
        if (!pendingDrafts.current.has(key)) {
          draftCache.current.set(key, row.code);
        }
      }
      const enabled = (key: string) => loaded.languages[key]?.enabled;
      const recent = draftRows.find((row) => enabled(row.language))?.language;
      const preferred = storedLanguage();
      const initialLanguage = (recent && enabled(recent) ? recent : undefined)
        ?? (enabled(preferred) ? preferred : undefined)
        ?? (Object.keys(loaded.languages).find(enabled) ?? "python3");
      setLanguage(initialLanguage);
      const saved = draftCache.current.get(`${loaded.slug}:${initialLanguage}`);
      const initialCode = saved ?? loaded.languages[initialLanguage].starter;
      setCode(initialCode);
      setDrafts(loaded.public_cases.map((test) =>
        Object.fromEntries(Object.entries(test.input).map(([key, value]) => [key, JSON.stringify(value)])),
      ));
    }).catch((error: Error) => {
      if (!cancelled) setLoadError(error.message);
    });
    return () => { cancelled = true; };
  }, [activeSlug, ensureProblems]);

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
    try { sessionStorage.setItem(LANGUAGE_STORAGE_KEY, key); } catch { /* Preference is best-effort. */ }
    flushDrafts();
    const next = draftCache.current.get(`${problem.slug}:${key}`) ?? problem.languages[key].starter;
    setLanguage(key);
    setCode(next);
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

  if (sessionPhase !== "active") {
    if (sessionPhase === "checking") {
      return <FullPageMessage icon={<LoaderCircle className="spin" />} title="Preparing the judge bench" detail="Checking your session…" />;
    }
    return <GuestGate expired={sessionExpired} error={gateError} onEnter={enterAsGuest} theme={theme} onToggleTheme={toggleTheme} />;
  }
  if (loadError) return <FullPageMessage icon={<CircleAlert />} title="OpenOJ could not load" detail={loadError} />;
  if (activeSlug === null) return <Landing theme={theme} onToggleTheme={toggleTheme} onOpen={openProblem} />;
  if (problemsError && allProblems === null) {
    return <FullPageMessage icon={<CircleAlert />} title="The problem set could not load" detail={problemsError} />;
  }
  if (!problem || !allProblems) return <FullPageMessage icon={<LoaderCircle className="spin" />} title="Preparing the judge bench" detail="Loading problem resources…" />;

  const currentIndex = allProblems.findIndex((entry) => entry.slug === activeSlug);
  const prevSlug = currentIndex > 0 ? allProblems[currentIndex - 1].slug : null;
  const nextSlug = currentIndex >= 0 && currentIndex + 1 < allProblems.length ? allProblems[currentIndex + 1].slug : null;

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
            <button className={leftTab === "solutions" ? "tab active" : "tab"} onClick={() => setLeftTab("solutions")}>
              <Braces size={15} /> Solutions
            </button>
          </div>
          {leftTab === "description" ? (
            <article className="problem-scroll">
              <div className="problem-heading">
                <h1>{problem.title}</h1>
                <div className="problem-meta">
                  <span className={`difficulty ${difficultyTone(problem.difficulty)}`}>{difficultyLabel(problem.difficulty)}</span>
                  {problem.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
                </div>
              </div>
              <div className="markdown-body">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    // Statement figures live beside the bundle (figures/*.svg)
                    // and are served by the API; rewrite the relative refs.
                    img: ({ src, alt }) => (
                      <img
                        className="statement-figure"
                        src={typeof src === "string" && src.startsWith("figures/")
                          ? `/api/problems/${problem.slug}/${src}`
                          : src}
                        alt={alt ?? ""}
                        loading="lazy"
                      />
                    ),
                  }}
                >{problem.description}</ReactMarkdown>
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
          ) : leftTab === "solutions" ? (
            <Solutions key={problem.slug} slug={problem.slug} fallbackLanguage={language} languages={problem.languages} theme={theme} />
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
                  saveDraft(problem.slug, language, value ?? "");
                }}
                theme={theme === "dark" ? "openoj-dark" : "openoj-light"}
                loading={<div className="editor-loading"><LoaderCircle className="spin" size={18} /> Loading syntax engine…</div>}
                options={{
                  automaticLayout: true,
                  fontFamily: "Roboto Mono, ui-monospace, monospace",
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
              <span><span className="saved-dot" /> Saved</span>
              <span className="editor-shortcut" aria-hidden="true">⏎ run · ⇧⏎ submit</span>
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
                <Results result={result} busy={busy} error={actionError} comparison={problem.invocation.comparison} />
              )}
            </div>
          </section>
        </section>
      </main>

      {problemListOpen && (
        <ProblemDrawer
          problems={allProblems!}
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
            saveDraft(problem.slug, language, languageConfig.starter);
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

const LANDING_PAGE_SIZE = 50;

function pageNumbers(current: number, pages: number): Array<number | "ellipsis-start" | "ellipsis-end"> {
  // Small sets get every page; larger ones keep the first and last page and
  // a seven-page window around the current one, shifted to stay full when the
  // current page hugs either end.
  if (pages <= 9) return Array.from({ length: pages }, (_, index) => index + 1);
  let start = Math.max(2, current - 3);
  let end = Math.min(pages - 1, current + 3);
  if (end - start < 6) {
    if (start === 2) end = Math.min(pages - 1, start + 6);
    else start = Math.max(2, end - 6);
  }
  const numbers: Array<number | "ellipsis-start" | "ellipsis-end"> = [1];
  if (start > 2) numbers.push("ellipsis-start");
  for (let page = start; page <= end; page += 1) numbers.push(page);
  if (end < pages - 1) numbers.push("ellipsis-end");
  numbers.push(pages);
  return numbers;
}

function Landing({ theme, onToggleTheme, onOpen }: {
  theme: Theme;
  onToggleTheme: () => void;
  onOpen: (slug: string) => void;
}) {
  const [items, setItems] = useState<ProblemSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  // Full problem set for the search box; the rendered page alone would miss
  // problems on later pages.
  const [allItems, setAllItems] = useState<ProblemSummary[] | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const loadPage = useCallback((target: number) => {
    setLoading(true);
    setError("");
    api.getProblems(target, LANDING_PAGE_SIZE).then((data) => {
      setItems(data.items);
      setTotal(data.total);
      setPage(data.page);
      setPages(data.pages);
    }).catch((loadError: Error) => setError(loadError.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadPage(1);
  }, [loadPage]);

  useEffect(() => {
    let cancelled = false;
    api.getProblems().then((data) => {
      if (!cancelled) setAllItems(data.items);
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  const goToPage = (target: number) => {
    if (target < 1 || target > pages || target === page) return;
    loadPage(target);
    listRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  };

  const normalized = searchText(query);
  const filtered = normalized && allItems
    ? allItems.filter((entry) => matchesFilter(entry, normalized))
    : null;

  const renderRow = (entry: ProblemSummary) => (
    <button
      key={entry.slug}
      className="problem-row"
      onClick={() => onOpen(entry.slug)}
    >
      <span className="problem-row-main">
        <strong>{entry.title}</strong>
        {entry.tags.length > 0 && <small>{entry.tags.join(" · ")}</small>}
      </span>
      <span className={`difficulty ${difficultyTone(entry.difficulty)}`}>{difficultyLabel(entry.difficulty)}</span>
    </button>
  );

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
          <section className="landing-index" ref={listRef}>
            <header className="landing-masthead">
              <div className="landing-masthead-row">
                <h1>All problems</h1>
                <span className="landing-count">
                  {filtered !== null
                    ? `${filtered.length} of ${allItems?.length ?? total} problems`
                    : `${total} ${total === 1 ? "problem" : "problems"}`}
                </span>
              </div>
            </header>
            <div className="landing-filter">
              <input
                className="landing-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Filter by title or tag"
                aria-label="Filter problems"
              />
            </div>
            {error ? (
              <p className="landing-error">{error}</p>
            ) : filtered !== null ? (
              <div className="landing-list">
                {filtered.length ? filtered.map(renderRow) : (
                  <p className="landing-empty">No problems match “{query.trim()}”.</p>
                )}
              </div>
            ) : loading && items.length === 0 ? (
              <div className="landing-list">
                <p className="landing-loading"><LoaderCircle className="spin" size={16} /> Loading the problem set…</p>
              </div>
            ) : (
              <>
                <div className="landing-list">
                  {items.map(renderRow)}
                </div>
                {pages > 1 && (
                  <nav className="pagination" aria-label="Problem pages">
                    <button className="page-button" disabled={page <= 1} onClick={() => goToPage(1)} aria-label="First page">«</button>
                    <button className="page-button" disabled={page <= 1} onClick={() => goToPage(page - 1)} aria-label="Previous page">‹</button>
                    {pageNumbers(page, pages).map((entry) =>
                      typeof entry === "number" ? (
                        <button
                          key={entry}
                          className={`page-button${entry === page ? " active" : ""}`}
                          onClick={() => goToPage(entry)}
                          aria-current={entry === page ? "page" : undefined}
                        >
                          {entry}
                        </button>
                      ) : (
                        <span key={entry} className="page-ellipsis">…</span>
                      ),
                    )}
                    <button className="page-button" disabled={page >= pages} onClick={() => goToPage(page + 1)} aria-label="Next page">›</button>
                    <button className="page-button" disabled={page >= pages} onClick={() => goToPage(pages)} aria-label="Last page">»</button>
                    <span className="page-status">Page {page} of {pages}</span>
                  </nav>
                )}
              </>
            )}
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

function Results({ result, busy, error, comparison }: { result: JudgeResult | null; busy: string | null; error: string; comparison?: Problem["invocation"]["comparison"] }) {
  const [openCase, setOpenCase] = useState(0);
  useEffect(() => setOpenCase(0), [result]);
  if (busy) return <ConsoleEmpty icon={<LoaderCircle className="spin" />} title="Executing code and judging" />;
  if (error) return <ConsoleEmpty icon={<CircleAlert />} title="Execution stopped" detail={error} tone="danger" />;
  if (!result) return <ConsoleEmpty icon={<TerminalSquare />} title="No results yet" detail="Run to check your code against the visible cases, or Submit to face the full judge." />;
  const active = result.results[openCase];
  const tone = statusTone(result.status);
  return (
    <div className="results-view">
      <div className={`result-summary ${tone}`}>
        <span className="seal" title={statusLabel(result.status)}>{verdictCode(result.status)}</span>
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
                {active.expected !== undefined && <ResultValue
                    label={comparison === "close" || (typeof comparison === "object" && comparison !== null && comparison.mode === "close")
                      ? `Expected ±${formatTolerance(typeof comparison === "object" && comparison !== null ? comparison.tolerance : undefined)}`
                      : "Expected"}
                    value={active.expected}
                  />}
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

function Solutions({ slug, fallbackLanguage, languages, theme }: {
  slug: string;
  fallbackLanguage: string;
  languages: Problem["languages"];
  theme: Theme;
}) {
  const [content, setContent] = useState<SolutionsContent | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "empty">("loading");
  const [langByVariant, setLangByVariant] = useState<Record<string, string>>({});

  useEffect(() => {
    setLangByVariant((current) => {
      const next: Record<string, string> = {};
      for (const key of Object.keys(current)) next[key] = fallbackLanguage;
      return next;
    });
  }, [fallbackLanguage]);

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    api.getSolutions(slug).then((loaded) => {
      if (cancelled) return;
      setContent(loaded);
      setState("ready");
    }).catch(() => {
      if (!cancelled) setState("empty");
    });
    return () => { cancelled = true; };
  }, [slug]);

  if (state === "loading") {
    return <FullPageMessage icon={<LoaderCircle className="spin" />} title="Loading solutions" detail="Fetching the solution guides…" />;
  }
  if (state === "empty" || content === null) {
    return <FullPageMessage icon={<Braces />} title="No solutions published" detail="This problem has no solution guide yet." />;
  }

  // Variants are the named approaches (bfs, dfs, …); a canonical-only
  // problem shows its single solution untitled.
  const variants = Object.keys(content.implementations).sort();
  const entries = variants.length > 0
    ? variants.map((variant) => ({
        name: variant,
        title: variant.toUpperCase(),
        body: content.guide[variant] ?? "",
        code: content.implementations[variant],
      }))
    : Object.keys(content.canonical).length > 0
      ? [{
          name: "",
          title: "",
          body: Object.values(content.guide)[0] ?? "",
          code: content.canonical,
        }]
      : [];
  if (entries.length === 0) {
    return <FullPageMessage icon={<Braces />} title="No solutions published" detail="This problem has no solution guide yet." />;
  }

  return (
    <article className="problem-scroll solutions">
      {entries.map((entry) => (
        <SolutionBlock
          key={entry.name || "canonical"}
          title={entry.title}
          body={entry.body}
          code={entry.code}
          languages={languages}
          slug={slug}
          theme={theme}
          selected={langByVariant[entry.name || "canonical"]}
          onSelect={(language) => setLangByVariant((current) => ({ ...current, [entry.name || "canonical"]: language }))}
        />
      ))}
    </article>
  );
}

function SolutionBlock({ title, body, code, languages, slug, theme, selected, onSelect }: {
  title: string;
  body: string;
  code: Record<string, string>;
  languages: Problem["languages"];
  slug: string;
  theme: Theme;
  selected: string | undefined;
  onSelect: (language: string) => void;
}) {
  const languageKeys = Object.keys(code);
  const shown = selected && languageKeys.includes(selected) ? selected : languageKeys[0];
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(code[shown]).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    }).catch(() => undefined);
  };

  return (
    <section className="solution-block">
      {title && <h3 className="solution-block-title">{title}</h3>}
      <div className="solution-block-bar">
        <LanguageMenu
          value={shown}
          options={languageKeys.map((key) => ({
            key,
            label: languages[key]?.display_name ?? key,
            enabled: true,
          }))}
          onChange={onSelect}
        />
        <button className="solution-copy" onClick={copy} title="Copy solution code" aria-label="Copy solution code">
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <div className="solution-code-scroll">
        <Editor
          height={360}
          language={languages[shown]?.monaco_language ?? "plaintext"}
          value={code[shown]}
          theme={theme === "dark" ? "openoj-dark" : "openoj-light"}
          loading={<div className="editor-loading"><LoaderCircle className="spin" size={18} /> Loading syntax engine…</div>}
          options={{
            readOnly: true,
            domReadOnly: true,
            automaticLayout: true,
            minimap: { enabled: false },
            fontFamily: "Roboto Mono, ui-monospace, monospace",
            fontSize: 12.5,
            lineHeight: 19,
            scrollBeyondLastLine: false,
            renderLineHighlight: "none",
            overviewRulerLanes: 0,
            scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
            padding: { top: 10, bottom: 10 },
          }}
        />
      </div>
      {body && (
        <div className="markdown-body solutions-guide">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              img: ({ src, alt }) => (
                <img
                  className="statement-figure"
                  src={typeof src === "string" && src.startsWith("figures/") ? `/api/problems/${slug}/${src}` : src}
                  alt={alt ?? ""}
                  loading="lazy"
                />
              ),
            }}
          >{body}</ReactMarkdown>
        </div>
      )}
    </section>
  );
}

function Submissions({ submissions, problem }: { submissions: Submission[]; problem: Problem }) {
  if (!submissions.length) return <ConsoleEmpty icon={<History />} title="No submissions yet" detail="Submit a solution and its verdict will be saved here." />;
  return (
    <div className="submission-list">
      <div className="submission-header"><span>Verdict</span><span>Language</span><span>Runtime</span><span>Submitted</span></div>
      {submissions.map((submission) => (
        <div className="submission-row" key={submission.id}>
          <span className="submission-status">
            <span className={`result-dot ${statusTone(submission.status)}`} />
            <span className={`status-text ${statusTone(submission.status)}`}>{statusLabel(submission.status)}</span>
          </span>
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

  const normalized = searchText(query.trim());
  const filtered = normalized
    ? problems.filter((entry) => matchesFilter(entry, normalized))
    : problems;

  return (
    <div className="drawer-backdrop" onMouseDown={onClose}>
      <aside className="drawer" onMouseDown={(event) => event.stopPropagation()}>
        <div className="drawer-heading">
          <div><strong>Practice library</strong></div>
          <button className="icon-button" onClick={onClose} aria-label="Close problem list"><X size={18} /></button>
        </div>
        <div className="drawer-tools">
          <input
            ref={filterRef}
            className="drawer-filter"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter by title or tag"
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
                {entry.tags.length > 0 && <small>{entry.tags.join(" · ")}</small>}
              </span>
              <span className={`difficulty ${difficultyTone(entry.difficulty)}`}>{difficultyLabel(entry.difficulty)}</span>
            </button>
          )) : <p className="drawer-empty">No problems match “{query.trim()}”.</p>}
        </div>
      </aside>
    </div>
  );
}

function ConsoleEmpty({ icon, title, detail, tone = "" }: { icon: React.ReactNode; title: string; detail?: string; tone?: string }) {
  return <div className={`console-empty ${tone}`}><span>{icon}</span><strong>{title}</strong>{detail ? <p>{detail}</p> : null}</div>;
}

function FullPageMessage({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) {
  return <main className="full-page-message"><span>{icon}</span><h1>{title}</h1><p>{detail}</p></main>;
}

// The only entrance until accounts exist: every visitor works as a guest
// session that idles out after about an hour.
function GuestGate({ expired, error, onEnter, theme, onToggleTheme }: {
  expired: boolean;
  error: string;
  onEnter: () => void;
  theme: Theme;
  onToggleTheme: () => void;
}) {
  return (
    <main className="guest-gate">
      <button
        className="icon-button theme-toggle gate-theme"
        onClick={onToggleTheme}
        title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
        aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      >
        {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
      </button>
      <div className="guest-card">
        <span className="brand-mark gate-mark"><Code2 size={22} strokeWidth={2.4} /></span>
        <h1>OpenOJ</h1>
        {expired && <p className="gate-notice">Your session idled out — drafts and submissions from it are gone.</p>}
        {error && <p className="gate-notice">{error}</p>}
        <p className="gate-copy">
          Sessions are guest-only and ephemeral: pick problems, write solutions, get verdicts.
          Editor drafts persist for the session and clear after about an hour of inactivity.
        </p>
        <button className="gate-enter" onClick={onEnter}>Continue as guest</button>
      </div>
    </main>
  );
}

export default App;
