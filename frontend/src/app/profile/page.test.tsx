/**
 * 档案页渲染测试：这一页的价值全在"敢说多少、不敢说多少"上，
 * 所以测的就是这两件事——
 *   1) 该显示的都显示了：置信区间、趋势、时间维度、"先改这一件"、方法说明；
 *   2) 没有数据时说的是"没有数据"，而不是编一句结论（时间压力那一块尤其重要）。
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import ProfilePage from "./page";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

const WEAKNESS = {
  error_type: "advantage_conversion",
  label_zh: "优势局面转换",
  event_count: 24,
  share: 0.245,
  games: 9,
  average_expected_score_loss: 0.52,
  severity_mix: { blunder: 18, mistake: 6 },
  confidence: "medium",
  statement_zh: "从数据看：优势局面转换，占重大失误的 24%（9 局游戏中共 24 次）。",
  share_low: 0.171,
  share_high: 0.336,
  by_phase: { middlegame: 20, endgame: 4 },
  under_time_pressure: 0,
  clocked_events: 0,
  first_seen: "2026-08-01T10:00:00",
  last_seen: "2026-09-20T10:00:00",
  trend: {
    available: true,
    direction: "flat",
    statement_zh: "前后两半没有明显差别（每 100 手 2.7 次 vs 1.8 次，p=0.34）。",
    early_rate: 2.7,
    late_rate: 1.8,
    early_events: 24,
    late_events: 16,
    p_value: 0.34,
    compared_types: 11,
    significance_level: 0.0045,
  },
  examples: [
    {
      game_id: "game-1",
      ply: 43,
      move_number: 22,
      san: "Rxe7",
      opponent: "opp",
      severity: "blunder",
      one_liner_zh: "这一步把赢棋送回去了。",
      fen: "8/8/8/8/8/8/8/K6k w - - 0 1",
      solution_san: "Bb7",
    },
  ],
};

const PROFILE = {
  total_games: 30,
  total_player_moves: 1039,
  total_problems: 120,
  blunders: 40,
  mistakes: 58,
  inaccuracies: 22,
  average_expected_score_loss: 0.13,
  weaknesses: [WEAKNESS],
  phases: [{ phase: "middlegame", label_zh: "中局", events: 90, share: 0.75, average_expected_score_loss: 0.4 }],
  top_concepts: [{ concept: "hanging_piece", label_zh: "悬子（无保护）", count: 12, share: 0.1 }],
  trend: { available: false, statement_zh: "目前只有 2 局数据，样本不足以判断趋势。", direction: "flat" },
  trend_points: [],
  time_controls: [
    {
      speed: "bullet",
      label_zh: "子弹",
      games: 4,
      problems: 21,
      problems_per_game: 5.25,
      average_expected_score_loss: 0.2,
    },
    {
      speed: "rapid",
      label_zh: "快棋",
      games: 25,
      problems: 98,
      problems_per_game: 3.92,
      average_expected_score_loss: 0.11,
    },
  ],
  clocked_problem_moves: 0,
  problems_under_pressure: 0,
  under_time_pressure_share: null,
  clock_note_zh:
    "你的对局 PGN 里没有逐步剩余时间，所以这份档案无法判断失误是否与时间紧张有关。Lichess 导出的 PGN 默认带时钟；Chess.com 导出时要勾选 Include clock times。",
  next_focus: {
    error_type: "advantage_conversion",
    label_zh: "优势局面转换",
    statement_zh: "先改这一件：优势局面转换（占重大失误的 24%（9 局中 24 次））。",
    confidence: "medium",
    drill_zh: "1. 先看引擎推荐走法。 2. 自己想一遍为什么它更好。",
  },
  sample_size_note_zh: "已分析 30 局、120 个失误，统计有一定的参考价值。",
  evidence_note_zh:
    "占比的分母是「严重失误 + 失误」（98 次），不是全部着法。 括号里的百分比区间是 95% Wilson 区间：样本越小，区间越宽，别把 30% 当成精确值。 趋势会同时检验 11 个错误类型，因此把显著性门槛按 Bonferroni 收紧到 0.05/11；没到门槛的一律写成「没有明显差别」。",
  generated_at: "2026-09-22T10:00:00",
};

function stubFetch(body: unknown) {
  globalThis.fetch = (async () => ({
    ok: true,
    status: 200,
    json: async () => body,
  })) as unknown as typeof fetch;
}

describe("档案页", () => {
  beforeEach(() => {
    stubFetch(PROFILE);
  });

  it("弱项卡片给出区间、趋势、阶段分布和时钟覆盖情况", async () => {
    render(<ProfilePage />);

    await waitFor(() => expect(screen.getByText("优势局面转换")).toBeTruthy());
    // 百分比必须带区间，否则小样本会显得很确定
    expect(screen.getByText(/95% 区间 17%–34%/)).toBeTruthy();
    expect(screen.getByText(/趋势：没有明显变化/)).toBeTruthy();
    expect(screen.getByText(/中局 20/)).toBeTruthy();
    // 没有时钟数据时如实说明，而不是写"时间不紧张"
    expect(screen.getByText(/没有逐步时钟，无法判断是否与时间有关/)).toBeTruthy();
  });

  it("例子能点回那盘棋的具体一手（带 ?ply=）", async () => {
    render(<ProfilePage />);

    const link = await screen.findByRole("link", { name: /22\. Rxe7/ });
    expect(link.getAttribute("href")).toBe("/games/game-1?ply=43");
  });

  it("顶部有「先改这一件」，并说明是按样本量和占比挑的", async () => {
    render(<ProfilePage />);

    expect(await screen.findByText("如果只能先改一件事")).toBeTruthy();
    expect(screen.getByText(/先改这一件：优势局面转换/)).toBeTruthy();
    expect(screen.getByText(/按「样本量够 \+ 占比最高」挑出来的/)).toBeTruthy();
    expect(screen.getByText(/怎么练：/)).toBeTruthy();
  });

  it("时间维度按时限分档，并明确写出这是相关不是因果", async () => {
    render(<ProfilePage />);

    expect(await screen.findByText(/你是一快就崩，还是与时间无关/)).toBeTruthy();
    expect(screen.getByText(/子弹 · 4 局/)).toBeTruthy();
    expect(screen.getByText(/每局 5\.25 个问题着法/)).toBeTruthy();
    expect(screen.getByText(/这是相关，不是因果/)).toBeTruthy();
    // 没有逐手时钟时只说没有数据，并告诉用户怎么才能有
    expect(screen.getByText(/勾选 Include clock times/)).toBeTruthy();
  });

  it("把统计口径写在折叠起来的方法说明里", async () => {
    render(<ProfilePage />);

    const summary = await screen.findByText(/这些数字是怎么算出来的/);
    expect(summary).toBeTruthy();
    expect(screen.getByText(/95% Wilson 区间/)).toBeTruthy();
    expect(screen.getByText(/Bonferroni/)).toBeTruthy();
  });

  it("完全没有数据时也是诚实的：不推荐、不编时间结论", async () => {
    stubFetch({
      ...PROFILE,
      total_games: 0,
      total_problems: 0,
      weaknesses: [],
      top_concepts: [],
      time_controls: [],
      next_focus: null,
      sample_size_note_zh: "还没有分析过对局。",
      clock_note_zh: "你的对局 PGN 里没有逐步剩余时间，所以这份档案无法判断失误是否与时间紧张有关。",
    });
    render(<ProfilePage />);

    expect(await screen.findByText("还没有足够的失误数据")).toBeTruthy();
    expect(screen.queryByText("如果只能先改一件事")).toBeNull();
    expect(screen.getByText(/无法判断失误是否与时间紧张有关/)).toBeTruthy();
  });
});
