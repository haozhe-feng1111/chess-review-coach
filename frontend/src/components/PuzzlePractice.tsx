"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

import PuzzleBoard, { type PuzzleBoardArrow } from "@/components/PuzzleBoard";
import { ApiError, api } from "@/lib/api";
import {
  PHASE_LABELS,
  colorLabel,
  formatPercent,
  puzzleDifficultyLabel,
  puzzleGoalLabel,
  puzzleKindLabel,
  PUZZLE_VERDICT_CLASSES,
  PUZZLE_VERDICT_LABELS,
  severityLabel,
} from "@/lib/labels";
import type { Puzzle, PuzzleAttemptResult, PuzzleDetail } from "@/lib/types";

const PLAYED_ARROW_COLOR = "#f2645a";
const SOLUTION_ARROW_COLOR = "#4f9cf9";
const AUTOPLAY_MS = 900;

interface PuzzlePracticeProps {
  puzzle: Puzzle;
  position: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
  /** 判定完通知外层刷新统计数字（题库统计不该等用户手动刷新）。 */
  onGraded: () => void;
}

/**
 * 一道题的练习区。
 *
 * 外层用 ``key={puzzle.id}`` 挂载它，所以"换题要清空上一次的作答状态"这件事是
 * 靠重新挂载自然发生的，不需要在 effect 里手动重置一堆 state。
 *
 * 这里不做任何棋规判断：合法着法、答案线路、对错判定全部来自服务端。
 */
