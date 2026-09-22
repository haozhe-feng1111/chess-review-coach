"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { ApiError, api } from "@/lib/api";
import {
  SEVERITY_BADGE,
  SEVERITY_LABELS,
  conceptLabel,
  formatLoss,
  formatPercent,
  severityLabel,
} from "@/lib/labels";
import type { ProfileSummary, RecurringWeakness } from "@/lib/types";

const CONFIDENCE_LABELS: Record<string, string> = {
  insufficient: "样本不足",
  low: "初步观察",
  medium: "有一定参考价值",
};

const TREND_LABELS: Record<string, string> = {
  improving: "在变少",
  worsening: "在变多",
  flat: "没有明显变化",
  unknown: "样本不足",
};

const TREND_CLASSES: Record<string, string> = {
  improving: "text-emerald-300",
  worsening: "text-rose-300",
  flat: "text-slate-300",
  unknown: "text-slate-400",
};

const PHASE_SHORT: Record<string, string> = {
  opening: "开局",
  middlegame: "中局",
  endgame: "残局",
};

/** 区间条：把 95% Wilson 区间的宽度画出来，避免让小样本的百分比显得很确定。 */
function IntervalBar({ weakness, max }: { weakness: RecurringWeakness; max: number }) {
  const left = (weakness.share_low / max) * 100;
  const width = Math.max(1.5, ((weakness.share_high - weakness.share_low) / max) * 100);
  const point = (weakness.share / max) * 100;
  return (
    <div className="relative mt-2 h-2 w-full overflow-hidden rounded-full ring-1 ring-slate-700">
      <div
        className="absolute h-full bg-amber-500/35"
        style={{ left: `${left}%`, width: `${width}%` }}
      />
      <div
        className="absolute h-full w-[3px] bg-amber-300"
        style={{ left: `calc(${point}% - 1.5px)` }}
      />
    </div>
  );
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<ProfileSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .profile()
      .then(setProfile)
      .catch((caught: unknown) =>
        setError(caught instanceof ApiError ? caught.hintZh ?? caught.message : "加载失败"),
      );
  }, []);

  if (error) {
    return (
      <div className="panel p-6">
        <h1 className="text-lg font-semibold">无法加载个人档案</h1>
        <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
          {error}
        </p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="panel p-6 text-sm" style={{ color: "var(--muted)" }}>
        正在加载个人档案…
      </div>
    );
  }

  const maxShare = Math.max(0.0001, ...profile.weaknesses.map((weakness) => weakness.share));
  const maxProblemsPerGame = Math.max(
    0.0001,
    ...profile.time_controls.map((item) => item.problems_per_game),
  );
  const maxTrend = Math.max(
    0.0001,
    ...profile.trend_points.map((point) => point.average_expected_score_loss),
  );

  return (
    <div className="space-y-5">
      <section className="panel p-5">
        <h1 className="text-xl font-semibold">个人档案</h1>
        <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
          长期看的不只是「这盘棋怎么样」，而是「你反复犯哪一类错误」。
        </p>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="已分析对局" value={String(profile.total_games)} />
          <Stat label="你的着法" value={String(profile.total_player_moves)} />
          <Stat label="问题着法" value={String(profile.total_problems)} />
          <Stat label="严重失误" value={String(profile.blunders)} tone="blunder" />
          <Stat label="失误" value={String(profile.mistakes)} tone="mistake" />
          <Stat label="不够精确" value={String(profile.inaccuracies)} tone="inaccuracy" />
        </div>
        <p className="mt-3 text-xs" style={{ color: "var(--muted)" }}>
          平均期望得分损失 <span className="mono">{formatLoss(profile.average_expected_score_loss)}</span> ·{" "}
          {profile.sample_size_note_zh}
        </p>
        {profile.evidence_note_zh ? (
          <details className="mt-3 text-xs" style={{ color: "var(--muted)" }}>
            <summary className="cursor-pointer">这些数字是怎么算出来的（点开看口径与边界）</summary>
            <p className="mt-1 leading-relaxed">{profile.evidence_note_zh}</p>
          </details>
        ) : null}
      </section>

      {profile.next_focus ? (
        <section className="panel p-5 ring-1 ring-amber-900">
          <h2 className="text-base font-semibold text-amber-200">如果只能先改一件事</h2>
          <p className="mt-2 text-sm">{profile.next_focus.statement_zh}</p>
          <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
            怎么练：{profile.next_focus.drill_zh}
          </p>
          <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
            这是按「样本量够 + 占比最高」挑出来的，不是按感觉挑的。
            {CONFIDENCE_LABELS[profile.next_focus.confidence]
              ? `当前证据强度：${CONFIDENCE_LABELS[profile.next_focus.confidence]}。`
              : ""}
          </p>
        </section>
      ) : null}

      <section className="panel p-5">
        <h2 className="text-base font-semibold">
          {profile.weaknesses.length > 0 ? "你的失误集中在哪些类型" : "还没有足够的失误数据"}
        </h2>
        <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
          每一条都给出 95% 置信区间和趋势判断：区间宽说明样本还不够，宁可写得不确定，也不假装确定。
        </p>
        {profile.weaknesses.length === 0 ? (
          <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
            分析更多对局后，这里会显示反复出现的失误类型。
          </p>
        ) : (
          <div className="mt-3 space-y-3">
            {profile.weaknesses.slice(0, 6).map((weakness) => (
              <div key={weakness.error_type} className="panel-soft p-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-sm font-medium">{weakness.label_zh}</span>
                  <span className="text-xs" style={{ color: "var(--muted)" }}>
                    {formatPercent(weakness.share)} 的重大失误（95% 区间 {formatPercent(weakness.share_low)}–
                    {formatPercent(weakness.share_high)}） · {weakness.games} 局中 {weakness.event_count} 次 ·{" "}
                    {CONFIDENCE_LABELS[weakness.confidence] ?? weakness.confidence}
                  </span>
                </div>
                <IntervalBar weakness={weakness} max={maxShare} />
                <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
                  {weakness.statement_zh}
                </p>
                <p className={`mt-1 text-xs ${TREND_CLASSES[weakness.trend.direction] ?? ""}`}>
                  趋势：{TREND_LABELS[weakness.trend.direction] ?? weakness.trend.direction}
                  {weakness.trend.statement_zh ? ` —— ${weakness.trend.statement_zh}` : ""}
                </p>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs" style={{ color: "var(--muted)" }}>
                  {Object.entries(weakness.by_phase).map(([phase, count]) => (
                    <span key={phase}>
                      {PHASE_SHORT[phase] ?? phase} {count}
                    </span>
                  ))}
                  {weakness.clocked_events > 0 ? (
                    <span>
                      时间紧张 {weakness.under_time_pressure}/{weakness.clocked_events}
                    </span>
                  ) : (
                    <span>没有逐步时钟，无法判断是否与时间有关</span>
                  )}
                </div>
                <div className="mt-2 flex flex-wrap gap-1 text-xs">
                  {Object.entries(weakness.severity_mix).map(([severity, count]) => (
                    <span
                      key={severity}
                      className={`rounded px-1.5 py-0.5 ring-1 ${
                        SEVERITY_BADGE[severity as keyof typeof SEVERITY_BADGE] ?? ""
                      }`}
                    >
                      {severityLabel(severity as never)} {count}
                    </span>
                  ))}
                  <span className="tag">
                    平均损失 {formatLoss(weakness.average_expected_score_loss)}
                  </span>
                </div>
                {weakness.examples.length > 0 ? (
                  <div className="mt-2 space-y-1">
                    {weakness.examples.map((example) => (
                      <Link
                        key={`${example.game_id}-${example.ply}`}
                        href={`/games/${example.game_id}?ply=${example.ply}`}
                        className="block truncate text-xs hover:underline"
                        style={{ color: "var(--muted)" }}
                      >
                        · {example.move_number}. {example.san}
                        {example.opponent ? `（对 ${example.opponent}）` : ""}
                        {example.one_liner_zh ? ` — ${example.one_liner_zh}` : ""}
                      </Link>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel p-5">
        <h2 className="text-base font-semibold">时间维度：你是一快就崩，还是与时间无关</h2>
        <p className="mt-2 text-sm">{profile.clock_note_zh}</p>
        {profile.time_controls.length > 0 ? (
          <div className="mt-3 space-y-2">
            {profile.time_controls.map((item) => (
              <div key={item.speed}>
                <div className="flex items-baseline justify-between text-xs">
                  <span>
                    {item.label_zh} · {item.games} 局
                  </span>
                  <span style={{ color: "var(--muted)" }}>
                    每局 {item.problems_per_game.toFixed(2)} 个问题着法 · 平均损失{" "}
                    {formatLoss(item.average_expected_score_loss)}
                  </span>
                </div>
                <div className="mt-1 h-2 w-full overflow-hidden rounded-full ring-1 ring-slate-700">
                  <div
                    className="h-full bg-violet-500"
                    style={{
                      width: `${(item.problems_per_game / maxProblemsPerGame) * 100}%`,
                    }}
                  />
                </div>
              </div>
            ))}
            <p className="text-xs" style={{ color: "var(--muted)" }}>
              分档用的是 PGN 的 TimeControl 头（40 回合折算，Lichess 口径）。
              不同时限的对手强度也不同，所以这是相关，不是因果。
            </p>
          </div>
        ) : (
          <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
            这些对局的 PGN 里没有 TimeControl 头，无法按时限分档。
          </p>
        )}
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="panel p-5">
          <h2 className="text-base font-semibold">按对局阶段分布</h2>
          <div className="mt-3 space-y-2">
            {profile.phases.map((phase) => (
              <div key={phase.phase}>
                <div className="flex items-baseline justify-between text-xs">
                  <span>{phase.label_zh}</span>
                  <span style={{ color: "var(--muted)" }}>
                    {phase.events} 次 · {formatPercent(phase.share)} · 平均损失{" "}
                    {formatLoss(phase.average_expected_score_loss)}
                  </span>
                </div>
                <div className="mt-1 h-2 w-full overflow-hidden rounded-full ring-1 ring-slate-700">
                  <div className="h-full bg-sky-600" style={{ width: `${phase.share * 100}%` }} />
                </div>
              </div>
            ))}
          </div>

          {profile.top_concepts.length > 0 ? (
            <>
              <h3 className="mt-4 text-sm font-semibold">出现最多的概念</h3>
              <div className="mt-2 flex flex-wrap gap-1">
                {profile.top_concepts.map((concept) => (
                  <span key={concept.concept} className="tag">
                    {concept.label_zh || conceptLabel(concept.concept)} {concept.count}
                  </span>
                ))}
              </div>
            </>
          ) : null}
        </section>

        <section className="panel p-5">
          <h2 className="text-base font-semibold">趋势</h2>
          <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
            {profile.trend.statement_zh}
          </p>
          {profile.trend_points.length > 0 ? (
            <div className="mt-4 flex h-32 items-end gap-1">
              {profile.trend_points.map((point) => (
                <Link
                  key={point.game_id}
                  href={`/games/${point.game_id}`}
                  title={`${point.label} · 平均损失 ${formatLoss(point.average_expected_score_loss)}`}
                  className="flex-1 rounded-t bg-slate-600 hover:bg-sky-500"
                  style={{
                    height: `${Math.max(4, (point.average_expected_score_loss / maxTrend) * 100)}%`,
                  }}
                />
              ))}
            </div>
          ) : null}
          <p className="mt-3 text-xs" style={{ color: "var(--muted)" }}>
            柱状图是每盘棋的平均期望得分损失（越低越好）。
            {profile.trend.available && profile.trend.recent_average_loss !== null
              ? ` 最近 ${formatLoss(profile.trend.recent_average_loss)} vs 之前 ${formatLoss(
                  profile.trend.earlier_average_loss,
                )}。`
              : " 样本足够时才会给出趋势判断。"}
          </p>

          <h3 className="mt-4 text-sm font-semibold">下一步练习方向</h3>
          <ul className="mt-2 space-y-1 text-sm" style={{ color: "var(--muted)" }}>
            {profile.weaknesses.slice(0, 3).map((weakness) => (
              <li key={weakness.error_type}>· {weakness.label_zh}</li>
            ))}
            {profile.weaknesses.length === 0 ? <li>· 继续积累对局样本</li> : null}
          </ul>
          <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
            这些分类基于你自己的失误局面，未来可以直接生成对应的练习题。
          </p>
        </section>
      </div>

      <section className="panel p-5">
        <h2 className="text-base font-semibold">严重程度说明</h2>
        <div className="mt-2 grid gap-1 text-xs" style={{ color: "var(--muted)" }}>
          {(["inaccuracy", "mistake", "blunder"] as const).map((severity) => (
            <div key={severity} className="flex items-center gap-2">
              <span className={`rounded px-1.5 py-0.5 ring-1 ${SEVERITY_BADGE[severity]}`}>
                {SEVERITY_LABELS[severity]}
              </span>
              <span>{severity === "inaccuracy" ? "期望得分损失 5%–10%" : severity === "mistake" ? "10%–20%" : "超过 20%"}</span>
            </div>
          ))}
        </div>
        <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
          阈值可在后端 <span className="mono">analysis/thresholds.py</span> 中调整；它们是最初的工程默认值，并非科学标定。
        </p>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "blunder" | "mistake" | "inaccuracy";
}) {
  return (
    <div className="panel-soft p-3">
      <div className="text-xs" style={{ color: "var(--muted)" }}>
        {label}
      </div>
      <div
        className={`mono mt-1 text-lg font-semibold ${
          tone ? SEVERITY_BADGE[tone].split(" ")[1] : ""
        }`}
      >
        {value}
      </div>
    </div>
  );
}
