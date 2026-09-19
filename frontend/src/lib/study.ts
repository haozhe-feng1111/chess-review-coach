import { Chess } from "chess.js";
import type { GameReview } from "./types";

export interface StudyNode {
  id: string; parent_id: string | null; uci: string; san: string; fen: string;
  ply: number; move_number: number; color: "white" | "black"; original_ply: number | null;
}
export interface Study {
  root_fen: string; revision: number; selected_id: string; nodes: StudyNode[];
}
export interface SearchSettings {
  mode: "time" | "depth" | "infinite"; seconds: number; depth: number;
  threads: number; hash_mb: number; multipv: number;
}
export interface SearchOptions {
  max_threads: number; max_hash_mb: number; max_depth: number; max_seconds: number;
  available: boolean; defaults: SearchSettings;
}
export interface EngineLine {
  rank: number; depth: number; cp: number | null; mate: number | null;
  bound: "lower" | "upper" | null; pv_uci: string[]; pv_san: string[];
}
export interface LiveSearch {
  id: string; fen: string; status: "queued" | "running" | "stopped" | "completed" | "failed";
  engine: string; settings: SearchSettings; applied: boolean; depth: number;
  nodes: number; nps: number; elapsed: number; hashfull: number; memory_mb: number | null;
  lines: EngineLine[]; error: string | null; outcome: { result: string; reason: string } | null;
}

export function pathTo(nodes: StudyNode[], id: string): StudyNode[] {
  const index = new Map(nodes.map(n => [n.id, n]));
  const path: StudyNode[] = [];
  let node = index.get(id);
  while (node?.parent_id) { path.push(node); node = index.get(node.parent_id); }
  return path.reverse();
}

export function appendLine(study: Study, from: string, moves: string[]): Study {
  const nodes = [...study.nodes];
  let cursor = nodes.find(n => n.id === from)!;
  for (const uci of moves) {
    const existing = nodes.find(n => n.parent_id === cursor.id && n.uci === uci);
    if (existing) { cursor = existing; continue; }
    if (nodes.length >= 2001) throw new Error("这盘棋已达到 2000 步上限，请先导出棋谱。 ");
    const board = new Chess(cursor.fen);
    const number = board.moveNumber();
    const move = board.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] });
    cursor = { id: `v${crypto.randomUUID()}`, parent_id: cursor.id, uci, san: move.san,
      fen: board.fen(), ply: cursor.ply+1, move_number: number,
      color: move.color === "w" ? "white" : "black", original_ply: null };
    nodes.push(cursor);
  }
  return { ...study, nodes: nodes.length === study.nodes.length ? study.nodes : nodes, selected_id: cursor.id };
}

export function studyPayload(study: Study) {
  return { revision: study.revision, selected_id: study.selected_id,
    moves: study.nodes.filter(n => n.parent_id).map(({ id, parent_id, uci }) => ({ id, parent_id, uci })) };
}

/** Export the current in-memory tree, including changes not yet saved to the server. */
export function exportPgn(study: Study, review: GameReview) {
  const headers: Record<string, string> = { ...review.headers, White: review.white, Black: review.black, Result: review.result };
  const initial = new Chess().fen();
  if (study.root_fen !== initial) { headers.SetUp = "1"; headers.FEN = study.root_fen; }
  const children = new Map<string, StudyNode[]>();
  for (const n of study.nodes) if (n.parent_id) children.set(n.parent_id, [...(children.get(n.parent_id) ?? []), n]);
  const token = (n: StudyNode) => `${n.move_number}${n.color === "white" ? "." : "..."} ${n.san}`;
  function line(first: StudyNode): string {
    const parts = [token(first)];
    let next = children.get(first.id) ?? [];
    while (next.length) {
      parts.push(token(next[0]));
      for (const variation of next.slice(1)) parts.push(`(${line(variation)})`);
      next = children.get(next[0].id) ?? [];
    }
    return parts.join(" ");
  }
  const starts = children.get("root") ?? [];
  let notation = "";
  if (starts.length) {
    // Root alternatives belong immediately after the first mainline move.
    const main = line(starts[0]);
    const head = token(starts[0]);
    notation = head + starts.slice(1).map(n => ` (${line(n)})`).join("") + main.slice(head.length);
  }
  return Object.entries(headers).map(([key, value]) => `[${key} "${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/[\r\n]/g, " ")}"]`).join("\n") + `\n\n${notation} ${review.result}\n`;
}

export function scoreText(line?: EngineLine) {
  if (!line) return "—";
  const prefix = line.bound === "lower" ? "≥" : line.bound === "upper" ? "≤" : "";
  return prefix + (line.mate !== null ? `${line.mate < 0 ? "−" : ""}M${Math.abs(line.mate)}` :
    line.cp !== null ? `${line.cp > 0 ? "+" : ""}${(line.cp/100).toFixed(2)}` : "—");
}
