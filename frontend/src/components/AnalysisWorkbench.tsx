"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Board from "./Board";
import EnginePanel from "./EnginePanel";
import VariationTree from "./VariationTree";
import HumanExplorerPanel from "./HumanExplorerPanel";
import { request } from "@/lib/api";
import { appendLine, exportPgn, pathTo, type Study, type SearchOptions, type SearchSettings } from "@/lib/study";
import { useLiveAnalysis } from "@/lib/useLiveAnalysis";
import { useStudy } from "@/lib/useStudy";
import type { GameReview } from "@/lib/types";

export default function AnalysisWorkbench({ review, initial, jump }: {
  review: GameReview; initial: Study; jump: { ply: number; serial: number } | null;
}) {
  const { study, change, saveState, saveError, retry, recovery } = useStudy(review.game_id, initial);
  const [orientation, setOrientation] = useState(review.player_color);
  const [options, setOptions] = useState<SearchOptions | null>(null);
  const [settings, setSettings] = useState<SearchSettings | null>(null);
  const [optionError, setOptionError] = useState("");
  const [optionRetry, setOptionRetry] = useState(0);
  const [enabled, setEnabled] = useState(true);
  const [tab, setTab] = useState("moves");
  const [arrows, setArrows] = useState(true);
  const [moveError, setMoveError] = useState("");
  const [uciInput, setUciInput] = useState("");
  const current = study.nodes.find(n => n.id === study.selected_id) ?? study.nodes[0];
  const path = useMemo(() => pathTo(study.nodes, current.id), [study.nodes, current.id]);
  const child = study.nodes.find(n => n.parent_id === current.id);
  const live = useLiveAnalysis(study.root_fen, path.map(n => n.uci), settings, enabled);
  const select = useCallback((id: string) => { change({ ...study, selected_id: id }); setMoveError(""); }, [study, change]);
  useEffect(() => {
    let disposed = false;
    request<SearchOptions>("/api/analysis/options").then(value => {
      if (disposed) return;
      setOptionError("");
      setOptions(value);
      let config = value.defaults;
      try {
        const stored = JSON.parse(localStorage.getItem("chess-engine-settings") ?? "null");
        if (stored && ["time", "depth", "infinite"].includes(stored.mode)) config = {
          mode: stored.mode,
          seconds: Math.min(600, Math.max(0.1, Number(stored.seconds) || 5)),
          depth: Math.min(60, Math.max(1, Math.round(Number(stored.depth) || 20))),
          threads: Math.min(value.max_threads, Math.max(1, Math.round(Number(stored.threads) || 2))),
          hash_mb: Math.min(value.max_hash_mb, Math.max(16, Math.round(Number(stored.hash_mb) || 64))),
          multipv: Math.min(5, Math.max(1, Math.round(Number(stored.multipv) || 3))),
        };
      } catch { /* Use safe defaults if storage is disabled. */ }
      setSettings(config);
    }).catch(error => { if (!disposed) setOptionError(error.message); });
    return () => { disposed = true; };
  }, [optionRetry]);
  useEffect(() => {
    if (!jump) return;
    const timer = setTimeout(() => {
      const id = jump.ply === 0 ? "root" : `m${jump.ply}`;
      if (study.nodes.some(n => n.id === id)) { select(id); setTab("moves"); }
    }, 0);
    return () => clearTimeout(timer);
    // A click on a review note is a one-shot navigation, not a lock on that move.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jump]);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest("input, textarea, select, [contenteditable=true], [role=dialog], [role=tab]")) return;
      let destination: string | undefined;
      if (event.key === "ArrowLeft") destination = current.parent_id ?? undefined;
      if (event.key === "ArrowRight") destination = child?.id;
      if (event.key === "Home") destination = "root";
      if (event.key === "End") destination = review.moves.length ? `m${review.moves.length}` : "root";
      if (destination) { event.preventDefault(); select(destination); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [current.parent_id, child?.id, review.moves.length, select]);
  function add(moves: string[]) {
    try { change(appendLine(study, current.id, moves)); setMoveError(""); setTab("moves"); setUciInput(""); }
    catch { setMoveError(study.nodes.length >= 2001 ? "分支已达到 2000 步上限，请导出棋谱。" : "这一步不合法，请检查走法后重试。 "); }
  }
  function download(target = study) {
    const url = URL.createObjectURL(new Blob([exportPgn(target, review)], { type: "application/x-chess-pgn;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `${review.game_id}-variations.pgn`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const best = live.data?.lines[0]?.pv_uci[0];
  const isBranch = current.original_ply === null;
  const mainAncestor = [...path].reverse().find(n => n.original_ply !== null)?.id ?? "root";
  const turn = current.fen.split(" ")[1] === "w" ? "白方" : "黑方";
  const recordedNext = current.original_ply !== null ? review.moves[current.original_ply]?.uci : undefined;
  return <section className="analysis-workbench" aria-label="分析工作台">
    <div className="workbench-board-column">
      <div className="board-context">
        <div className="flex flex-wrap items-center gap-2"><span className={`side-to-move ${turn === "白方" ? "white" : "black"}`} aria-hidden="true" /><strong>{turn}走棋</strong><span className="text-xs text-[var(--muted)]">{isBranch ? "分析分支" : "实战主线"}</span></div>
        <span className="mono text-sm">{current.ply ? `${current.move_number}${current.color === "white" ? "." : "..."} ${current.san}` : "起始局面"}</span>
      </div>
      <Board fen={current.fen} orientation={orientation} onMove={uci => add([uci])}
        lastMove={current.uci ? { from: current.uci.slice(0, 2), to: current.uci.slice(2, 4) } : null}
        bestMoveArrow={arrows && best ? { from: best.slice(0, 2), to: best.slice(2, 4) } : null} />
      <nav className="board-navigation" aria-label="棋谱导航">
        <button className="workbench-button" title="起始局面（Home）" aria-label="起始局面" onClick={() => select("root")} disabled={current.id === "root"}>
          <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><path d="M5 4v12m10-12-7 6 7 6" fill="none" stroke="currentColor" strokeWidth="1.7" /></svg>
        </button>
        <button className="workbench-button" onClick={() => current.parent_id && select(current.parent_id)} disabled={!current.parent_id} title="上一步（←）">上一步</button>
        <button className="workbench-button" onClick={() => child && select(child.id)} disabled={!child} title="下一步（→）">下一步</button>
        <button className="workbench-button" onClick={() => select(review.moves.length ? `m${review.moves.length}` : "root")} title="实战终局（End）" aria-label="实战终局">
          <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><path d="M15 4v12M5 4l7 6-7 6" fill="none" stroke="currentColor" strokeWidth="1.7" /></svg>
        </button>
        <button className="workbench-button" onClick={() => setOrientation(orientation === "white" ? "black" : "white")}>翻转棋盘</button>
      </nav>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="text-[var(--muted)]">拖动或点选走子 · 蓝箭头为引擎推荐</span>
        <label className="flex items-center gap-1.5"><input type="checkbox" checked={arrows} onChange={e => setArrows(e.target.checked)} />推荐箭头</label>
      </div>
      {isBranch && <button className="workbench-button mt-3" onClick={() => select(mainAncestor)}>回到实战分叉处</button>}
      {moveError && <p role="alert" className="mt-2 text-sm text-amber-200">{moveError}</p>}
      <details className="mt-3 text-xs text-[var(--muted)]"><summary className="cursor-pointer py-1">键盘输入走法</summary>
        <form className="mt-2 flex gap-2" onSubmit={event => { event.preventDefault(); add([uciInput.trim().toLowerCase()]); }}>
          <label className="sr-only" htmlFor="uci-move">走法坐标</label><input className="workbench-input min-w-0 flex-1" id="uci-move" placeholder="例如 e2e4；升变 e7e8q" value={uciInput} onChange={e => setUciInput(e.target.value)} required pattern="[a-hA-H][1-8][a-hA-H][1-8][qQrRbBnN]?" />
          <button className="workbench-button" type="submit">走子</button>
        </form>
      </details>
    </div>
    <div className="workbench-analysis-column">
      <EnginePanel options={options} settings={settings} data={live.data} error={live.error || optionError}
        enabled={enabled} visible={live.visible} fen={current.fen} onToggle={() => setEnabled(!enabled)}
        onRetryOptions={() => setOptionRetry(n => n + 1)}
        onApply={config => { setSettings(config); setEnabled(true); try { localStorage.setItem("chess-engine-settings", JSON.stringify(config)); } catch {} }} onLine={add} />
      <div className="workbench-tabs" role="tablist" aria-label="分析内容" onKeyDown={event => {
        if (event.target instanceof HTMLElement && event.target.getAttribute("role") === "tab" && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
          event.preventDefault(); const next = tab === "moves" ? "database" : "moves"; setTab(next); document.getElementById(`${next}-tab`)?.focus();
        }
      }}>
        <button role="tab" id="moves-tab" aria-controls="moves-panel" tabIndex={tab === "moves" ? 0 : -1} aria-selected={tab === "moves"} onClick={() => setTab("moves")}>分支棋谱</button>
        <button role="tab" id="database-tab" aria-controls="database-panel" tabIndex={tab === "database" ? 0 : -1} aria-selected={tab === "database"} onClick={() => setTab("database")}>真人数据库</button>
        <button className="export-pgn" onClick={() => download()}>导出 PGN</button>
      </div>
      {tab === "moves" ? <div role="tabpanel" id="moves-panel" aria-labelledby="moves-tab" className="flex min-h-0 flex-1 flex-col">
        <VariationTree nodes={study.nodes} selected={current.id} onSelect={select} moves={review.moves} />
        <div className="study-footer"><span>{review.result} · 实战结果</span><span role="status">{saveState}</span></div>
        {study.nodes.every(n => n.original_ply !== null) && <p className="px-4 pb-4 text-xs leading-relaxed text-[var(--muted)]">从任意一步试走，变化会缩进显示在实战旁；点引擎候选线也能加入分支。</p>}
      </div> : <div role="tabpanel" id="database-panel" aria-labelledby="database-tab" className="database-scroll"><HumanExplorerPanel fen={current.fen} playedMove={recordedNext} bestMove={best} /></div>}
      {saveError && <p className="px-4 pb-3 text-sm text-amber-200" role="alert">{saveError} <button className="underline underline-offset-4" onClick={() => void retry()}>重试保存</button></p>}
      {recovery && <p className="px-4 pb-3 text-sm text-amber-200">发现另一版本的未保存草稿。<button className="underline underline-offset-4" onClick={() => download(recovery)}>导出草稿备份</button></p>}
    </div>
  </section>;
}
