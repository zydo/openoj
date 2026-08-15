import type { JudgeResult, Problem, ProblemPage, Submission } from "./types";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail || `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  getProblem: (slug: string) => request<Problem>(`/problems/${slug}`),
  // pageSize of 0 (default) returns the full list in one page — the editor
  // needs the whole ordering for prev/next and the drawer. The landing page
  // passes an explicit page_size to fetch just the page it renders.
  getProblems: (page = 1, pageSize = 0) =>
    request<ProblemPage>(`/problems?page=${page}&page_size=${pageSize}`),
  run: (slug: string, language: string, code: string, cases: Record<string, unknown>[]) =>
    request<JudgeResult>("/run", {
      method: "POST",
      body: JSON.stringify({ slug, language, code, cases }),
    }),
  submit: (slug: string, language: string, code: string) =>
    request<JudgeResult>("/submit", {
      method: "POST",
      body: JSON.stringify({ slug, language, code }),
    }),
  getSubmissions: (slug: string) => request<Submission[]>(`/submissions?slug=${encodeURIComponent(slug)}`),
};

