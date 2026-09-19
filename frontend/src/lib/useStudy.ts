"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { request } from "./api";
import { studyPayload, type Study } from "./study";

/** Serialize saves; retain a local recovery copy until the database acknowledges it. */
export function useStudy(gameId: string, initial: Study) {
  const [study, setStudy] = useState(initial);
  const [saveState, setSaveState] = useState("分支已保存到本机");
  const [saveError, setSaveError] = useState("");
  const [recovery, setRecovery] = useState<Study | null>(null);
  const latest = useRef(initial);
  const savedNodes = useRef(initial.nodes);
  const revision = useRef(initial.revision);
  const saving = useRef(false);
  const draftKey = `chess-study-draft:${gameId}`;
  const flush = useCallback(async () => {
    if (saving.current || savedNodes.current === latest.current.nodes) return;
    saving.current = true;
    setSaveError("");
    try {
      while (savedNodes.current !== latest.current.nodes) {
        const sent = { ...latest.current, revision: revision.current };
        setSaveState("正在保存分支…");
        const response = await request<Study>(`/api/games/${gameId}/study`, { method: "PUT", body: JSON.stringify(studyPayload(sent)) });
        revision.current = response.revision;
        savedNodes.current = sent.nodes;
        try {
          if (latest.current.nodes === sent.nodes) localStorage.removeItem(draftKey);
          else localStorage.setItem(draftKey, JSON.stringify({ ...latest.current, revision: revision.current }));
        } catch { /* Database save is authoritative even when browser storage is unavailable. */ }
      }
      setSaveState("分支已保存到本机");
    } catch (error) {
      setSaveError((error as Error).message);
      setSaveState("分支尚未保存");
    } finally { saving.current = false; }
  }, [gameId, draftKey]);
  const change = useCallback((next: Study) => {
    latest.current = next;
    setStudy(next);
    if (savedNodes.current !== next.nodes) {
      setSaveState("等待保存…");
      try { localStorage.setItem(draftKey, JSON.stringify({ ...next, revision: revision.current })); }
      catch { setSaveError("浏览器无法保留离线草稿；请等待本机保存完成，或导出棋谱。 "); }
    }
  }, [draftKey]);
  useEffect(() => {
    // Defer storage access until mount; server-rendered markup stays deterministic.
    const timer = setTimeout(() => {
      try {
        const text = localStorage.getItem(draftKey);
        if (!text) return;
        const draft = JSON.parse(text) as Study;
        if (!Array.isArray(draft.nodes) || draft.root_fen !== initial.root_fen || !draft.nodes[0]?.fen) return;
        if (draft.revision === initial.revision) change(draft);
        else setRecovery(draft);
      } catch { /* An invalid recovery file must never stop opening the game. */ }
    }, 0);
    return () => clearTimeout(timer);
  }, [draftKey, initial, change]);
  useEffect(() => {
    const timer = setTimeout(() => { void flush(); }, 350);
    return () => clearTimeout(timer);
  }, [study.nodes, flush]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (savedNodes.current !== latest.current.nodes) { event.preventDefault(); }
    };
    window.addEventListener("beforeunload", warn);
    return () => { window.removeEventListener("beforeunload", warn); void flush(); };
  }, [flush]);
  return { study, change, saveState, saveError, retry: flush, recovery };
}
