"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import PuzzlePractice from "@/components/PuzzlePractice";
import { api } from "@/lib/api";
import { formatPercent } from "@/lib/labels";
import type { Puzzle, PuzzleKind, PuzzleStats } from "@/lib/types";

type KindFilter = PuzzleKind | "all";

/**
 * 题目训练页。
 *
 * 只做一件事：把**你自己对局里漏掉的强制手段**摆出来重做一遍。
 * 题目、答案、合法着法、对错判定全部来自服务端（引擎 + python-chess + 确定性规则），
 * 前端只负责显示，以及收集"他走了哪一步"。
 */
export default function PuzzlePage() {
  const [puzzles, setPuzzles] = useState<Puzzle[]>([]);
  const [stats, setStats] = useState<PuzzleStats | null>(null);
  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  const [themeFilter, setThemeFilter] = useState<string>("all");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [index, setIndex] = useState(0);

  const refreshStats = useCallback(() => {
    api
      .puzzleStats()
      .then(setStats)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const list = await api.puzzles({
          limit: 200,
          kind: kindFilter,
          theme: themeFilter === "all" ? null : themeFilter,
        });
        if (cancelled) return;
        setPuzzles(list);
        setLoadError(null);
        setIndex(0);
      } catch (error) {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : "加载题目失败");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [kindFilter, themeFilter]);

  useEffect(() => {
    refreshStats();
  }, [refreshStats]);

  const current: Puzzle | null = puzzles[clamp(index, puzzles.length)] ?? null;
  const themes = stats?.by_theme ?? [];

  const goTo = useCallback(
    (next: number) => {
      if (!puzzles.length) return;
      setIndex((next + puzzles.length) % puzzles.length);
    },
    [puzzles.length],
  );

  return (
    <div className="space-y-5">
      <section className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">题目训练</h1>
          <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
            题目只来自你自己的对局里漏掉的强制手段：能强制将杀，或者能在几步内净赚子力。
            答案和判定都由本机引擎给出。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <select
            aria-label="题型"
            className="rounded border bg-transparent px-2 py-1"
            style={{ borderColor: "var(--border)" }}
            value={kindFilter}
            onChange={(event) => setKindFilter(event.target.value as KindFilter)}
          >
            <option value="all">全部题型</option>
            <option value="mate">强制将杀</option>
            <option value="material">赚取子力</option>
          </select>
          <select
            aria-label="主题"
            className="rounded border bg-transparent px-2 py-1"
            style={{ borderColor: "var(--border)" }}
            value={themeFilter}
            onChange={(event) => setThemeFilter(event.target.value)}
          >
            <option value="all">全部主题</option>
            {themes.map((item) => (
              <option key={item.theme ?? "none"} value={item.theme ?? ""}>
                {item.label_zh}（{item.count}）
              </option>
            ))}
          </select>
        </div>
      </section>

      {stats && (
        <section
          className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded border px-4 py-3 text-sm"
          style={{ borderColor: "var(--border)" }}
        >
          <span>
            题库 <strong>{stats.total}</strong> 道（将杀 {stats.mate} · 赚子 {stats.material}）
          </span>
          <span>
            做过 <strong>{stats.attempted}</strong> 道，做对 <strong>{stats.solved}</strong> 道
            {stats.attempted > 0 && `（${formatPercent(stats.solved_rate)}）`}
          </span>
          <span style={{ color: "var(--muted)" }}>
            题目少是正常的：只有「该赢的局里漏掉强制手段」才会出题。
          </span>
        </section>
      )}

      {loadError && (
        <p className="rounded border border-rose-900 bg-rose-950/60 px-3 py-2 text-sm text-rose-200">
          {loadError}
        </p>
      )}

      {!loading && !puzzles.length && (
        <section
          className="rounded border px-4 py-6 text-sm"
          style={{ borderColor: "var(--border)", color: "var(--muted)" }}
        >
          还没有题目。题目是从已分析的对局里提取的，所以先去
          <Link href="/" className="mx-1 underline">
            导入并分析一盘棋
          </Link>
          ；如果已经分析过对局，可以运行
          <code className="mx-1 rounded bg-slate-800 px-1">
            python backend/scripts/backfill_puzzles.py
          </code>
          给旧对局补题。
        </section>
      )}

      {current && (
        <PuzzlePractice
          key={current.id}
          puzzle={current}
          position={clamp(index, puzzles.length)}
          total={puzzles.length}
          onPrev={() => goTo(clamp(index, puzzles.length) - 1)}
          onNext={() => goTo(clamp(index, puzzles.length) + 1)}
          onGraded={refreshStats}
        />
      )}
    </div>
  );
}

function clamp(index: number, length: number): number {
  if (length <= 0) return 0;
  return Math.min(Math.max(index, 0), length - 1);
}
