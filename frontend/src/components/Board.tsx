"use client";

import { useMemo, useState } from "react";
import { Chess, type Square } from "chess.js";
import { Chessboard, type Arrow } from "react-chessboard";
import type { Color } from "@/lib/types";

export interface BoardArrow { from: string; to: string; color?: string }
interface BoardProps {
  fen: string; orientation: Color; squareColors?: Record<string, string>;
  lastMove?: { from: string; to: string } | null;
  bestMoveArrow?: BoardArrow | null; playedArrow?: BoardArrow | null;
  onMove?: (uci: string) => void;
}

export default function Board({ fen, orientation, squareColors = {}, lastMove, bestMoveArrow, playedArrow, onMove }: BoardProps) {
  const chess = useMemo(() => new Chess(fen), [fen]);
  const [selection, setSelection] = useState<{ fen: string; square: string } | null>(null);
  const [promotion, setPromotion] = useState<{ fen: string; from: string; to: string } | null>(null);
  const selected = selection?.fen === fen ? selection.square : null;
  const promoting = promotion?.fen === fen ? promotion : null;
  const legal = selected ? chess.moves({ square: selected as Square, verbose: true }) : [];
  function attempt(from: string, to: string) {
    if (!onMove) return false;
    const moves = chess.moves({ square: from as Square, verbose: true }).filter(m => m.to === to);
    if (!moves.length) return false;
    setSelection(null);
    if (moves.some(m => m.promotion)) { setPromotion({ fen, from, to }); return false; }
    onMove(from + to);
    return true;
  }
  function click(square: string) {
    if (!onMove || promoting) return;
    if (selected && square !== selected && attempt(selected, square)) return;
    const piece = chess.get(square as Square);
    setSelection(piece?.color === chess.turn() && selected !== square ? { fen, square } : null);
  }
  const squareStyles: Record<string, React.CSSProperties> = {};
  for (const [sq, color] of Object.entries(squareColors)) squareStyles[sq] = { backgroundColor: color };
  if (lastMove) for (const sq of [lastMove.from, lastMove.to]) squareStyles[sq] = { backgroundColor: "rgba(217,164,65,.42)" };
  if (selected) squareStyles[selected] = { backgroundColor: "rgba(79,156,249,.65)" };
  for (const move of legal) squareStyles[move.to] = { backgroundImage: move.captured ?
    "radial-gradient(transparent 58%, rgba(11,18,32,.4) 60%)" : "radial-gradient(rgba(11,18,32,.35) 22%, transparent 24%)" };
  const arrows: Arrow[] = [];
  if (playedArrow) arrows.push({ startSquare: playedArrow.from, endSquare: playedArrow.to, color: playedArrow.color ?? "#f2645a" });
  if (bestMoveArrow && !selected && !promoting) arrows.push({ startSquare: bestMoveArrow.from, endSquare: bestMoveArrow.to, color: bestMoveArrow.color ?? "#4f9cf9" });
  return (
    <div className="relative w-full" aria-label="分析棋盘">
      <Chessboard options={{
        id: "review-board", position: fen, boardOrientation: orientation,
        allowDragging: Boolean(onMove) && !promoting, allowDragOffBoard: false, allowAutoScroll: false,
        canDragPiece: ({ square }) => Boolean(square && chess.get(square as Square)?.color === chess.turn()),
        onPieceDrag: ({ square }) => { if (square) setSelection({ fen, square }); },
        onPieceDrop: ({ sourceSquare, targetSquare }) => targetSquare ? attempt(sourceSquare, targetSquare) : false,
        onSquareClick: ({ square }) => click(square),
        squareRenderer: ({ square, children }) => <div role="button" tabIndex={onMove ? 0 : -1}
          aria-label={`${square}${chess.get(square as Square) ? ` ${chess.get(square as Square)?.type}` : " 空格"}`}
          className="board-square-key" style={{ width: "100%", height: "100%", ...squareStyles[square] }}
          onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); click(square); } }}>
          {children}</div>,
        allowDrawingArrows: true, showAnimations: false, animationDurationInMs: 0,
        showNotation: true, arrows, squareStyles,
        darkSquareStyle: { backgroundColor: "#4a5a78" }, lightSquareStyle: { backgroundColor: "#c8d2e3" },
        darkSquareNotationStyle: { color: "#c8d2e3" }, lightSquareNotationStyle: { color: "#4a5a78" },
        boardStyle: { borderRadius: "0.5rem", overflow: "hidden" },
      }} />
      {promoting && (
        <div className="promotion-picker" role="dialog" aria-label="选择升变棋子" aria-modal="false">
          <p className="mb-3 font-semibold">兵升变</p>
          <div className="flex flex-wrap justify-center gap-2">
            {([["q", "后"], ["r", "车"], ["b", "象"], ["n", "马"]] as const).map(([piece, label]) => (
              <button className="workbench-button" autoFocus={piece === "q"} key={piece} onClick={() => {
                onMove?.(promoting.from + promoting.to + piece); setPromotion(null);
              }}>{label}</button>
            ))}
            <button className="workbench-button" onClick={() => setPromotion(null)}>取消</button>
          </div>
        </div>
      )}
    </div>
  );
}
