import type { JudgeResult, Problem, Submission } from "./types";

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
  getProblems: () => request<Array<Pick<Problem, "id" | "slug" | "title" | "difficulty" | "tags">>>("/problems"),
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

