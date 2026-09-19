"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE, request } from "./api";
import type { LiveSearch, SearchSettings } from "./study";

export function useLiveAnalysis(rootFen: string, moves: string[], settings: SearchSettings | null, enabled: boolean) {
  const client = useRef("");
  const sequence = useRef(0);
  const [visible, setVisible] = useState(true);
  const [result, setResult] = useState<{ key: string; data?: LiveSearch; error?: string } | null>(null);
  const key = JSON.stringify([rootFen, moves, settings]);
  useEffect(() => {
    const change = () => setVisible(!document.hidden);
    change();
    document.addEventListener("visibilitychange", change);
    return () => document.removeEventListener("visibilitychange", change);
  }, []);
  useEffect(() => {
    if (!enabled || !visible || !settings) return;
    if (!client.current) client.current = crypto.randomUUID();
    const requestSequence = ++sequence.current;
    let disposed = false;
    let id: string | null = null;
    let timer: ReturnType<typeof setTimeout>;
    const stop = () => {
      if (id) void fetch(`${API_BASE}/api/analysis/${id}/stop`, { method: "POST", keepalive: true }).catch(() => {});
    };
    const poll = async () => {
      try {
        const data = await request<LiveSearch>(`/api/analysis/${id}`);
        if (disposed) return;
        setResult({ key, data });
        if (data.status === "running" || data.status === "queued") timer = setTimeout(poll, 250);
      } catch (error) {
        if (!disposed) { setResult({ key, error: (error as Error).message }); stop(); }
      }
    };
    timer = setTimeout(async () => {
      try {
        const [fen, path, config] = JSON.parse(key);
        const data = await request<LiveSearch>("/api/analysis/start", { method: "POST", body: JSON.stringify({
          client_id: client.current, sequence: requestSequence, root_fen: fen, moves: path, settings: config,
        }) });
        id = data.id;
        if (disposed) { stop(); return; }
        setResult({ key, data });
        timer = setTimeout(poll, 120);
      } catch (error) {
        if (!disposed) setResult({ key, error: (error as Error).message });
      }
    }, 180);
    window.addEventListener("pagehide", stop);
    return () => { disposed = true; clearTimeout(timer); stop(); window.removeEventListener("pagehide", stop); };
  }, [key, enabled, visible, settings]);
  return { data: result?.key === key ? result.data : undefined, error: result?.key === key ? result.error : undefined, visible };
}
