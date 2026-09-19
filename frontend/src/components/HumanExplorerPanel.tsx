"use client";

import { useEffect, useMemo, useState } from "react";
import { API_BASE, api } from "@/lib/api";
import type { ExplorerCounts, ExplorerResponse } from "@/lib/types";

const RATINGS: Record<string, number[]> = {
  "1200–1799": [1200, 1400, 1600],
  "0–1199": [0, 1000],
  "1800–2199": [1800, 2000],
  "2200 及以上": [2200, 2500],
  "全部等级分": [0, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500],
};
const SPEEDS: Record<string, string[]> = {
  "快棋 Rapid": ["rapid"],
  "超快棋 Blitz": ["blitz"],
  "慢棋 Classical": ["classical"],
  "子弹棋 Bullet": ["bullet"],
  "全部用时": ["ultraBullet", "bullet", "blitz", "rapid", "classical", "correspondence"],
};
const count = (value: number) => value.toLocaleString("zh-CN");
const total = (data: ExplorerCounts) => data.white + data.draws + data.black;
const percent = (value: number, n: number) => n ? `${(100 * value / n).toFixed(1)}%` : "—";

function Outcomes({ data, compact = false }: { data: ExplorerCounts; compact?: boolean }) {
  const n = total(data);
  return (
    <div className="space-y-1.5 tabular-nums">
      <div className="flex h-2.5 overflow-hidden rounded-sm border border-[var(--muted)]" aria-hidden="true">
        <span className="bg-slate-100" style={{ width: `${n ? 100 * data.white / n : 0}%` }} />
        <span className="bg-slate-400" style={{ width: `${n ? 100 * data.draws / n : 0}%` }} />
        <span className="bg-slate-800" style={{ width: `${n ? 100 * data.black / n : 0}%` }} />
      </div>
      <div className={compact ? "grid grid-cols-1 gap-1 text-xs" : "flex flex-wrap justify-between gap-x-3 gap-y-1 text-xs"}>
        <span title={`${count(data.white)} 局`}>白胜 {percent(data.white, n)}</span>
        <span title={`${count(data.draws)} 局`}>和棋 {percent(data.draws, n)}</span>
        <span title={`${count(data.black)} 局`}>黑胜 {percent(data.black, n)}</span>
      </div>
    </div>
  );
}

