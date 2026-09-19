"use client";

import { useState } from "react";
import { scoreText, type EngineLine, type LiveSearch, type SearchOptions, type SearchSettings } from "@/lib/study";

const MODE = { time: "按时间", depth: "按深度", infinite: "持续分析" };
export default function EnginePanel({ options, settings, data, error, enabled, visible, fen, onApply, onToggle, onLine, onRetryOptions }: {
  options: SearchOptions | null; settings: SearchSettings | null; data?: LiveSearch; error?: string;
  enabled: boolean; visible: boolean; fen: string; onApply: (settings: SearchSettings) => void;
  onToggle: () => void; onLine: (moves: string[]) => void;
  onRetryOptions: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<SearchSettings | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const current = draft ?? settings;
  const fields = fen.split(" ");
  const turn = fields[1];
  const number = Number(fields[5]);
  const working = enabled && visible && (!data || ["queued", "running"].includes(data.status)) && !error;
  const state = !enabled ? "已暂停" : !visible ? "页面隐藏，已暂停" : error || data?.status === "failed" ? "分析中断" :
    data?.outcome ? "终局" : data?.status === "completed" ? "分析完成" : data?.status === "stopped" ? "已停止" : "正在分析";
  function notation(index: number, san: string) {
    const half = (turn === "b" ? 1 : 0) + index;
    const moveNumber = number + Math.floor(half / 2);
    return half % 2 === 0 ? `${moveNumber}. ${san}` : index === 0 ? `${moveNumber}... ${san}` : san;
  }
  function pv(line: EngineLine) {
    const isOpen = expanded.has(line.rank);
    return <div className="pv-row" key={line.rank}>
      <span className="pv-score mono">{scoreText(line)}</span>
      <div className={`pv-moves ${isOpen ? "is-expanded" : ""}`}>
        {line.pv_san.map((san, i) => <button key={i} type="button" title={`试走到 ${notation(i, san)}`}
          onClick={() => onLine(line.pv_uci.slice(0, i + 1))}>{notation(i, san)}</button>)}
        {isOpen && <button className="pv-add" onClick={() => onLine(line.pv_uci)}>加入整条分支</button>}
      </div>
      <button className="pv-expand" title={`深度 ${line.depth}`} aria-label={`${isOpen ? "收起" : "展开"}第 ${line.rank} 条候选线`}
        aria-expanded={isOpen} onClick={() => setExpanded(prev => { const next = new Set(prev); if (next.has(line.rank)) next.delete(line.rank); else next.add(line.rank); return next; })}>
        <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d={isOpen ? "m3 10 5-5 5 5" : "m3 6 5 5 5-5"} fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
      </button>
    </div>;
  }
  return <section className="engine-live" aria-label="实时引擎">
    <div className="engine-topbar">
      <button className={`engine-switch ${enabled ? "is-on" : ""}`} aria-label={enabled ? "暂停引擎" : "启动引擎"}
        aria-pressed={enabled} onClick={onToggle} disabled={!settings}>
        <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true">
          {enabled ? <path d="M7 4v12M13 4v12" stroke="currentColor" strokeWidth="2.5" /> : <path d="m6 3 10 7-10 7Z" fill="currentColor" />}
        </svg>
      </button>
      <strong className="engine-score mono" title="正数白方有利，负数黑方有利">{data?.outcome ? data.outcome.result : scoreText(data?.lines[0])}</strong>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 text-sm font-medium"><span>{data?.engine ?? "Stockfish"}</span><span className={`engine-state ${working ? "is-working" : ""}`}>{state}</span></div>
        <p className="mt-0.5 text-xs text-[var(--muted)] tabular-nums">深度 {data?.depth ?? "—"} · {data ? `${Math.round(data.nps / 1000).toLocaleString()} kn/s · ${data.elapsed.toFixed(1)} s` : "等待局面"}</p>
      </div>
      <button className="workbench-button engine-settings-button" aria-expanded={open} onClick={() => { setDraft(settings); setOpen(!open); }} disabled={!settings}>设置</button>
    </div>
    <div className="engine-budget text-xs text-[var(--muted)]">
      <span>白方视角</span>
      {settings && <span>{settings.mode === "time" ? `${settings.seconds} 秒 / 局面` : settings.mode === "depth" ? `目标深度 ${settings.depth}` : "持续分析"} · {settings.threads} Threads · {settings.hash_mb} MB Hash</span>}
    </div>
    {open && current && options && <form className="engine-settings" onSubmit={event => {
      event.preventDefault(); onApply(current); setOpen(false);
    }}>
      <div className="engine-settings-grid">
        <label>分析方式<select value={current.mode} onChange={e => setDraft({ ...current, mode: e.target.value as SearchSettings["mode"] })}>
          {Object.entries(MODE).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        {current.mode !== "infinite" && <label>{current.mode === "time" ? "思考时间（秒）" : "分析深度"}
          <input type="number" required min={current.mode === "time" ? 0.1 : 1} step={current.mode === "time" ? 0.1 : 1}
            max={current.mode === "time" ? options.max_seconds : options.max_depth}
            value={current.mode === "time" ? current.seconds : current.depth}
            onChange={e => setDraft({ ...current, [current.mode === "time" ? "seconds" : "depth"]: e.target.value === "" ? "" : Number(e.target.value) } as SearchSettings)} />
        </label>}
        <label>线程 Threads<input type="number" required min="1" max={options.max_threads} value={current.threads}
          onChange={e => setDraft({ ...current, threads: e.target.value === "" ? "" : Number(e.target.value) } as SearchSettings)} /></label>
        <label>内存 Hash（MB）<input type="number" required min="16" max={options.max_hash_mb} value={current.hash_mb}
          onChange={e => setDraft({ ...current, hash_mb: e.target.value === "" ? "" : Number(e.target.value) } as SearchSettings)} /></label>
        <label>候选线 MultiPV<select value={current.multipv} onChange={e => setDraft({ ...current, multipv: Number(e.target.value) })}>
          {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n} 条</option>)}</select></label>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-[var(--muted)]">本机计算，不产生 API 费用。Threads 最多 {options.max_threads}；Hash 是置换表大小，进程总内存会更高。持续分析直到暂停或离开页面。</p>
      <div className="mt-3 flex gap-2"><button className="workbench-button primary" type="submit">应用并重新分析</button><button className="workbench-button" type="button" onClick={() => setOpen(false)}>取消</button></div>
    </form>}
    {(error || data?.error) && <div role="alert" className="p-3 text-sm text-amber-200">{error || data?.error} <button className="underline underline-offset-4" onClick={() => settings ? onApply({ ...settings }) : onRetryOptions()}>重试分析</button></div>}
    {data?.outcome ? <p className="p-4 text-sm">{data.outcome.reason === "checkmate" ? "将死" : data.outcome.reason === "stalemate" ? "逼和" : "和棋"} · {data.outcome.result}。可回到前面的局面继续试走。</p> :
      data?.lines.length ? <div className="engine-pvs">{data.lines.map(pv)}</div> :
        <p className="px-4 py-5 text-sm text-[var(--muted)]">{!enabled ? "启动引擎，查看当前局面的候选线路。" : error ? "走子和分支仍可使用。" : "正在计算候选线路…"}</p>}
    {data?.applied && <p className="engine-resource text-xs text-[var(--muted)] tabular-nums">
      已应用 {data.settings.threads} Threads / {data.settings.hash_mb} MB · 进程内存 {data.memory_mb ?? "—"} MB · Hash 使用 {(data.hashfull / 10).toFixed(1)}%
    </p>}
  </section>;
}
