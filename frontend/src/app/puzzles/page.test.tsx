/**
 * 题目训练页的渲染与交互测试。
 *
 * 为什么要有这一层：这个页面同时依赖「服务端算好的合法着法」「引擎判定结果」和
 * 「答案线路播放」，任何一环接错了用户都会卡住——比如合法着法没传下去，用户就
 * 一步也走不了（这正是拖拽做题最容易静默失败的地方）。所以这里用假 fetch 喂真实
 * 结构的数据，渲染真页面，然后断言：棋盘能落子、合法的着法会被提交、判错会显示
 * 引擎给的理由、看答案能播放线路。
 */

import { StrictMode } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import PuzzlePage from "./page";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

// 真实棋盘依赖 dnd-kit / ResizeObserver，和被测逻辑无关：换成一个能"落子"的替身，
// 把组件传下来的合法着法原样暴露出来，测试就能验证白名单真的传下去了。
vi.mock("@/components/PuzzleBoard", () => ({
  default: ({
    fen,
    legalMoves,
    onMove,
    interactive,
  }: {
    fen: string;
    legalMoves: string[];
    onMove: (uci: string) => void;
    interactive: boolean;
  }) => (
    <div data-testid="board" data-fen={fen} data-interactive={String(interactive)}>
      <span data-testid="legal-moves">{legalMoves.join(",")}</span>
      <button type="button" onClick={() => onMove("d1d5")}>
        走 Rxd5
      </button>
      <button type="button" onClick={() => onMove("d1d2")}>
        走 Rd2
      </button>
    </div>
  ),
}));

const PUZZLE = {
  id: "game-1:1",
  game_id: "game-1",
  ply: 1,
  move_number: 1,
  player_color: "white",
  phase: "middlegame",
  kind: "material",
  fen: "4k3/8/8/3n4/8/8/8/3RK3 w - - 0 1",
  solution_uci: "d1d5",
  solution_san: "Rxd5",
  solution_line_uci: ["d1d5"],
  solution_line_san: ["Rxd5"],
  mate_in: null,
  material_gain: 3,
  theme: "hanging_piece",
  theme_label_zh: "悬子（无保护）",
  played_san: "h3",
  severity: "mistake",
  difficulty: "easy",
  concept_tags: ["hanging_piece"],
  created_at: "2024-01-01T00:00:00",
};

const DETAIL = {
  puzzle: PUZZLE,
  steps: [{ uci: "d1d5", san: "Rxd5", fen_after: "after-rxd5", mover: "white" }],
  opponent_replies: [],
  legal_moves: ["d1d5", "d1d2", "e1f1"],
};

const STATS = {
  total: 1,
  mate: 0,
  material: 1,
  attempted: 0,
  solved: 0,
  solved_rate: 0,
  by_theme: [{ theme: "hanging_piece", label_zh: "悬子（无保护）", count: 1 }],
};

function stubFetch(attempt: Record<string, unknown>) {
  const calls: { url: string; method: string; body: string | null }[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: (init?.body as string) ?? null });
    let body: unknown = STATS;
    if (url.includes("/attempt")) body = attempt;
    else if (url.includes("/puzzles/")) body = DETAIL;
    else if (url.includes("/puzzles?")) body = [PUZZLE];
    return { ok: true, status: 200, json: async () => body } as Response;
  }) as typeof fetch;
  return calls;
}

const CORRECT = {
  puzzle_id: PUZZLE.id,
  correct: true,
  played_uci: "d1d5",
  played_san: "Rxd5",
  best_san: "Rxd5",
  is_engine_move: true,
  graded_by: "engine",
  verdict: "correct",
  verdict_zh: "走对了：这就是引擎的答案",
  expected_score_loss: 0,
  played_expected_score: 0.97,
  best_expected_score: 0.97,
  attempts: 1,
  solved: 1,
};

