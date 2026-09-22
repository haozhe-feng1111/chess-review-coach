"use client";

import { useCallback, useState } from "react";
import { Chessboard, type Arrow } from "react-chessboard";

import type { Color } from "@/lib/types";

export interface PuzzleBoardArrow {
  from: string;
  to: string;
  color?: string;
}

interface PuzzleBoardProps {
  fen: string;
  orientation: Color;
  /**
   * 题目局面下的合法着法（UCI），**由服务端算好**。
   *
   * 前端不引 chess.js、也不自己判棋规：这里只做"用户点/拖的这一下在不在白名单里"。
   * 棋规只有 python-chess 一个来源，这条是项目的硬约束。
   */
  legalMoves: string[];
  /** 落子回调：只在合法着法里触发。 */
  onMove: (uci: string) => void;
  /** 关掉之后再怎么点都不会动子（已经答完、或正在播放答案）。 */
  interactive?: boolean;
  lastMove?: { from: string; to: string } | null;
  arrows?: PuzzleBoardArrow[];
  /** 客户端只用来"看起来对"，真正的合法性仍然由 legalMoves 决定。 */
  turn: Color;
}

const SELECTED_COLOR = "rgba(79, 156, 249, 0.55)";
const TARGET_COLOR = "rgba(79, 156, 249, 0.28)";
const LAST_MOVE_COLOR = "rgba(242, 100, 90, 0.45)";

function promotionSuffixes(legalMoves: string[], from: string, to: string): string[] {
  return legalMoves.filter(
    (uci) =>
      uci.length === 5 &&
      uci.startsWith(`${from}${to}`) &&
      ["q", "r", "b", "n"].includes(uci[4]),
  );
}

/**
 * 做题用的棋盘：可以点也可以拖，但每一步都必须落在服务端给的合法着法里。
 *
 * 交互方式（先点起点、再点终点，和拖拽并存）是刻意做成"不需要自己算棋"的：
 * 用户点一个子，我们只高亮那些**服务端说合法**的目标格。
 *
 * 局面变化时由外层用 ``key`` 重新挂载，所以这里不需要在 effect 里重置选中状态。
 */
export default function PuzzleBoard({
  fen,
  orientation,
  legalMoves,
  onMove,
  interactive = true,
  lastMove = null,
  arrows = [],
  turn,
}: PuzzleBoardProps) {
  const [selected, setSelected] = useState<string | null>(null);
  const [promotion, setPromotion] = useState<{ from: string; to: string } | null>(null);
  /** 轮到自己走的那一方的棋子前缀：react-chessboard 用 "wP"/"bP" 标记颜色。 */
  const mine = turn === "white" ? "w" : "b";

  const tryMove = useCallback(
    (from: string, to: string) => {
      if (!interactive) return false;
      const candidates = promotionSuffixes(legalMoves, from, to);
      if (candidates.length > 1) {
        setPromotion({ from, to });
        setSelected(null);
        return true;
      }
      const uci = `${from}${to}`;
      const legal = legalMoves.find(
        (candidate) => candidate === uci || (candidates[0] && candidate === candidates[0]),
      );
      if (!legal) return false;
      setSelected(null);
      onMove(legal);
      return true;
    },
    [interactive, legalMoves, onMove],
  );

  const squareStyles: Record<string, React.CSSProperties> = {};
  if (lastMove) {
    squareStyles[lastMove.from] = { backgroundColor: LAST_MOVE_COLOR };
    squareStyles[lastMove.to] = { backgroundColor: "rgba(242, 100, 90, 0.55)" };
  }

  if (interactive && selected) {
    squareStyles[selected] = {
      ...(squareStyles[selected] ?? {}),
      backgroundColor: SELECTED_COLOR,
    };
    for (const uci of legalMoves) {
      if (uci.startsWith(selected)) {
        const to = uci.slice(2, 4);
        squareStyles[to] = {
          ...(squareStyles[to] ?? {}),
          backgroundColor: TARGET_COLOR,
          boxShadow: "inset 0 0 0 3px rgba(79, 156, 249, 0.65)",
        };
      }
    }
  }

  const boardArrows: Arrow[] = arrows.map((arrow) => ({
    startSquare: arrow.from,
    endSquare: arrow.to,
    color: arrow.color ?? "#4f9cf9",
  }));

  const promotionOptions = promotion
    ? promotionSuffixes(legalMoves, promotion.from, promotion.to)
    : [];

  return (
    <div className="w-full">
      <Chessboard
        options={{
          id: "puzzle-board",
          position: fen,
          boardOrientation: orientation,
          allowDragging: interactive,
          allowDrawingArrows: false,
          showAnimations: true,
          animationDurationInMs: 200,
          showNotation: true,
          arrows: boardArrows,
          squareStyles,
          darkSquareStyle: { backgroundColor: "#4a5a78" },
          lightSquareStyle: { backgroundColor: "#c8d2e3" },
          darkSquareNotationStyle: { color: "#c8d2e3" },
          lightSquareNotationStyle: { color: "#4a5a78" },
          boardStyle: {
            borderRadius: "0.5rem",
            overflow: "hidden",
            boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
          },
          // 只能动轮到自己走的那一方的子。这里看的是棋子的颜色标记（"wP"/"bP"），
          // 不是棋规判断——能不能走到某格仍然只看服务端给的合法着法。
          canDragPiece: ({ piece }) => interactive && piece.pieceType.startsWith(mine),
          onPieceDrop: ({ sourceSquare, targetSquare }) => {
            if (!targetSquare) return false;
            return tryMove(sourceSquare, targetSquare);
          },
          onSquareClick: ({ piece, square }) => {
            if (!interactive) return;
            const isMine = piece?.pieceType?.startsWith(mine) ?? false;
            if (!selected) {
              // 空点或对方的子不选中：选中了也高亮不出任何合法目标，只会让人困惑
              if (isMine) setSelected(square);
              return;
            }
            if (selected === square) {
              setSelected(null);
              return;
            }
            if (!tryMove(selected, square)) setSelected(isMine ? square : null);
          },
        }}
      />
      {promotionOptions.length > 1 && (
        <div className="mt-2 flex items-center gap-2 text-sm">
          <span style={{ color: "var(--muted)" }}>升变成：</span>
          {promotionOptions.map((uci) => (
            <button
              key={uci}
              type="button"
              className="rounded border px-2 py-1"
              style={{ borderColor: "var(--border)" }}
              onClick={() => {
                setPromotion(null);
                onMove(uci);
              }}
            >
              {uci[4] === "q" ? "后" : uci[4] === "r" ? "车" : uci[4] === "b" ? "象" : "马"}
            </button>
          ))}
        </div>
      )}
      <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
        轮到你走（{turn === "white" ? "白方" : "黑方"}）：点一下棋子，再点目标格，或者直接拖过去。
        只能走服务端标出的合法着法。
      </p>
    </div>
  );
}
