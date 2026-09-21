"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

import Board from "@/components/Board";
import CriticalMomentCard from "@/components/CriticalMomentCard";
import EvalBar from "@/components/EvalBar";
import EvidencePanel from "@/components/EvidencePanel";
import ExplanationPanel from "@/components/ExplanationPanel";
import LineWalker, { type LineKind } from "@/components/LineWalker";
import MoveList from "@/components/MoveList";
import ProblemMoveList from "@/components/ProblemMoveList";
import { ApiError, api } from "@/lib/api";
import { formatLoss, formatPercent, severityLabel, SEVERITY_BADGE } from "@/lib/labels";
import type {
  CriticalMoment,
  GameReview,
  GameSummaryRecord,
  MomentExplanation,
  MomentLines,
} from "@/lib/types";

interface ExplanationState {
  data: MomentExplanation | null;
  loading: boolean;
  error: string | null;
}

const PLAYED_ARROW_COLOR = "#f2645a";

export default function GameReviewPage() {
  const params = useParams<{ id: string }>();
  const gameId = params?.id ?? "";

  const [review, setReview] = useState<GameReview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  /** 棋盘显示的局面：已经走了多少步（0 = 开局）。 */
  const [positionIndex, setPositionIndex] = useState(0);
  /** 正在讨论的关键局面（哪一手走错了）。 */
  const [selectedPly, setSelectedPly] = useState<number | null>(null);
  const [showBestMove, setShowBestMove] = useState(true);
  const [summary, setSummary] = useState<GameSummaryRecord | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [explanations, setExplanations] = useState<Record<number, ExplanationState>>({});
  /** 线路演示：kind = 引擎推荐/实战，index = 已经走了线路里的多少步。 */
  const [lineMode, setLineMode] = useState<{ kind: LineKind; index: number } | null>(null);
  const [linesByPly, setLinesByPly] = useState<Record<number, MomentLines>>({});
  const [linesLoading, setLinesLoading] = useState(false);
  const [autoPlaying, setAutoPlaying] = useState(false);
  const requestedPlys = useRef<Set<number>>(new Set());
  const requestedLines = useRef<Set<number>>(new Set());
  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    if (!gameId) return;
    let cancelled = false;
    api
      .review(gameId)
      .then(({ review: loaded }) => {
        if (cancelled) return;
        setReview(loaded);
        const first = loaded.critical_moments[0];
        if (first) {
          setSelectedPly(first.ply);
          // 关键局面展示的是「你当时面对的局面」，也就是这一手走出之前的位置。
          setPositionIndex(Math.max(0, first.ply - 1));
        } else {
          setPositionIndex(loaded.moves.length);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof ApiError ? error.hintZh ?? error.message : "加载失败");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [gameId]);

  const loadExplanation = useCallback(
    async (ply: number) => {
      if (requestedPlys.current.has(ply)) return;
      requestedPlys.current.add(ply);
      setExplanations((previous) => ({
        ...previous,
        [ply]: { data: previous[ply]?.data ?? null, loading: true, error: null },
      }));
      try {
        const { explanation } = await api.explanation(gameId, ply);
        setExplanations((previous) => ({
          ...previous,
          [ply]: { data: explanation, loading: false, error: null },
        }));
      } catch (error: unknown) {
        requestedPlys.current.delete(ply);
        setExplanations((previous) => ({
          ...previous,
          [ply]: {
            data: null,
            loading: false,
            error:
              error instanceof ApiError
                ? error.hintZh ?? error.message
                : "AI 解释生成失败（引擎复盘不受影响）",
          },
        }));
      }
    },
    [gameId],
  );

  useEffect(() => {
    if (selectedPly !== null) void loadExplanation(selectedPly);
  }, [selectedPly, loadExplanation]);

  const startWalkthrough = useCallback(
    async (ply: number, kind: LineKind = "best") => {
      setLineMode({ kind, index: 0 });
      if (requestedLines.current.has(ply)) return;
      requestedLines.current.add(ply);
      setLinesLoading(true);
      try {
        const loaded = await api.lines(gameId, ply);
        setLinesByPly((previous) => ({ ...previous, [ply]: loaded }));
      } catch {
        requestedLines.current.delete(ply);
      } finally {
        setLinesLoading(false);
      }
    },
    [gameId],
  );

  const exitWalkthrough = useCallback(() => {
    setLineMode(null);
    setAutoPlaying(false);
  }, []);

  /** 所有"移动棋盘"的操作都走这里，顺便退出线路演示（线路只属于某个特定局面）。 */
  const goToPosition = useCallback(
    (next: number) => {
      exitWalkthrough();
      setPositionIndex(Math.max(0, next));
    },
    [exitWalkthrough],
  );

  const moments = useMemo(() => review?.critical_moments ?? [], [review]);
  const moves = useMemo(() => review?.moves ?? [], [review]);
  const maxPly = moves.length;
  const clampedPosition = Math.max(0, Math.min(positionIndex, maxPly));

  const selectedMoment = moments.find((moment) => moment.ply === selectedPly) ?? null;
  const selectedIndex = selectedMoment
    ? moments.findIndex((moment) => moment.ply === selectedMoment.ply)
    : -1;

  /**
   * 棋盘停在任何一个局面时，棋谱里"从这一步走出去的那一手"就是当前局面的决策手。
   * 所以实战走法和引擎推荐对**每一手**都能显示——引擎推荐只在走子前的局面里合法，
   * 这也是不能把它画到走子之后的局面上的原因。
   */
  const upcomingMove = clampedPosition < maxPly ? moves[clampedPosition] : undefined;
  /** 棋盘是否正好停在某个关键局面的决策点上（关键局面详情用这个判断）。 */
  const atDecisionPoint =
    selectedMoment !== null && clampedPosition === Math.max(0, selectedMoment.ply - 1);

  const fen = useMemo(() => {
    if (!review) return "";
    if (clampedPosition === 0) return moves[0]?.fen_before ?? "";
    return moves[clampedPosition - 1]?.fen_after ?? "";
  }, [review, moves, clampedPosition]);

  const lastPlayedMove = clampedPosition > 0 ? moves[clampedPosition - 1] : undefined;
  const highlightedPly = atDecisionPoint && selectedMoment ? selectedMoment.ply : clampedPosition;

  // ---------------------------------------------------------------- 线路演示
  /** 当前局面这一手（upcomingMove）的线路数据。 */
  const currentPlyLines = upcomingMove ? linesByPly[upcomingMove.ply] ?? null : null;
  const momentLines = selectedMoment ? linesByPly[selectedMoment.ply] ?? null : null;
  const activeLine = momentLines
    ? lineMode?.kind === "played"
      ? momentLines.played
      : momentLines.best
    : null;
  const lineIndex = lineMode?.index ?? 0;
  const currentLineStep = activeLine && lineIndex > 0 ? activeLine.steps[lineIndex - 1] : null;
  const nextLineStep =
    activeLine && lineIndex < activeLine.steps.length ? activeLine.steps[lineIndex] : null;

  const arrowOf = (uci: string) => ({ from: uci.slice(0, 2), to: uci.slice(2, 4) });

  const boardFen = lineMode
    ? currentLineStep?.fen_after ?? selectedMoment?.fen ?? fen
    : fen;
  const boardLastMove = lineMode
    ? currentLineStep
      ? arrowOf(currentLineStep.uci)
      : null
    : lastPlayedMove
      ? arrowOf(lastPlayedMove.uci)
      : null;
  const boardBestArrow = lineMode
    ? nextLineStep
      ? arrowOf(nextLineStep.uci)
      : null
    : showBestMove && upcomingMove?.best_move_uci
      ? arrowOf(upcomingMove.best_move_uci)
      : null;
  // 实战走法与引擎推荐相同时只画一个箭头，避免两条线叠在一起
  const boardPlayedArrow =
    !lineMode && upcomingMove && upcomingMove.best_move_uci !== upcomingMove.uci
      ? { ...arrowOf(upcomingMove.uci), color: PLAYED_ARROW_COLOR }
      : null;

  // 自动播放：每次只推进一格，播完自动停下。
  useEffect(() => {
    if (!autoPlaying || !lineMode || !activeLine) return;
    if (lineMode.index >= activeLine.steps.length) return;
    const timer = setTimeout(() => {
      const next = lineMode.index + 1;
      if (next >= activeLine.steps.length) setAutoPlaying(false);
      setLineMode({ kind: lineMode.kind, index: next });
    }, 900);
    return () => clearTimeout(timer);
  }, [autoPlaying, lineMode, activeLine]);

  const goToMoment = useCallback(
    (index: number) => {
      const target = moments[index];
      if (!target) return;
      exitWalkthrough();
      setSelectedPly(target.ply);
      setPositionIndex(Math.max(0, target.ply - 1));
    },
    [moments, exitWalkthrough],
  );

  const goToNextMoment = useCallback(() => {
    if (moments.length === 0) return;
    goToMoment(selectedIndex < 0 ? 0 : Math.min(moments.length - 1, selectedIndex + 1));
  }, [goToMoment, moments.length, selectedIndex]);

  const goToPreviousMoment = useCallback(() => {
    if (moments.length === 0) return;
    goToMoment(selectedIndex <= 0 ? 0 : selectedIndex - 1);
  }, [goToMoment, moments.length, selectedIndex]);

  // 用「上一个/下一个关键局面」跳转时，把对应卡片滚进视野。
  useEffect(() => {
    if (selectedPly === null) return;
    // 滚动只是锦上添花：某些环境（老浏览器、无头环境）没有这个方法，不能因此让页面崩掉
    cardRefs.current[selectedPly]?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [selectedPly]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape" && lineMode) {
        exitWalkthrough();
        return;
      }
      if (event.key === "ArrowLeft") {
        if (event.shiftKey) {
          goToPreviousMoment();
        } else if (lineMode && activeLine) {
          // 演示线路时，左右键走的是线路，而不是实战棋局。
          setLineMode({ kind: lineMode.kind, index: Math.max(0, lineMode.index - 1) });
        } else {
          goToPosition(clampedPosition - 1);
        }
      }
      if (event.key === "ArrowRight") {
        if (event.shiftKey) {
          goToNextMoment();
        } else if (lineMode && activeLine) {
          setLineMode({
            kind: lineMode.kind,
            index: Math.min(activeLine.steps.length, lineMode.index + 1),
          });
        } else {
          goToPosition(clampedPosition + 1);
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [clampedPosition, goToNextMoment, goToPreviousMoment, lineMode, activeLine, exitWalkthrough, goToPosition]);

  const loadSummary = async () => {
    setSummaryLoading(true);
    try {
      const { summary: loaded } = await api.summary(gameId);
      setSummary(loaded);
    } catch {
      setSummary(null);
    } finally {
      setSummaryLoading(false);
    }
  };

  if (loadError) {
    return (
      <div className="panel p-6">
        <h2 className="text-lg font-semibold">无法加载这盘棋</h2>
        <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
          {loadError}
        </p>
        <Link href="/" className="mt-4 inline-block text-sm text-sky-400 hover:underline">
          返回导入页面
        </Link>
      </div>
    );
  }

  if (!review) {
    return (
      <div className="panel p-6 text-sm" style={{ color: "var(--muted)" }}>
        正在加载复盘结果…
      </div>
    );
  }

  const counts = review.counts;

  // 决策点上用关键局面自己的引擎数据；其它位置用所在局面的数据。
  const evalView =
    atDecisionPoint && selectedMoment
      ? {
          evaluation: selectedMoment.evidence.engine.evaluation_before,
          mate: selectedMoment.evidence.engine.mate_before,
          expected: selectedMoment.evidence.engine.expected_score_before,
        }
      : {
          evaluation: lastPlayedMove?.evaluation_after ?? null,
          mate: lastPlayedMove?.mate_after ?? null,
          expected: evalToExpected(lastPlayedMove?.evaluation_after ?? null),
        };

  return (
    <div className="space-y-5">
      <section className="panel p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold">
              {review.white} <span style={{ color: "var(--muted)" }}>vs</span> {review.black}
            </h1>
            <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
              结果 {review.result} · 你执{review.player_color === "white" ? "白" : "黑"}方
              {review.opening ? ` · ${review.opening}` : ""} · 引擎 {review.engine.engine_name} ·
              用时 {review.engine.elapsed_seconds.toFixed(1)}s
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="tag">最佳/优秀 {counts.best + counts.excellent}</span>
            <span className={`rounded px-2 py-1 ring-1 ${SEVERITY_BADGE.inaccuracy}`}>
              不够精确 {counts.inaccuracy}
            </span>
            <span className={`rounded px-2 py-1 ring-1 ${SEVERITY_BADGE.mistake}`}>
              失误 {counts.mistake}
            </span>
            <span className={`rounded px-2 py-1 ring-1 ${SEVERITY_BADGE.blunder}`}>
              严重失误 {counts.blunder}
            </span>
            <span className="tag">
              平均期望得分损失 {formatLoss(review.average_expected_score_loss)}
            </span>
          </div>
        </div>

        {review.warnings.length > 0 ? (
          <ul className="mt-3 space-y-1 text-xs text-amber-300">
            {review.warnings.map((warning) => (
              <li key={warning}>· {warning}</li>
            ))}
          </ul>
        ) : null}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={loadSummary}
            disabled={summaryLoading}
            className="rounded border px-3 py-1.5 text-sm"
            style={{ borderColor: "var(--border)" }}
          >
            {summaryLoading ? "生成中…" : summary ? "重新生成整体总结" : "生成整盘总结"}
          </button>
          <Link
            href="/profile"
            className="rounded border px-3 py-1.5 text-sm"
            style={{ borderColor: "var(--border)" }}
          >
            查看个人档案
          </Link>
        </div>

        {summary ? (
          <div className="coach-block mt-3 rounded-r-md p-3">
            <div className="mb-1 flex items-center gap-2">
              <span className="tag tag-coach">
                {summary.source === "llm" ? "AI 整体总结" : "规则模板总结（未使用 AI）"}
              </span>
              <span className="text-xs" style={{ color: "var(--muted)" }}>
                置信度 {formatPercent(summary.explanation.confidence)}
              </span>
            </div>
            <p className="text-sm leading-relaxed">{summary.explanation.summary}</p>
            {summary.explanation.main_patterns.length > 0 ? (
              <ul className="mt-2 space-y-1 text-sm">
                {summary.explanation.main_patterns.map((pattern) => (
                  <li key={pattern}>· 反复出现：{pattern}</li>
                ))}
              </ul>
            ) : null}
            {summary.explanation.practice_advice.length > 0 ? (
              <ul className="mt-2 space-y-1 text-sm" style={{ color: "var(--muted)" }}>
                {summary.explanation.practice_advice.map((advice) => (
                  <li key={advice}>· 建议：{advice}</li>
                ))}
              </ul>
            ) : null}
            <p className="mt-2 text-[11px]" style={{ color: "var(--muted)" }}>
              该总结只使用了上面已经确认过的失误清单，不会重新评估任何局面。
            </p>
          </div>
        ) : null}
      </section>

      <div className="grid gap-5 lg:grid-cols-[minmax(320px,440px)_1fr]">
        <section className="space-y-3 lg:sticky lg:top-4 lg:self-start">
          <Board
            fen={boardFen}
            orientation={review.player_color}
            lastMove={boardLastMove}
            bestMoveArrow={boardBestArrow}
            playedArrow={boardPlayedArrow}
          />

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <button
                type="button"
                className="rounded border px-2.5 py-1.5 text-sm"
                style={{ borderColor: "var(--border)" }}
                onClick={() => goToPosition(0)}
                disabled={clampedPosition === 0}
                title="回到开局"
              >
                ⏮
              </button>
              <button
                type="button"
                className="rounded border px-2.5 py-1.5 text-sm"
                style={{ borderColor: "var(--border)" }}
                onClick={() => goToPosition(clampedPosition - 1)}
                disabled={clampedPosition === 0}
                title="上一步（←）"
              >
                ◀ 上一步
              </button>
              <span className="mono text-xs" style={{ color: "var(--muted)" }}>
                {clampedPosition}/{maxPly}
              </span>
              <button
                type="button"
                className="rounded border px-2.5 py-1.5 text-sm"
                style={{ borderColor: "var(--border)" }}
                onClick={() => goToPosition(clampedPosition + 1)}
                disabled={clampedPosition >= maxPly}
                title="下一步（→）"
              >
                下一步 ▶
              </button>
              <button
                type="button"
                className="rounded border px-2.5 py-1.5 text-sm"
                style={{ borderColor: "var(--border)" }}
                onClick={() => goToPosition(maxPly)}
                disabled={clampedPosition >= maxPly}
                title="跳到终局"
              >
                ⏭
              </button>
            </div>

            {moments.length > 0 ? (
              <div className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  className="flex-1 rounded border px-2.5 py-1.5 text-sm"
                  style={{ borderColor: "var(--border)" }}
                  onClick={goToPreviousMoment}
                  disabled={selectedIndex <= 0}
                  title="上一个关键局面（Shift + ←）"
                >
                  ⇤ 上一个关键局面
                </button>
                <button
                  type="button"
                  className="flex-1 rounded border px-2.5 py-1.5 text-sm"
                  style={{ borderColor: "var(--border)" }}
                  onClick={goToNextMoment}
                  disabled={selectedIndex >= moments.length - 1}
                  title="下一个关键局面（Shift + →）"
                >
                  下一个关键局面 ⇥
                </button>
              </div>
            ) : null}

            {moments.length > 0 && selectedIndex >= 0 ? (
              <p className="text-center text-xs" style={{ color: "var(--muted)" }}>
                关键局面 {selectedIndex + 1} / {moments.length}
                {atDecisionPoint
                  ? " · 棋盘显示的是你当时面对的局面"
                  : " · 棋盘已移开，点卡片可跳回"}
              </p>
            ) : null}
          </div>

          <EvalBar
            evaluation={evalView.evaluation}
            mate={evalView.mate}
            expectedScore={evalView.expected}
            orientation={review.player_color}
            label={atDecisionPoint ? "走子前评估（你的一方）" : "局面评估（你的一方）"}
          />

          {lineMode && activeLine ? (
            <div className="panel-soft p-3 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span>
                  {currentLineStep
                    ? `第 ${
                        (selectedMoment?.move_number ?? 1) +
                        Math.floor(Math.max(0, lineMode.index - 1) / 2)
                      } 手 · ${currentLineStep.mover === "white" ? "白方" : "黑方"}走 ${
                        currentLineStep.san
                      }`
                    : "起点：你当时面对的局面"}
                </span>
                <span className="tag tag-engine">引擎线路</span>
              </div>
              {nextLineStep ? (
                <div className="mt-1" style={{ color: "var(--muted)" }}>
                  线路下一步：<span className="mono text-sky-300">{nextLineStep.san}</span>
                </div>
              ) : null}
            </div>
          ) : upcomingMove ? (
            <div className="panel-soft p-3 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span>
                  第 {upcomingMove.move_number} 手 ·{" "}
                  {upcomingMove.is_player_move ? "你在这里走" : "对手在这里走"}
                </span>
                {upcomingMove.severity ? (
                  <span
                    className={`rounded px-1.5 py-0.5 ring-1 ${SEVERITY_BADGE[upcomingMove.severity]}`}
                  >
                    {severityLabel(upcomingMove.severity)}
                  </span>
                ) : null}
              </div>

              <div className="mt-1.5 space-y-1">
                <div>
                  实战：<span className="mono">{upcomingMove.san}</span>
                  {upcomingMove.is_engine_best ? (
                    <span className="text-emerald-300"> · 就是引擎首选</span>
                  ) : null}
                </div>
                {!upcomingMove.is_engine_best ? (
                  <div>
                    引擎推荐：
                    <span className="mono text-sky-300">
                      {" "}
                      {upcomingMove.best_move_san ?? "—"}
                    </span>
                    {upcomingMove.best_move_uci && showBestMove ? (
                      <span style={{ color: "var(--muted)" }}>（棋盘上蓝色箭头）</span>
                    ) : null}
                  </div>
                ) : null}
                {upcomingMove.expected_score_loss !== null &&
                upcomingMove.expected_score_loss > 0 ? (
                  <div style={{ color: "var(--muted)" }}>
                    期望得分损失{" "}
                    <span className="mono">{formatLoss(upcomingMove.expected_score_loss)}</span>
                  </div>
                ) : null}
              </div>

              {upcomingMove.is_critical ? (
                <button
                  type="button"
                  onClick={() => {
                    const index = moments.findIndex(
                      (moment) => moment.ply === upcomingMove.ply,
                    );
                    if (index >= 0) goToMoment(index);
                  }}
                  className="mt-2 rounded border px-2 py-1 text-sky-300"
                  style={{ borderColor: "var(--border)" }}
                >
                  看这个局面的完整解释 ↓
                </button>
              ) : upcomingMove.severity && upcomingMove.severity !== "best" &&
                upcomingMove.severity !== "excellent" && upcomingMove.severity !== "good" ? (
                <p className="mt-2" style={{ color: "var(--muted)" }}>
                  这一手不在关键局面清单里：只给引擎推荐，不生成 AI 解释。
                </p>
              ) : null}
            </div>
          ) : lastPlayedMove?.severity ? (
            <div className="panel-soft p-3 text-xs">
              <div className="flex items-center justify-between">
                <span>
                  第 {lastPlayedMove.move_number} 手{" "}
                  <span className="mono">{lastPlayedMove.san}</span>
                </span>
                <span
                  className={`rounded px-1.5 py-0.5 ring-1 ${SEVERITY_BADGE[lastPlayedMove.severity]}`}
                >
                  {severityLabel(lastPlayedMove.severity)}
                </span>
              </div>
              <div className="mt-1" style={{ color: "var(--muted)" }}>
                {lastPlayedMove.is_player_move ? "你的着法" : "对手着法"} · 期望得分损失{" "}
                <span className="mono">{formatLoss(lastPlayedMove.expected_score_loss)}</span>
              </div>
            </div>
          ) : null}

          <label
            className="flex items-center gap-2 px-1 text-xs"
            style={{ color: "var(--muted)" }}
          >
            <input
              type="checkbox"
              checked={showBestMove}
              onChange={(event) => setShowBestMove(event.target.checked)}
            />
            在棋盘上显示引擎推荐走法（每一手都可以看）
          </label>

          {/* 后续线路演示：放在棋盘旁边，任何局面都能用，随时可以回到实战 */}
          {upcomingMove || lineMode ? (
            <LineWalker
              lines={currentPlyLines}
              loading={linesLoading}
              active={lineMode !== null}
              kind={lineMode?.kind ?? "best"}
              index={lineMode?.index ?? 0}
              playing={autoPlaying}
              onStart={() => {
                if (upcomingMove) void startWalkthrough(upcomingMove.ply);
              }}
              onExit={exitWalkthrough}
              onKindChange={(kind) => setLineMode({ kind, index: 0 })}
              onIndexChange={(index) =>
                setLineMode((current) =>
                  current ? { ...current, index } : { kind: "best", index },
                )
              }
              onTogglePlaying={() => setAutoPlaying((value) => !value)}
            />
          ) : null}

        </section>

        <section className="space-y-4">
          <MoveList
            moves={moves}
            currentPly={highlightedPly}
            onSelect={goToPosition}
          />

          <div className="panel p-3">
            <h2 className="text-sm font-semibold">
              {moments.length > 0
                ? `这盘棋真正值得复盘的 ${moments.length} 个局面`
                : "这盘棋没有出现值得单独复盘的失误"}
            </h2>
            {moments.length === 0 ? (
              <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
                引擎全程没有发现明显的期望得分损失。可以查看着法列表里的评估变化。
              </p>
            ) : (
              <div className="mt-3 space-y-2">
                {moments.map((moment, index) => (
                  <div
                    key={moment.ply}
                    ref={(node) => {
                      cardRefs.current[moment.ply] = node;
                    }}
                  >
                    <CriticalMomentCard
                      moment={moment}
                      index={index}
                      selected={moment.ply === selectedPly}
                      onSelect={() => goToMoment(index)}
                    />

                    {/* 解释放在对应关键局面的正下方，不需要滚到页面底部 */}
                    {moment.ply === selectedPly ? (
                      <MomentDetail
                        moment={moment}
                        engineName={review.engine.engine_name}
                        atDecisionPoint={atDecisionPoint}
                        onJumpBack={() => goToPosition(Math.max(0, moment.ply - 1))}
                        explanation={explanations[moment.ply]}
                        llmConfigured={review.llm_available}
                        onRetry={() => {
                          requestedPlys.current.delete(moment.ply);
                          void loadExplanation(moment.ply);
                        }}
                      />
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </div>

          <ProblemMoveList
            moves={moves}
            selectedPly={selectedPly}
            onSelect={(ply) => {
              goToPosition(ply);
              if (moments.some((moment) => moment.ply === ply)) setSelectedPly(ply);
            }}
          />
        </section>
      </div>
    </div>
  );
}

interface MomentDetailProps {
  moment: CriticalMoment;
  engineName: string;
  atDecisionPoint: boolean;
  onJumpBack: () => void;
  explanation: ExplanationState | undefined;
  llmConfigured: boolean;
  onRetry: () => void;
}

/** 关键局面的展开内容：控制条 + 引擎证据 + 教练解释。 */
function MomentDetail({
  moment,
  engineName,
  atDecisionPoint,
  onJumpBack,
  explanation,
  llmConfigured,
  onRetry,
}: MomentDetailProps) {
  return (
    <div className="mt-2 space-y-3 border-l-2 pl-3" style={{ borderColor: "var(--border)" }}>
      {atDecisionPoint ? null : (
        <div className="text-xs">
          <button
            type="button"
            onClick={onJumpBack}
            className="rounded border px-2 py-1"
            style={{ borderColor: "var(--border)" }}
          >
            把棋盘移回这个局面
          </button>
        </div>
      )}

      <p className="text-sm leading-relaxed">{moment.one_liner_zh}</p>

      <EvidencePanel
        engine={moment.evidence.engine}
        engineName={engineName}
        playedSan={moment.played_move_san}
      />

      <ExplanationPanel
        explanation={explanation?.data ?? null}
        loading={explanation?.loading ?? false}
        error={explanation?.error ?? null}
        llmConfigured={llmConfigured}
        onRetry={onRetry}
      />
    </div>
  );
}

/** Fallback expected score from a pawn evaluation (only used while stepping manually). */
function evalToExpected(evaluation: number | null): number {
  if (evaluation === null) return 0.5;
  const clamped = Math.max(-10, Math.min(10, evaluation));
  return 1 / (1 + Math.pow(10, -(clamped * 100) / 400));
}
