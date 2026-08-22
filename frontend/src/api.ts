import type { JudgeResult, Problem, ProblemPage, SolutionsContent, Submission } from "./types";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

// Set by App: any 401 (idle-expired guest session) routes the app back to the
// Continue-as-guest entrance.
let unauthorizedHandler: (() => void) | null = null;

export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.();
    const payload = await response.json().catch(() => null);
    throw new ApiError(payload?.detail || `Request failed with status ${response.status}`, response.status);
  }
  return response.json() as Promise<T>;
}

export type SessionStatus = {
  status: string;
  idle_seconds: number;
  user: { username: string; is_admin: boolean } | null;
};
export type DraftRow = { language: string; code: string; updated_at: number };

export const api = {
  sessionStatus: (): Promise<SessionStatus> => request<SessionStatus>("/session"),
  // Idle-expiry probe: validates without extending the session's clock, so
  // the inactivity watcher can poll without keeping the session alive.
  probeSession: (): Promise<SessionStatus> => request<SessionStatus>("/session?touch=0"),
  startSession: (): Promise<SessionStatus> =>
    request<SessionStatus>("/session", { method: "POST" }),
  authStatus: (): Promise<{ needs_setup: boolean }> =>
    request<{ needs_setup: boolean }>("/auth/status"),
  register: (username: string, password: string): Promise<SessionStatus> =>
    request<SessionStatus>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  login: (username: string, password: string): Promise<SessionStatus & { username: string; is_admin: boolean }> =>
    request<SessionStatus & { username: string; is_admin: boolean }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: (): Promise<{ status: string }> =>
    request<{ status: string }>("/auth/logout", { method: "POST" }),
  getProblem: (slug: string) => request<Problem>(`/problems/${slug}`),
  // pageSize of 0 (default) returns the full list in one page — the editor
  // needs the whole ordering for prev/next and the drawer. The landing page
  // passes an explicit page_size to fetch just the page it renders.
  getProblems: (page = 1, pageSize = 0) =>
    request<ProblemPage>(`/problems?page=${page}&page_size=${pageSize}`),
  getSolutions: (slug: string): Promise<SolutionsContent> =>
    request<SolutionsContent>(`/problems/${encodeURIComponent(slug)}/solutions`),
  getDrafts: (slug: string): Promise<DraftRow[]> =>
    request<DraftRow[]>(`/drafts/${encodeURIComponent(slug)}`),
  putDraft: (slug: string, language: string, code: string) =>
    request<{ status: string }>(`/drafts/${encodeURIComponent(slug)}/${encodeURIComponent(language)}`, {
      method: "PUT",
      body: JSON.stringify({ code }),
      // Survive the tab being torn down right after a flush.
      keepalive: true,
    }),
  run: (slug: string, language: string, code: string, cases: Record<string, unknown>[]) =>
    request<JudgeResult>("/run", {
      method: "POST",
      body: JSON.stringify({ slug, language, code, cases }),
    }),
  // Formatting depends on the language alone, so no slug is sent.
  format: (language: string, code: string) =>
    request<{ code: string }>("/format", {
      method: "POST",
      body: JSON.stringify({ language, code }),
    }),
  submit: (slug: string, language: string, code: string) =>
    request<JudgeResult>("/submit", {
      method: "POST",
      body: JSON.stringify({ slug, language, code }),
    }),
  getSubmissions: (slug: string) => request<Submission[]>(`/submissions?slug=${encodeURIComponent(slug)}`),
  // Per-problem status marks for the current viewer (user or guest):
  // "solved" (any language accepted) or "attempted"; absent slugs are never-tried.
  getProgress: (): Promise<Record<string, "attempted" | "solved">> => request("/progress"),
};