export default function HumanExplorerPanel({ fen, playedMove, bestMove }: {
  fen: string;
  playedMove?: string;
  bestMove?: string | null;
}) {
  const [rating, setRating] = useState("1200–1799");
  const [speed, setSpeed] = useState("快棋 Rapid");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [result, setResult] = useState<{ key: string; response?: ExplorerResponse; error?: string } | null>(null);
  const [cooldown, setCooldown] = useState(0);
  const query = useMemo(() => ({
    fen, ratings: RATINGS[rating], speeds: SPEEDS[speed], since: since || null, until: until || null,
  }), [fen, rating, speed, since, until]);
  const key = JSON.stringify([query, refresh]);
  const invalidRange = Boolean(since && until && since > until);

  useEffect(() => {
    if (!fen || invalidRange) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await api.explorer(query, controller.signal);
        if (!controller.signal.aborted) {
          setResult({ key, response });
          if (response.status === "rate_limited") setCooldown(response.retry_after ?? 60);
        }
      } catch {
        if (!controller.signal.aborted) setResult({ key, error: "无法获取真人统计，请检查本地服务和网络后刷新。" });
      }
    }, 350);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [fen, query, key, invalidRange]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((seconds) => Math.max(0, seconds - 1)), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  // A result belongs to one exact board/filter request. Never display old-board
  // statistics while the next request is still debouncing or in flight.
  const current = result?.key === key && !invalidRange ? result : null;
  const response = current?.response;
  const data = response?.status === "ok" ? response.data : null;
  const loading = !invalidRange && !current;
  const fieldClass = "mt-1 w-full min-w-0 rounded border border-[var(--border)] bg-[var(--panel-soft)] px-2 py-2 text-xs";

  return (
    <section className="human-explorer panel p-4" aria-labelledby="human-explorer-title" aria-busy={loading}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="human-explorer-title" className="text-sm font-semibold">真人实战统计</h2>
        <button type="button" className="rounded border border-[var(--border)] px-3 py-2 text-xs hover:bg-[var(--panel-soft)]"
          onClick={() => setRefresh((value) => value + 1)} disabled={loading || cooldown > 0 || invalidRange}>
          {cooldown > 0 ? `${cooldown} 秒后可刷新` : "刷新统计"}
        </button>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-[var(--muted)]">
        当前棋盘局面 · Lichess 有等级分对局
      </p>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <label className="min-w-0 text-xs text-[var(--muted)]">等级分分组
          <select value={rating} onChange={(event) => setRating(event.target.value)} className={fieldClass}>
            {Object.keys(RATINGS).map((label) => <option key={label}>{label}</option>)}
          </select>
        </label>
        <label className="min-w-0 text-xs text-[var(--muted)]">对局用时
          <select value={speed} onChange={(event) => setSpeed(event.target.value)} className={fieldClass}>
            {Object.keys(SPEEDS).map((label) => <option key={label}>{label}</option>)}
          </select>
        </label>
      </div>
      <details className="mt-3 text-xs text-[var(--muted)]">
        <summary className="cursor-pointer py-1">月份范围{since || until ? "（已筛选）" : "（全部历史）"}</summary>
        <div className="mt-2 grid grid-cols-2 gap-3">
          <label className="min-w-0">开始月份<input type="month" value={since} onChange={(event) => setSince(event.target.value)} className={fieldClass} /></label>
          <label className="min-w-0">结束月份<input type="month" value={until} onChange={(event) => setUntil(event.target.value)} className={fieldClass} /></label>
        </div>
      </details>
      <div className="mt-4" aria-live="polite">
        {invalidRange ? <p className="text-sm text-amber-200">开始月份不能晚于结束月份。</p> : null}
        {loading ? <p className="py-3 text-sm text-[var(--muted)]">正在查询当前局面的真人对局…</p> : null}
        {current?.error || (response && response.status !== "ok") ? (
          <div className="space-y-3 text-sm leading-relaxed">
            <p>{current?.error || response?.message_zh}</p>
            {response?.status === "auth_required" ? (
              <><a className="inline-block rounded border border-[var(--engine)] px-3 py-2 text-sky-200 hover:bg-[var(--panel-soft)]"
                href={`${API_BASE}/api/lichess/connect`} target="_blank" rel="noopener noreferrer">连接 Lichess</a>
                <p className="text-xs text-[var(--muted)]">在新标签页完成授权后，返回这里点击刷新统计。</p></>
            ) : null}
          </div>
        ) : null}
        {data ? (
          <>
            <p className="mb-3 text-sm tabular-nums">样本 <strong>{count(total(data))}</strong> 局</p>
            {total(data) > 0 ? <Outcomes data={data} /> : <p className="text-sm text-[var(--muted)]">此局面和筛选条件下暂无对局。可放宽筛选或退回前几步。</p>}
            {total(data) > 0 && total(data) < 100 ? <p className="mt-3 text-xs text-amber-200">样本不足 100 局，比例容易波动，请谨慎参考。</p> : null}
            {data.moves.length > 0 ? (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-xs tabular-nums">
                  <caption className="sr-only">常见走法的样本数、使用率和白胜、和棋、黑胜比例</caption>
                  <thead className="text-[var(--muted)]"><tr>
                    <th scope="col" className="pb-2 font-normal">走法 / 样本</th>
                    <th scope="col" className="pb-2 pr-3 text-right font-normal">使用率</th>
                    <th scope="col" className="pb-2 font-normal">白胜 / 和棋 / 黑胜</th>
                  </tr></thead>
                  <tbody>{data.moves.map((move) => <tr key={move.uci} className="border-t border-[var(--border)]">
                    <th scope="row" className="py-3 pr-2 font-normal">
                      <div className="flex flex-wrap items-center gap-1.5"><span className="mono font-semibold">{move.san}</span>
                        {move.uci === playedMove ? <span className="text-amber-200">实战</span> : null}
                        {move.uci === bestMove ? <span className="text-sky-200">引擎</span> : null}
                      </div>
                      <div className="mt-1 text-[var(--muted)]">{count(total(move))} 局{total(move) < 100 ? " · 少量样本" : ""}</div>
                    </th>
                    <td className="py-3 pr-3 text-right">{percent(total(move), total(data))}</td>
                    <td className="min-w-32 py-3"><Outcomes data={move} compact /></td>
                  </tr>)}</tbody>
                </table>
              </div>
            ) : null}
            <p className="mt-3 text-xs leading-relaxed text-[var(--muted)]">
              {data.moves.length > 0 ? "最多显示 12 种常见走法；使用率以当前局面的全部样本为分母。" : ""}
              历史胜率不代表你下一盘的获胜概率，也不决定引擎推荐。
            </p>
            <p className="mt-2 text-xs leading-relaxed text-[var(--muted)]">
              <a href="https://lichess.org/analysis#explorer" target="_blank" rel="noopener noreferrer" className="underline underline-offset-4 hover:text-[var(--text)]">数据来源：Lichess 开局库</a>
              {` · ${response?.cached ? "缓存于" : "获取于"} ${new Date(data.fetched_at).toLocaleString("zh-CN")}`}
            </p>
          </>
        ) : null}
      </div>
    </section>
  );
}
