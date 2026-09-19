"use client";

import type { EngineEvidence } from "@/lib/types";
import { formatEval, formatLoss, formatPercent } from "@/lib/labels";

interface EvidencePanelProps {
  engine: EngineEvidence;
  engineName: string;
  /** SAN of the move actually played, shown next to the engine's recommendation. */
  playedSan: string;
}

function Row({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <span className="text-xs" style={{ color: "var(--muted)" }}>
        {label}
      </span>
      <span className={`text-sm ${mono ? "mono" : ""}`}>{value}</span>
    </div>
  );
}

function WdlRow({ label, wdl }: { label: string; wdl: { win: number; draw: number; loss: number } }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <span className="text-xs" style={{ color: "var(--muted)" }}>
        {label}
      </span>
      <span className="mono text-sm">
        胜 {formatPercent(wdl.win)} / 和 {formatPercent(wdl.draw)} / 负 {formatPercent(wdl.loss)}
      </span>
    </div>
  );
}

/**
 * ENGINE EVIDENCE.
 *
 * Everything in this panel is Stockfish output, reproduced verbatim. Nothing here is
 * generated text, which is why it is the section a user can always fall back on to
 * check an explanation.
 */
export default function EvidencePanel({ engine, engineName, playedSan }: EvidencePanelProps) {
  return (
    <div className="engine-block rounded-r-md p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="tag tag-engine">引擎证据 · {engineName}</span>
        <span className="text-xs" style={{ color: "var(--muted)" }}>
          深度 {engine.depth_before}
          {engine.depth_after ? ` / ${engine.depth_after}` : ""}
          {engine.multipv_before > 1 ? ` · MultiPV ${engine.multipv_before}` : ""}
        </span>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Row
            label="评估（你的一方）"
            value={`${formatEval(engine.evaluation_before, engine.mate_before)} → ${formatEval(
              engine.evaluation_after,
              engine.mate_after,
            )}`}
          />
          <WdlRow label="走子前引擎胜/和/负估计" wdl={engine.wdl_before} />
          <WdlRow label="走子后引擎胜/和/负估计" wdl={engine.wdl_after} />
          <p className="my-2 text-xs leading-relaxed" style={{ color: "var(--muted)" }}>
            这是引擎模型的估计；真人历史结果请看「真人实战统计」。
          </p>
          <Row
            label="期望得分"
            value={`${engine.expected_score_before.toFixed(3)} → ${engine.expected_score_after.toFixed(3)}`}
          />
          <Row label="期望得分损失" value={formatLoss(engine.expected_score_loss)} />
          <Row
            label="评估分损失（参考）"
            value={engine.centipawn_loss === null ? "不适用" : `${engine.centipawn_loss} cp`}
          />
          {engine.wdl_estimated ? (
            <p className="mt-2 text-xs text-amber-300">
              该引擎未提供 WDL 数据，严重程度是由评估分估算的。
            </p>
          ) : null}
        </div>

        <div>
          <Row label="引擎推荐" value={engine.best_move_san ?? "—"} />
          <Row label="实战走法" value={playedSan} />
          {engine.is_engine_best ? (
            <p className="py-1 text-xs text-emerald-300">你走的这一手就是引擎的第一选择。</p>
          ) : null}
          {engine.best_move_unique ? (
            <p className="py-1 text-xs text-amber-300">这个局面的好棋很窄，首选明显优于第二选择。</p>
          ) : null}
          <div className="mt-2 space-y-1 text-xs">
            <div>
              <span style={{ color: "var(--muted)" }}>推荐线路：</span>
              <span className="mono"> {engine.best_line_san.slice(0, 8).join(" ") || "—"}</span>
            </div>
            <div>
              <span style={{ color: "var(--muted)" }}>实战后续：</span>
              <span className="mono"> {engine.played_line_san.slice(0, 8).join(" ") || "—"}</span>
            </div>
          </div>
        </div>
      </div>

      {engine.alternatives.length > 0 ? (
        <div className="mt-3">
          <div className="mb-1 text-xs" style={{ color: "var(--muted)" }}>
            引擎的其他候选
          </div>
          <div className="space-y-1 text-xs">
            {engine.alternatives.map((candidate) => (
              <div key={candidate.uci} className="flex items-baseline gap-2">
                <span className="mono w-14 shrink-0">{candidate.san}</span>
                <span className="mono shrink-0" style={{ color: "var(--muted)" }}>
                  {formatEval(candidate.cp === null ? null : candidate.cp / 100, candidate.mate)}
                </span>
                <span className="mono truncate" style={{ color: "var(--muted)" }}>
                  {candidate.pv_san.slice(0, 6).join(" ")}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <p className="mt-3 text-[11px]" style={{ color: "var(--muted)" }}>
        以上数值全部来自 Stockfish，未经任何模型改写。严重程度以期望得分损失为准，评估分仅作参考。
      </p>
    </div>
  );
}