export default function PuzzlePractice({
  puzzle,
  position,
  total,
  onPrev,
  onNext,
  onGraded,
}: PuzzlePracticeProps) {
  const [detail, setDetail] = useState<PuzzleDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [result, setResult] = useState<PuzzleAttemptResult | null>(null);
  const [grading, setGrading] = useState(false);
  const [showSolution, setShowSolution] = useState(false);
  /** 答案线路播放到第几步（0 = 还没开始播，展示题目局面）。 */
  const [playIndex, setPlayIndex] = useState(0);
  const [autoPlaying, setAutoPlaying] = useState(false);
  const [playedUci, setPlayedUci] = useState<string | null>(null);
  const requested = useRef(false);

  useEffect(() => {
    if (requested.current) return;
    requested.current = true;
    let cancelled = false;
    api
      .puzzle(puzzle.id)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((error) => {
        if (!cancelled) {
          setDetailError(error instanceof Error ? error.message : "加载题目详情失败");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [puzzle.id]);

  const steps = detail?.steps ?? [];
  const currentStep = playIndex > 0 ? steps[playIndex - 1] : undefined;
  const boardFen = currentStep ? currentStep.fen_after : puzzle.fen;
  const lastMove = currentStep
    ? { from: currentStep.uci.slice(0, 2), to: currentStep.uci.slice(2, 4) }
    : null;

  // 答案线路自动播放：定时器里推进，effect 本身不放 setState（避免级联渲染）
  useEffect(() => {
    if (!autoPlaying || playIndex >= steps.length) return;
    const timer = setTimeout(() => {
      setPlayIndex((value) => value + 1);
      if (playIndex + 1 >= steps.length) setAutoPlaying(false);
    }, AUTOPLAY_MS);
    return () => clearTimeout(timer);
  }, [autoPlaying, playIndex, steps.length]);

  const arrows: PuzzleBoardArrow[] = useMemo(() => {
    const list: PuzzleBoardArrow[] = [];
    if (showSolution || result?.correct) {
      list.push({
        from: puzzle.solution_uci.slice(0, 2),
        to: puzzle.solution_uci.slice(2, 4),
        color: SOLUTION_ARROW_COLOR,
      });
    } else if (playedUci && playIndex === 0 && result) {
      list.push({
        from: playedUci.slice(0, 2),
        to: playedUci.slice(2, 4),
        color: PLAYED_ARROW_COLOR,
      });
    }
    return list;
  }, [playIndex, playedUci, puzzle.solution_uci, result, showSolution]);

  const submit = useCallback(
    async (uci: string) => {
      if (result || grading) return;
      setPlayedUci(uci);
      setGrading(true);
      try {
        const graded = await api.attemptPuzzle(puzzle.id, uci);
        setResult(graded);
        if (graded.correct) {
          setPlayIndex(1);
          setAutoPlaying(true);
        }
        onGraded();
      } catch (error) {
        const message =
          error instanceof ApiError && error.hintZh ? error.hintZh : "提交失败，请重试";
        setDetailError(message);
        setPlayedUci(null);
      } finally {
        setGrading(false);
      }
    },
    [grading, onGraded, puzzle.id, result],
  );

  const revealSolution = useCallback(() => {
    setShowSolution(true);
    setPlayIndex(0);
    setAutoPlaying(true);
  }, []);

  const reset = useCallback(() => {
    setResult(null);
    setPlayedUci(null);
    setShowSolution(false);
    setPlayIndex(0);
    setAutoPlaying(false);
    setDetailError(null);
  }, []);

  const answered = result !== null;

  return (
    <section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
      <div className="space-y-3" style={{ maxWidth: "min(100%, calc(100vh - 240px))" }}>
        {detailError && (
          <p className="rounded border border-amber-900 bg-amber-950/50 px-3 py-2 text-sm text-amber-200">
            {detailError}
          </p>
        )}
        {detail ? (
          <PuzzleBoard
            fen={boardFen}
            orientation={puzzle.player_color}
            legalMoves={playIndex === 0 && !answered ? detail.legal_moves : []}
            interactive={playIndex === 0 && !answered && !grading}
            onMove={(uci) => void submit(uci)}
            lastMove={lastMove}
            arrows={arrows}
            turn={puzzle.player_color}
          />
        ) : (
          <div
            className="flex h-80 items-center justify-center rounded border text-sm"
            style={{ borderColor: "var(--border)", color: "var(--muted)" }}
          >
            正在加载题目…
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 text-sm">
          <button
            type="button"
            className="rounded border px-2 py-1"
            style={{ borderColor: "var(--border)" }}
            onClick={onPrev}
          >
            ◀ 上一题
          </button>
          <span className="tabular-nums" style={{ color: "var(--muted)" }}>
            {position + 1}/{total}
          </span>
          <button
            type="button"
            className="rounded border px-2 py-1"
            style={{ borderColor: "var(--border)" }}
            onClick={onNext}
          >
            下一题 ▶
          </button>
          <span style={{ color: "var(--muted)" }}>│</span>
          <button
            type="button"
            className="rounded border px-2 py-1"
            style={{ borderColor: "var(--border)" }}
            onClick={revealSolution}
            disabled={!steps.length}
          >
            看答案并播放线路
          </button>
          <button
            type="button"
            className="rounded border px-2 py-1"
            style={{ borderColor: "var(--border)" }}
            onClick={reset}
            disabled={grading}
          >
            重做本题
          </button>
        </div>

        {steps.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span style={{ color: "var(--muted)" }}>答案线路：</span>
            {steps.map((step, position_) => (
              <button
                key={`${step.uci}-${position_}`}
                type="button"
                className="rounded px-2 py-0.5 tabular-nums"
                style={{
                  background: position_ < playIndex ? "rgba(79,156,249,0.25)" : "transparent",
                  border: "1px solid var(--border)",
                }}
                onClick={() => {
                  setAutoPlaying(false);
                  setShowSolution(true);
                  setPlayIndex(position_ >= playIndex ? position_ + 1 : position_);
                }}
              >
                {step.san}
              </button>
            ))}
            {autoPlaying && <span style={{ color: "var(--muted)" }}>播放中…</span>}
          </div>
        )}
      </div>

      <div className="space-y-3">
        <div className="rounded border px-4 py-3" style={{ borderColor: "var(--border)" }}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold">{puzzleKindLabel(puzzle.kind)}</span>
            <span
              className="rounded px-2 py-0.5 text-xs ring-1"
              style={{ background: "rgba(79,156,249,0.15)" }}
            >
              {puzzleGoalLabel(puzzle)}
            </span>
            <span className="text-xs" style={{ color: "var(--muted)" }}>
              {puzzleDifficultyLabel(puzzle.difficulty)} · {puzzle.theme_label_zh} ·{" "}
              {PHASE_LABELS[puzzle.phase]}
            </span>
          </div>
          <dl className="mt-3 space-y-1 text-sm" style={{ color: "var(--muted)" }}>
            <div>
              来自你自己的对局：第 {puzzle.move_number} 回合，{colorLabel(puzzle.player_color)}
            </div>
            <div>
              你当时走了 <strong className="text-rose-300">{puzzle.played_san}</strong>
              （{severityLabel(puzzle.severity)}）
            </div>
            {puzzle.material_gain ? (
              <div>
                引擎线路在 {puzzle.solution_line_san.length} 步内净赚 {puzzle.material_gain} 分
                （并且扛过了对手的应手）
              </div>
            ) : null}
          </dl>
          <Link
            href={`/games/${puzzle.game_id}`}
            className="mt-2 inline-block text-xs underline"
            style={{ color: "var(--muted)" }}
          >
            回到这盘棋的完整复盘 →
          </Link>
        </div>

        {grading && (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            引擎正在给这一步打分…
          </p>
        )}

        {result && (
          <div
            className={`rounded px-4 py-3 text-sm ring-1 ${PUZZLE_VERDICT_CLASSES[result.verdict]}`}
          >
            <div className="flex items-center gap-2">
              <span className="font-semibold">{PUZZLE_VERDICT_LABELS[result.verdict]}</span>
              <span className="text-xs opacity-80">
                {result.graded_by === "engine" ? "引擎判定" : "只比对了答案"}
              </span>
            </div>
            <p className="mt-1">{result.verdict_zh}</p>
            {result.played_san && (
              <p className="mt-1 text-xs opacity-90">
                你走了 {result.played_san}
                {result.best_san ? `，引擎答案是 ${result.best_san}` : ""}
              </p>
            )}
            {result.expected_score_loss !== null && (
              <p className="mt-1 text-xs opacity-90">
                期望得分：这一步 {formatScore(result.played_expected_score)}，引擎着法{" "}
                {formatScore(result.best_expected_score)}（差 {result.expected_score_loss.toFixed(3)}）
              </p>
            )}
          </div>
        )}

        <div
          className="rounded border px-4 py-3 text-xs leading-relaxed"
          style={{ borderColor: "var(--border)", color: "var(--muted)" }}
        >
          <p className="font-semibold text-slate-300">怎么判定对错</p>
          <p className="mt-1">
            先看是不是引擎的推荐着法；不是的话，再让引擎单独给「你走的这一步」打分，
            按期望得分的落差来判。所以和答案不同、但一样好的着法不会被判错。
          </p>
          <p className="mt-1">
            题目少是设计使然：只有「本来该赢、却漏掉了强制手段」的局面才会被收进来。
          </p>
        </div>
      </div>
    </section>
  );
}

function formatScore(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return formatPercent(value);
}
