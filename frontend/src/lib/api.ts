/**
 * Thin typed client for the local FastAPI backend.
 *
 * All analysis happens server-side; this module only moves JSON. It never sees an API
 * key and never computes a chess evaluation.
 */

import type {
  AnalysisJobStatus,
  Color,
  GameListItem,
  GameReview,
  GameSummaryRecord,
  HealthResponse,
  LLMTestResult,
  MomentExplanation,
  MomentLines,
  ProfileSummary,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly hintZh?: string;

  constructor(message: string, status: number, hintZh?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.hintZh = hintZh;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      `无法连接后端服务（${API_BASE}）`,
      0,
      "请确认后端已启动：cd backend && ../.venv/bin/python -m uvicorn api.main:app --port 8000",
    );
  }

  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = await response.json();
    } catch {
      detail = null;
    }
    const payload = detail as { detail?: unknown } | null;
    const inner = payload?.detail as
      | { error?: string; hint_zh?: string }
      | string
      | undefined;
    if (inner && typeof inner === "object") {
      throw new ApiError(inner.error ?? response.statusText, response.status, inner.hint_zh);
    }
    if (typeof inner === "string") {
      throw new ApiError(inner, response.status);
    }
    throw new ApiError(response.statusText || "请求失败", response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),

  /** 把某个局面的后续线路展开成可逐步演示的局面序列（任何一手都能查）。 */
  lines: (gameId: string, ply: number) =>
    request<MomentLines>(`/api/games/${gameId}/moves/${ply}/lines`),

  /** 真实调用一次 DeepSeek，验证 API Key 是否可用。 */
  testLlm: () => request<LLMTestResult>("/api/llm/test", { method: "POST" }),

  analyze: (body: {
    pgn: string;
    player_color?: Color | null;
    max_critical_moments?: number;
    deep?: boolean;
    force?: boolean;
  }) =>
    request<{ job_id: string; game_id: string; status: AnalysisJobStatus }>(
      "/api/games/analyze",
      { method: "POST", body: JSON.stringify(body) },
    ),

  job: (jobId: string) => request<{ job: AnalysisJobStatus }>(`/api/jobs/${jobId}`),

  review: (gameId: string) => request<{ review: GameReview }>(`/api/games/${gameId}`),

  explanation: (gameId: string, ply: number) =>
    request<{ ply: number; explanation: MomentExplanation }>(
      `/api/games/${gameId}/moments/${ply}/explanation`,
    ),

  summary: (gameId: string) =>
    request<{ game_id: string; summary: GameSummaryRecord }>(`/api/games/${gameId}/summary`),

  games: (limit = 50) => request<{ games: GameListItem[] }>(`/api/games?limit=${limit}`),

  deleteGame: (gameId: string) =>
    request<{ game_id: string; deleted: boolean }>(`/api/games/${gameId}`, {
      method: "DELETE",
    }),

  profile: () => request<ProfileSummary>("/api/profile"),
};

/** Poll a queued analysis job until it settles. */
export async function waitForJob(
  jobId: string,
  onProgress: (job: AnalysisJobStatus) => void,
  options: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<AnalysisJobStatus> {
  const interval = options.intervalMs ?? 1200;
  const deadline = Date.now() + (options.timeoutMs ?? 15 * 60 * 1000);

  for (;;) {
    const { job } = await api.job(jobId);
    onProgress(job);
    if (job.status === "completed" || job.status === "failed") {
      return job;
    }
    if (Date.now() > deadline) {
      throw new ApiError("分析超时", 408, "分析用时过长，请尝试降低深度后重试。");
    }
    await new Promise((resolve) => setTimeout(resolve, interval));
  }
}
