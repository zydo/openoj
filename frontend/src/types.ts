export type Language = {
  display_name: string;
  monaco_language: string;
  starter: string;
  enabled: boolean;
};

export type Problem = {
  id: number;
  slug: string;
  title: string;
  difficulty: string;
  tags: string[];
  description: string;
  hints: string[];
  invocation: {
    type: "function" | "design";
    class_name: string;
    method: string;
    parameters: Array<{ name: string; codec: string }>;
    return_codec: string;
  };
  limits: {
    time_ms: number;
    memory_mb: number;
  };
  languages: Record<string, Language>;
  public_cases: Array<{ name: string; input: Record<string, unknown> }>;
};

export type CaseResult = {
  index: number;
  name: string;
  status: string;
  runtime_ms?: number;
  timeout_ms?: number | null;
  input?: Record<string, unknown>;
  expected?: unknown;
  actual?: unknown;
  stdout?: string;
  error?: string;
};

export type JudgeResult = {
  status: string;
  passed: number;
  total: number;
  runtime_ms: number;
  reference_runtime_ms?: number | null;
  results: CaseResult[];
  submission_id?: number;
};

export type Submission = {
  id: number;
  problem_slug: string;
  language: string;
  status: string;
  passed: number;
  total: number;
  runtime_ms: number;
  created_at: string;
};
