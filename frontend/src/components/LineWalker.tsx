"use client";

import type { LineWalk, MomentLines } from "@/lib/types";

export type LineKind = "best" | "played";

interface LineWalkerProps {
  lines: MomentLines | null;
  loading: boolean;
  active: boolean;
  kind: LineKind;
  /** 已经走了线路里的多少步；0 = 还停在决策点。 */
  index: number;
  playing: boolean;
  onStart: () => void;
  onExit: () => void;
  onKindChange: (kind: LineKind) => void;
  onIndexChange: (index: number) => void;
  onTogglePlaying: () => void;
}

/**
 * 引擎线路演示器。
 *
 * 引擎给的不只是一手棋，还有一整条主变例。这个组件把它变成可以"播放"的东西：
 * 一步一步走、随时回到起点、或者直接跳到某一步，看完点「返回实战对局」回到真实棋局。
 *
 * 两条线路都能走：
 *   * 引擎推荐线路 —— 如果当时走对了会怎样；
 *   * 实战线路     —— 实际发生了什么（引擎接着会怎么惩罚你）。
 */
export default function LineWalker({
  lines,
  loading,
  active,
  kind,
  index,
  playing,
  onStart,
  onExit,
  onKindChange,
  onIndexChange,
  onTogglePlaying,
}: LineWalkerProps) {
  // 入口按钮必须在"还没取数据"时就能显示出来——线路数据是点了按钮才去取的，
  // 所以这里绝不能因为 lines === null 就直接 return null（那会让按钮永远出不来）。
  if (!active) {
    return (
      <div className="panel-soft flex flex-wrap items-center gap-2 p-3 text-xs">
        <button
          type="button"
          onClick={onStart}
          className="rounded border px-3 py-1.5 text-sm text-sky-300"
          style={{ borderColor: "rgba(79,156,249,0.5)" }}
        >
          ▶ 演示后续走法
        </button>
        <span style={{ color: "var(--muted)" }}>
          从当前这个局面出发，在棋盘上一步步走完引擎推荐的后续；
          也可以切到「实战线路」看对手会怎么惩罚，随时点「返回实战对局」回到真实棋局。
        </span>
      </div>
    );
  }

  if (loading && !lines) {
    return (
      <div className="panel-soft p-3 text-xs" style={{ color: "var(--muted)" }}>
        正在展开引擎线路…
      </div>
    );
  }

  if (!lines) {
    return (
      <div className="panel-soft flex flex-wrap items-center gap-2 p-3 text-xs">
        <span className="text-amber-300">没能取到这个局面的线路数据。</span>
        <button
          type="button"
          onClick={onStart}
          className="rounded border px-2 py-1"
          style={{ borderColor: "var(--border)" }}
        >
          重试
        </button>
        <button
          type="button"
          onClick={onExit}
          className="rounded border px-2 py-1"
          style={{ borderColor: "var(--border)" }}
        >
          返回实战对局
        </button>
      </div>
    );
  }

  const walk: LineWalk = kind === "best" ? lines.best : lines.played;
  const total = walk.steps.length;
  const currentStep = index > 0 ? walk.steps[index - 1] : null;
  const nextStep = index < total ? walk.steps[index] : null;

  return (
    <div
      className="rounded-md border p-3"
      style={{ borderColor: "rgba(79,156,249,0.5)", background: "rgba(79,156,249,0.06)" }}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="tag tag-engine">线路演示中</span>
          <div className="flex overflow-hidden rounded border" style={{ borderColor: "var(--border)" }}>
            {(
              [
                ["best", "引擎推荐线路"],
                ["played", "实战线路"],
              ] as [LineKind, string][]
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => onKindChange(value)}
                className={`px-2.5 py-1 text-xs ${
                  kind === value ? "bg-slate-700 text-white" : ""
                }`}
                style={kind === value ? undefined : { color: "var(--muted)" }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <button
          type="button"
          onClick={onExit}
          className="rounded border px-3 py-1 text-xs"
          style={{ borderColor: "var(--border)" }}
        >
          ← 返回实战对局
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <button
          type="button"
          onClick={onTogglePlaying}
          disabled={total === 0}
          className="rounded border px-2.5 py-1"
          style={{ borderColor: "var(--border)" }}
          title={playing ? "暂停" : "自动播放"}
        >
          {playing ? "⏸ 暂停" : "▶ 自动播放"}
        </button>
        <button
          type="button"
          onClick={() => onIndexChange(0)}
          disabled={index === 0}
          className="rounded border px-2.5 py-1"
          style={{ borderColor: "var(--border)" }}
          title="回到决策点"
        >
          ⏮
        </button>
        <button
          type="button"
          onClick={() => onIndexChange(Math.max(0, index - 1))}
          disabled={index === 0}
          className="rounded border px-2.5 py-1"
          style={{ borderColor: "var(--border)" }}
          title="线路上一手（←）"
        >
          ◀
        </button>
        <span className="mono" style={{ color: "var(--muted)" }}>
          {index}/{total}
        </span>
        <button
          type="button"
          onClick={() => onIndexChange(Math.min(total, index + 1))}
          disabled={index >= total}
          className="rounded border px-2.5 py-1"
          style={{ borderColor: "var(--border)" }}
          title="线路下一手（→）"
        >
          ▶
        </button>
        <button
          type="button"
          onClick={() => onIndexChange(total)}
          disabled={index >= total}
          className="rounded border px-2.5 py-1"
          style={{ borderColor: "var(--border)" }}
          title="走到底"
        >
          ⏭
        </button>
      </div>

      <div className="mt-2 flex flex-wrap gap-1">
        {walk.steps.map((step, stepIndex) => {
          const isCurrent = stepIndex === index - 1;
          const isNext = stepIndex === index;
          return (
            <button
              key={`${step.uci}-${stepIndex}`}
              type="button"
              onClick={() => onIndexChange(stepIndex + 1)}
              className={`mono rounded border px-1.5 py-0.5 text-xs ${
                isCurrent ? "bg-sky-700 text-white" : isNext ? "border-sky-500 text-sky-200" : ""
              }`}
              style={isCurrent || isNext ? undefined : { borderColor: "var(--border)", color: "var(--muted)" }}
              title={`第 ${stepIndex + 1} 步（${step.mover === "white" ? "白" : "黑"}方）`}
            >
              {step.san}
            </button>
          );
        })}
      </div>

      <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
        {currentStep
          ? `刚走：${currentStep.mover === "white" ? "白方" : "黑方"} ${currentStep.san}`
          : `起点：这个局面（评估 ${lines.evaluation_before ?? "—"}）`}
        {nextStep ? ` · 接下来：${nextStep.san}` : ""}
        {" · "}
        {index > 0 ? "点 ⏮ 可回到起点" : "点 ▶ 一步步走"}
      </p>

      {index >= total && total > 0 ? (
        <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
          {walk.ends_in_mate
            ? "线路以将杀结束。"
            : walk.truncated
              ? "引擎线路在保存时截断到前若干步，到这里就结束了。"
              : "线路到此结束。"}
        </p>
      ) : null}
      {!walk.complete ? (
        <p className="mt-1 text-xs text-amber-300">
          这条线路里有走不动的着法（数据不完整），演示到此为止。
        </p>
      ) : null}
      <p className="mt-1 text-[11px]" style={{ color: "var(--muted)" }}>
        线路里的每一步都是引擎认为双方最优的走法，所以走完之后的评估仍然接近起点的评估
        {lines.evaluation_before !== null ? `（${lines.evaluation_before}）` : ""}。
        键盘：<span className="mono">←</span> <span className="mono">→</span> 在线路里走，
        <span className="mono">Esc</span> 返回实战。
      </p>
    </div>
  );
}