const WRONG = {
  ...CORRECT,
  correct: false,
  played_uci: "d1d2",
  played_san: "Rd2",
  is_engine_move: false,
  verdict: "wrong",
  verdict_zh: "没走对：期望得分掉了 45%，这一步把刚才的机会放走了（引擎答案是 Rxd5）",
  expected_score_loss: 0.45,
  played_expected_score: 0.52,
  attempts: 2,
  solved: 1,
};

describe("题目训练页", () => {
  beforeEach(() => {
    stubFetch(CORRECT);
  });

  it("把服务端给的合法着法交给棋盘，并显示题目来源", async () => {
    render(<PuzzlePage />);

    const board = await screen.findByTestId("board");
    expect(board.dataset.fen).toBe(PUZZLE.fen);
    // 前端不自己算棋：合法着法必须原样来自接口
    await waitFor(() =>
      expect(screen.getByTestId("legal-moves").textContent).toBe("d1d5,d1d2,e1f1"),
    );
    expect(screen.getByTestId("legal-moves").textContent).not.toContain("a1a8");
    expect(screen.getByText(/第 1 回合/)).toBeTruthy();
    expect(screen.getByText("h3")).toBeTruthy();
    expect(screen.getByText(/净赚 3 分子力/)).toBeTruthy();
  });

  it("提交一步之后显示引擎判定，并把这一步上报给服务端", async () => {
    const calls = stubFetch(WRONG);
    render(<PuzzlePage />);
    await screen.findByTestId("board");

    fireEvent.click(screen.getByRole("button", { name: "走 Rd2" }));

    const verdict = await screen.findByText(/没走对：期望得分掉了 45%/);
    expect(verdict).toBeTruthy();
    expect(screen.getByText("引擎判定")).toBeTruthy();

    const attempt = calls.find((call) => call.url.includes("/attempt"));
    expect(attempt?.method).toBe("POST");
    // 只上报"他走了哪一步"，不自己判对错
    expect(attempt?.body).toBe(JSON.stringify({ played_uci: "d1d2" }));
  });

  it("答对之后自动播放引擎线路，并且棋盘不再接受落子", async () => {
    stubFetch(CORRECT);
    render(<PuzzlePage />);
    await screen.findByTestId("board");

    fireEvent.click(screen.getByRole("button", { name: "走 Rxd5" }));

    expect(await screen.findByText("走对了")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByTestId("board").dataset.fen).toBe("after-rxd5"),
    );
    expect(screen.getByTestId("board").dataset.interactive).toBe("false");
  });

  it("看答案会把答案线路展开成可点击的着法列表", async () => {
    render(<PuzzlePage />);
    await screen.findByTestId("board");

    fireEvent.click(screen.getByRole("button", { name: /看答案并播放线路/ }));

    const chip = await screen.findByRole("button", { name: "Rxd5" });
    expect(chip).toBeTruthy();
    fireEvent.click(chip);
    await waitFor(() =>
      expect(screen.getByTestId("board").dataset.fen).toBe("after-rxd5"),
    );
  });

  it("React 严格模式下（开发环境的双次 effect）也能加载出题目", async () => {
    // 这条是回归测试：next.config 里 reactStrictMode 是开着的，开发环境会
    // 挂载 → 清理 → 再挂载。如果组件用 ref 记住"已经请求过"、同时又在清理时
    // 把结果丢掉，就会出现"请求发出去了、但界面永远停在加载中"。
    render(
      <StrictMode>
        <PuzzlePage />
      </StrictMode>,
    );

    await waitFor(() => expect(screen.getByTestId("board")).toBeTruthy(), {
      timeout: 3000,
    });
  });

  it("题库为空时给出下一步该做什么，而不是一片空白", async () => {
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      const body = url.includes("/stats") ? { ...STATS, total: 0, by_theme: [] } : [];
      return { ok: true, status: 200, json: async () => body } as Response;
    }) as typeof fetch;

    render(<PuzzlePage />);

    expect(await screen.findByText(/还没有题目/)).toBeTruthy();
    expect(screen.getByText(/backfill_puzzles\.py/)).toBeTruthy();
  });
});
