"use client";

import type { MoveAssessment } from "@/lib/types";
import { SEVERITY_BADGE, decisionErrorLabel, formatLoss, severityLabel } from "@/lib/labels";

interface ProblemMoveListProps {
  moves: MoveAssessment[];
  onSelect: (ply: number) => void;
  selectedPly: number | null;
}

/**
 * 全部问题着法（不够精确 / 失误 / 严重失误）的一览表。
 *
 * 关键局面只展示 3–5 个并附带 AI 解释；这里把**其余**问题着法也列出来，
 * 但只给引擎推荐、不给解释——这正是"次一级关键"该有的待遇：
 * 你想看的时候一眼就能看到该走什么，不想看的时候也不会被大段文字淹没。
 */
export default function ProblemMoveList({
  moves,
  onSelect,
  selectedPly,
}: ProblemMoveListProps) {
  const problems = moves.filter(
    (move) =>
      move.is_player_move &&
      move.severity !== null &&
      (move.severity === "inaccuracy" ||
        move.severity === "mistake" ||
        move.severity === "blunder"),
  );

  return (
    <div className="panel p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">
          全部问题着法（{problems.length} 个）
        </h2>
        <span className="text-xs" style={{ color: "var(--muted)" }}>
          只给引擎推荐，不生成 AI 解释
        </span>
      </div>

      {problems.length === 0 ? (
        <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
          这盘棋没有出现「不够精确」及以上的着法。
        </p>
      ) : (
        <div className="mt-2 max-h-[320px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead>
              <tr style={{ color: "var(--muted)" }}>
                <th className="py-1 text-left font-normal">手数</th>
                <th className="py-1 text-left font-normal">实战</th>
                <th className="py-1 text-left font-normal">引擎推荐</th>
                <th className="py-1 text-left font-normal">主要失误原因</th>
                <th className="py-1 text-right font-normal">期望得分损失</th>
              </tr>
            </thead>
            <tbody>
              {problems.map((move) => (
                <tr
                  key={move.ply}
                  onClick={() => onSelect(move.ply)}
                  className={`cursor-pointer border-t transition ${
                    selectedPly === move.ply ? "bg-slate-700/50" : "hover:bg-slate-800/60"
                  }`}
                  style={{ borderColor: "var(--border)" }}
                  title="点击跳到这个局面"
                >
                  <td className="py-1.5 pr-2 whitespace-nowrap" style={{ color: "var(--muted)" }}>
                    {move.move_number}
                    {move.color === "white" ? "." : "..."}
                  </td>
                  <td className="py-1.5 pr-2">
                    <span className="mono">{move.san}</span>
                    {move.severity ? (
                      <span
                        className={`ml-1.5 rounded px-1 py-0.5 text-[10px] ring-1 ${
                          SEVERITY_BADGE[move.severity]
                        }`}
                      >
                        {severityLabel(move.severity)}
                      </span>
                    ) : null}
                  </td>
                  <td className="py-1.5 pr-2">
                    {move.is_engine_best ? (
                      <span className="text-emerald-300">就是引擎首选</span>
                    ) : (
                      <span className="mono text-sky-300">{move.best_move_san ?? "—"}</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-2" style={{ color: "var(--muted)" }}>
                    {move.primary_error ? decisionErrorLabel(move.primary_error) : "—"}
                  </td>
                  <td className="mono py-1.5 text-right">
                    {formatLoss(move.expected_score_loss)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
