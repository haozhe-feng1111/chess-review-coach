/**
 * 复盘页的渲染测试：验证「用户真的能在页面上看到并点到这些东西」。
 *
 * 为什么需要它：线路演示的入口按钮曾经因为组件里一个提前 `return null` 而**永远渲染不出来**。
 * 我当时用「后端接口正常」+「打包产物里有这段字符串」做了验证，两样都通过——
 * 但那只能证明字符串在包里，不能证明组件会渲染。这个测试补上这一环：
 * 用假的 fetch 喂一份复盘数据，渲染真实页面，然后断言按钮存在、点得动。
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import GameReviewPage from "./page";

// 路由参数
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "game-1" }),
}));

// 棋盘是个重组件（依赖 dnd-kit / ResizeObserver），和被测逻辑无关，替换成占位元素
vi.mock("@/components/Board", () => ({
  default: ({ fen }: { fen: string }) => <div data-testid="board">{fen}</div>,
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

const REVIEW = {
  game_id: "game-1",
  white: "me",
  black: "opponent",
  result: "0-1",
  player_color: "white",
  opening: "意大利开局",
  headers: {},
  moves: [
    {
      ply: 1,
      move_number: 1,
      color: "white",
      san: "e4",
      uci: "e2e4",
      fen_before: "start",
      fen_after: "after-e4",
      is_player_move: true,
      severity: "best",
      expected_score_loss: 0,
      evaluation_after: 0.3,
      mate_after: null,
      best_move_san: "e4",
      best_move_uci: "e2e4",
      is_engine_best: true,
      evaluation_before: 0.25,
      expected_score_before: 0.53,
      best_line_uci: ["e2e4", "e7e5"],
      best_line_san: ["e4", "e5"],
      played_line_uci: ["e2e4", "e7e5"],
      played_line_san: ["e4", "e5"],
      concept_tags: [],
      decision_error_tags: [],
      is_critical: false,
    },
    {
      ply: 2,
      move_number: 1,
      color: "black",
      san: "e5",
      uci: "e7e5",
      fen_before: "after-e4",
      fen_after: "after-e5",
      is_player_move: false,
      severity: "best",
      expected_score_loss: 0,
      evaluation_after: 0.28,
      mate_after: null,
      best_move_san: "e5",
      best_move_uci: "e7e5",
      is_engine_best: true,
      evaluation_before: 0.3,
      expected_score_before: 0.5,
      best_line_uci: ["e7e5"],
      best_line_san: ["e5"],
      played_line_uci: ["e7e5"],
      played_line_san: ["e5"],
      concept_tags: [],
      decision_error_tags: [],
      is_critical: false,
    },
    {
      ply: 3,
      move_number: 2,
      color: "white",
      san: "Bc4",
      uci: "f1c4",
      fen_before: "after-e5",
      fen_after: "after-bc4",
      is_player_move: true,
      severity: "blunder",
      expected_score_loss: 0.23,
      evaluation_after: -1.9,
      mate_after: null,
      best_move_san: "Nf3",
      best_move_uci: "g1f3",
      is_engine_best: false,
      evaluation_before: 0.28,
      expected_score_before: 0.5,
      best_line_uci: ["g1f3", "b8c6"],
      best_line_san: ["Nf3", "Nc6"],
      played_line_uci: ["f1c4", "g8f6"],
      played_line_san: ["Bc4", "Nf6"],
      concept_tags: [],
      decision_error_tags: [],
      is_critical: true,
    },
  ],
  critical_moments: [
    {
      ply: 3,
      move_number: 2,
      player_color: "white",
      phase: "opening",
      severity: "blunder",
      criticality_score: 0.5,
      reasons: ["high_loss"],
      one_liner_zh: "你忽略了对手的威胁。",
      fen: "after-e5",
      played_move_san: "Bc4",
      solution_uci: "g1f3",
      solution_san: "Nf3",
      evidence: {
        position: {
          fen: "after-e5",
          ply: 3,
          move_number: 2,
          player_color: "white",
          phase: "opening",
        },
        played_move: { uci: "f1c4", san: "Bc4" },
        engine: {
          pov_color: "white",
          evaluation_before: 0.28,
          evaluation_after: -1.9,
          mate_before: null,
          mate_after: null,
          wdl_before: { win: 0.5, draw: 0.4, loss: 0.1 },
          wdl_after: { win: 0.1, draw: 0.2, loss: 0.7 },
          expected_score_before: 0.5,
          expected_score_after: 0.2,
          expected_score_loss: 0.3,
          centipawn_loss: 100,
          best_move_uci: "g1f3",
          best_move_san: "Nf3",
          best_line_uci: ["g1f3"],
          best_line_san: ["Nf3"],
          played_line_uci: ["f1c4"],
          played_line_san: ["Bc4"],
          depth_before: 12,
          depth_after: 12,
          nodes_before: null,
          nodes_after: null,
          multipv_before: 1,
          multipv_after: 1,
          alternatives: [],
          is_engine_best: false,
          best_move_unique: false,
          wdl_estimated: false,
        },
        concepts: [],
        decision_errors: [],
        severity: "blunder",
        board_context: {},
        move_history_san: [],
      },
    },
  ],
  counts: { best: 1, excellent: 0, good: 0, inaccuracy: 0, mistake: 0, blunder: 1 },
  average_expected_score_loss: 0.1,
  phase_stats: [],
  engine: {
    engine_name: "Stockfish 19",
    pass1_depth: 12,
    pass1_nodes: 0,
    pass2_depth: 18,
    pass2_multipv: 3,
    threads: 4,
    hash_mb: 64,
    positions_analyzed: 3,
    cache_hits: 0,
    elapsed_seconds: 1.2,
    complete: true,
    warnings: [],
  },
  llm_available: false,
  status: "completed",
  warnings: [],
  created_at: null,
};

const LINES = {
  ply: 3,
  move_number: 2,
  played_move_san: "Bc4",
  best_move_san: "Nf3",
  evaluation_before: 0.28,
  expected_score_before: 0.5,
  best: {
    kind: "best",
    label_zh: "引擎推荐线路",
    start_fen: "after-e5",
    final_fen: "x",
    complete: true,
    truncated: false,
    ends_in_mate: false,
    steps: [
      { uci: "g1f3", san: "Nf3", fen_after: "f1", mover: "white" },
      { uci: "b8c6", san: "Nc6", fen_after: "f2", mover: "black" },
    ],
  },
  played: {
    kind: "played",
    label_zh: "实战线路（你实际走出来的）",
    start_fen: "after-e5",
    final_fen: "y",
    complete: true,
    truncated: false,
    ends_in_mate: false,
    steps: [{ uci: "f1c4", san: "Bc4", fen_after: "p1", mover: "white" }],
  },
};

function stubFetch() {
  const calls: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    calls.push(url);
    const body = url.includes("/lines") ? LINES : { review: REVIEW };
    return {
      ok: true,
      status: 200,
      json: async () => body,
    } as Response;
  }) as typeof fetch;
  return calls;
}

describe("复盘页", () => {
  beforeEach(() => {
    stubFetch();
  });

  it("打开页面就能看到「演示后续走法」入口（曾经渲染不出来）", async () => {
    render(<GameReviewPage />);

    // 等复盘数据加载完
    await waitFor(() => expect(screen.getByTestId("board")).toBeTruthy());
    const entry = await screen.findByRole("button", { name: /演示后续走法/ });
    expect(entry).toBeTruthy();
  });

  it("点入口会去取线路数据，并显示两条线路与步进控制", async () => {
    const calls = stubFetch();
    render(<GameReviewPage />);
    await waitFor(() => expect(screen.getByTestId("board")).toBeTruthy());

    (await screen.findByRole("button", { name: /演示后续走法/ })).click();

    await waitFor(() => expect(screen.getByText("线路演示中")).toBeTruthy());
    expect(calls.some((url) => url.includes("/moves/3/lines"))).toBe(true);
    expect(screen.getByRole("button", { name: "引擎推荐线路" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /返回实战对局/ })).toBeTruthy();
    // 线路里的每一步都点在棋盘上可走
    expect(screen.getByRole("button", { name: "Nf3" })).toBeTruthy();
  });

  it("线路控制必须和棋盘在同一块区域里（排版守卫）", async () => {
    render(<GameReviewPage />);
    await waitFor(() => expect(screen.getByTestId("board")).toBeTruthy());

    const board = screen.getByTestId("board");
    const section = board.closest("section");
    expect(section).toBeTruthy();

    // 入口按钮、评估条、着法跳转都必须和棋盘同属左栏，用户不用滚动才能点到
    const entry = await screen.findByRole("button", { name: /演示后续走法/ });
    expect(section?.contains(entry)).toBe(true);

    // 棋盘后面紧跟的节点顺序：棋盘 -> 跳转按钮 -> ...，距离不超过几层
    expect(section?.contains(screen.getByTitle("下一步（→）"))).toBe(true);
    expect(section?.contains(screen.getByTitle("下一个关键局面（Shift + →）"))).toBe(true);
    expect(
      screen.getAllByText("期望得分", { exact: false }).some((node) => section?.contains(node)),
    ).toBe(true);
  });

  it("页面底部会列出全部问题着法并给出引擎推荐", async () => {
    render(<GameReviewPage />);
    await waitFor(() => expect(screen.getByTestId("board")).toBeTruthy());

    expect(screen.getByText(/全部问题着法（1 个）/)).toBeTruthy();
    // 问题着法那一行里有它的引擎推荐
    expect(screen.getAllByText("Nf3").length).toBeGreaterThan(0);
  });
});
