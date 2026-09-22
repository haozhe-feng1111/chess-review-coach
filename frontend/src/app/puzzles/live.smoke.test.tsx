/**
 * 对着**真实后端**跑的端到端冒烟测试（默认不跑，见文件末尾的开关）。
 *
 * 为什么需要它：题目页曾经在开发环境里永远停在「正在加载题目…」——
 * 原因是 next.config 里开着 reactStrictMode，组件用 ref 记住"已经请求过"、
 * 又同时在清理时把结果丢掉，于是第二次 effect 直接跳过、第一次的结果被扔了。
 * 打桩 fetch 的组件测试**抓不到**这个：桩是同步 resolve 的，StrictMode 的
 * 挂载→清理→再挂载根本走不到"丢结果"那一步。只有"真接口 + 严格模式"一起上才复现。
 *
 * 跑法（需要后端已经在 127.0.0.1:8000 上运行）：
 *     npm run test:live
 *
 * 它是**只读**的：只看题库、题目详情和棋盘渲染，不提交作答、不写数据库。
 */

import { StrictMode } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import PuzzlePage from "./page";
import { API_BASE } from "@/lib/api";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

describe("题目页 × 真实后端", () => {
  it.skipIf(process.env.LIVE_API !== "1")(
    "严格模式下也能加载出题目、棋盘和合法着法",
    { timeout: 40000 },
    async () => {
      render(
        <StrictMode>
          <PuzzlePage />
        </StrictMode>,
      );

      // 题库统计（真实接口）
      await waitFor(() => expect(screen.getByText(/题库/)).toBeTruthy(), { timeout: 15000 });

      // 真实棋盘：64 个格子 + 交互提示。这里曾经永远不出现（StrictMode 丢结果）
      await waitFor(
        () => expect(document.querySelectorAll("[data-square]").length).toBe(64),
        { timeout: 15000 },
      );
      expect(screen.getByText(/轮到你走/)).toBeTruthy();
      expect(screen.getByText(/怎么判定对错/)).toBeTruthy();

      // 合法着法确实来自服务端，而且包含答案本身
      const listing = await fetch(`${API_BASE}/api/puzzles?limit=1`).then((r) => r.json());
      if (listing.length > 0) {
        const puzzle = listing[0];
        const detail = await fetch(
          `${API_BASE}/api/puzzles/${encodeURIComponent(puzzle.id)}`,
        ).then((r) => r.json());
        expect(detail.legal_moves).toContain(puzzle.solution_uci);
        expect(detail.steps.length).toBeGreaterThan(0);
      }
    },
  );
});
