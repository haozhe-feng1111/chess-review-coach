"use client";

import { clamp, formatEval, formatPercent } from "@/lib/labels";

interface EvalBarProps {
  /** Player-perspective evaluation in pawns (mate encoded as ±10 by the backend). */
  evaluation: number | null;
  mate: number | null;
  /** Expected score from the analyzed player's point of view. */
  expectedScore: number;
  orientation: "white" | "black";
  label?: string;
  /** 紧凑模式：一行放下，用于棋盘下方（默认的卡片式太高）。 */
  compact?: boolean;
}

/**
 * Two related numbers, deliberately kept apart:
 *
 * * the bar is the *expected score* (win + 0.5·draw), which is what severity is based
 *   on, and
 * * the number is the raw engine evaluation, shown for reference.
 */
export default function EvalBar({
  evaluation,
  mate,
  expectedScore,
  orientation,
  label,
  compact = false,
}: EvalBarProps) {
  const share = clamp(expectedScore, 0, 1);
  const whiteShare = orientation === "white" ? share : 1 - share;

  if (compact) {
    return (
      <div className="flex items-center gap-2 px-0.5 text-xs">
        <span style={{ color: "var(--muted)" }}>{label ?? "评估"}</span>
        <span className="mono w-12 shrink-0">{formatEval(evaluation, mate)}</span>
        <div className="flex h-2 flex-1 overflow-hidden rounded-full ring-1 ring-slate-700">
          <div style={{ width: `${whiteShare * 100}%`, background: "#e6ebf5" }} />
          <div style={{ width: `${(1 - whiteShare) * 100}%`, background: "#1b2438" }} />
        </div>
        <span className="shrink-0" style={{ color: "var(--muted)" }}>
          期望得分 <span className="mono">{formatPercent(share)}</span>
        </span>
      </div>
    );
  }

  return (
    <div className="panel-soft p-3">
      <div className="mb-2 flex items-center justify-between text-xs" style={{ color: "var(--muted)" }}>
        <span>{label ?? "局面评估（你的一方）"}</span>
        <span className="mono">{formatEval(evaluation, mate)}</span>
      </div>
      <div className="flex h-3 w-full overflow-hidden rounded-full ring-1 ring-slate-700">
        <div style={{ width: `${whiteShare * 100}%`, background: "#e6ebf5" }} />
        <div style={{ width: `${(1 - whiteShare) * 100}%`, background: "#1b2438" }} />
      </div>
      <div className="mt-2 flex items-center justify-between text-xs" style={{ color: "var(--muted)" }}>
        <span>期望得分 {formatPercent(share)}</span>
        <span>（胜率 + ½ 和棋率）</span>
      </div>
    </div>
  );
}
