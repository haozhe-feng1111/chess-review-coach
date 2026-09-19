"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import AnalysisWorkbench from "@/components/AnalysisWorkbench";
import CriticalMomentCard from "@/components/CriticalMomentCard";
import EvidencePanel from "@/components/EvidencePanel";
import ExplanationPanel from "@/components/ExplanationPanel";
import ProblemMoveList from "@/components/ProblemMoveList";
import { api, request } from "@/lib/api";
import type { Study } from "@/lib/study";
import type { GameReview, GameSummaryRecord, MomentExplanation } from "@/lib/types";

export default function GameReviewPage() {
  const { id } = useParams<{ id: string }>();
  const [loaded, setLoaded] = useState<{ review: GameReview; study: Study } | null>(null);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [jump, setJump] = useState<{ ply: number; serial: number } | null>(null);
  const [selectedPly, setSelectedPly] = useState<number | null>(null);
  const [explanations, setExplanations] = useState<Record<number, MomentExplanation>>({});
  const [explanationStatus, setExplanationStatus] = useState<Record<number, { loading: boolean; error: string }>>({});
  const [summary, setSummary] = useState<GameSummaryRecord | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState("");
  useEffect(() => {
    let disposed = false;
    Promise.all([api.review(id), request<Study>(`/api/games/${id}/study`)]).then(([{ review }, study]) => {
      if (disposed) return;
      const first = review.critical_moments[0];
      if (study.revision === 0 && first) study = { ...study, selected_id: first.ply > 1 ? `m${first.ply-1}` : "root" };
      setLoaded({ review, study }); setError("");
    }).catch(error => { if (!disposed) setError(error.message); });
    return () => { disposed = true; };
  }, [id, reload]);
  async function explain(ply: number) {
    setExplanationStatus(prev => ({ ...prev, [ply]: { loading: true, error: "" } }));
    try {
      const { explanation } = await api.explanation(id, ply);
      setExplanations(prev => ({ ...prev, [ply]: explanation }));
      setExplanationStatus(prev => ({ ...prev, [ply]: { loading: false, error: "" } }));
    } catch (error) { setExplanationStatus(prev => ({ ...prev, [ply]: { loading: false, error: (error as Error).message } })); }
  }
  function selectMoment(ply: number) {
    setSelectedPly(ply);
    setJump(prev => ({ ply: ply-1, serial: (prev?.serial ?? 0) + 1 }));
    if (!explanations[ply]) void explain(ply);
    document.querySelector('[aria-label="分析工作台"]')?.scrollIntoView({ behavior: "instant", block: "start" });
  }
  async function loadSummary() {
    setSummaryLoading(true); setSummaryError("");
    try { setSummary((await api.summary(id)).summary); }
    catch (error) { setSummaryError((error as Error).message); }
    finally { setSummaryLoading(false); }
  }
  if (error) return <div className="panel p-5"><h1 className="font-semibold">无法打开复盘</h1><p role="alert" className="my-3 text-sm text-amber-200">{error}</p><button className="workbench-button" onClick={() => setReload(n => n+1)}>重新加载</button><Link className="ml-4 text-sm underline" href="/">返回棋谱</Link></div>;
  if (!loaded || loaded.review.game_id !== id) return <div className="panel p-5 text-sm text-[var(--muted)]" role="status">正在载入棋谱和分析分支…</div>;
  const { review, study } = loaded;
  const moment = review.critical_moments.find(m => m.ply === selectedPly);
  return <div className="space-y-5">
    <header className="review-heading">
      <div><Link href="/" className="text-xs text-[var(--muted)] hover:text-[var(--text)]">返回棋谱</Link>
        <h1 className="mt-1 text-lg font-semibold">{review.white} <span className="mx-1 text-sm font-normal text-[var(--muted)]">vs</span> {review.black}</h1>
        <p className="mt-1 text-xs text-[var(--muted)]">{review.result} · 你执{review.player_color === "white" ? "白" : "黑"}{review.opening ? ` · ${review.opening}` : ""}</p>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--muted)]"><span>不够精确 <b className="text-[var(--text)]">{review.counts.inaccuracy}</b></span><span>失误 <b className="text-amber-300">{review.counts.mistake}</b></span><span>严重失误 <b className="text-red-300">{review.counts.blunder}</b></span></div>
    </header>
    <AnalysisWorkbench key={id} review={review} initial={study} jump={jump} />
    <section className="review-notes" aria-label="实战复盘说明">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">回看实战</h2><p className="mt-1 text-xs text-[var(--muted)]">下面的评价对应原棋谱。点关键局面，在棋盘上试走其他选择。</p></div>
        <div className="flex gap-2"><button className="workbench-button" onClick={loadSummary} disabled={summaryLoading}>{summaryLoading ? "生成中…" : summary ? "更新整盘总结" : "生成整盘总结"}</button><Link href="/profile" className="workbench-button">个人档案</Link></div>
      </div>
      {review.warnings.length > 0 && <ul className="mb-4 space-y-1 text-xs text-amber-200">{review.warnings.map(w => <li key={w}>{w}</li>)}</ul>}
      {summaryError && <p role="alert" className="mb-4 text-sm text-amber-200">{summaryError}</p>}
      {summary && <div className="coach-block mb-5 p-4"><span className="tag tag-coach">{summary.source === "llm" ? "AI 教练总结" : "规则模板总结"}</span><p className="mt-2 text-sm leading-relaxed">{summary.explanation.summary}</p><ul className="mt-2 list-inside list-disc space-y-1 text-sm">{summary.explanation.practice_advice.map(t => <li key={t}>{t}</li>)}</ul></div>}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-3">{review.critical_moments.map((m, index) => <CriticalMomentCard key={m.ply} moment={m} index={index} selected={selectedPly === m.ply} onSelect={selectMoment} />)}
          {!review.critical_moments.length && <p className="py-3 text-sm text-[var(--muted)]">没有需要单独讲解的关键局面，可以直接在上方棋盘研究变化。</p>}
          <ProblemMoveList moves={review.moves} selectedPly={selectedPly} onSelect={ply => { setSelectedPly(ply); setJump(prev => ({ ply: ply-1, serial: (prev?.serial ?? 0)+1 })); document.querySelector('[aria-label="分析工作台"]')?.scrollIntoView({ block: "start" }); }} />
        </div>
        {moment && <div className="space-y-3"><h3 className="text-sm font-semibold">第 {moment.move_number} 回合 · 实战 {moment.played_move_san}</h3><EvidencePanel engine={moment.evidence.engine} engineName={review.engine.engine_name} playedSan={moment.played_move_san} />
          <ExplanationPanel explanation={explanations[moment.ply] ?? null} loading={explanationStatus[moment.ply]?.loading ?? false} error={explanationStatus[moment.ply]?.error || null} llmConfigured={review.llm_available} onRetry={() => void explain(moment.ply)} />
        </div>}
      </div>
    </section>
  </div>;
}
