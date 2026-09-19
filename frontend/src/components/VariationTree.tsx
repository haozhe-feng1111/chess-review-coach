"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { StudyNode } from "@/lib/study";
import { pathTo } from "@/lib/study";
import type { MoveAssessment } from "@/lib/types";
import { severityLabel } from "@/lib/labels";

export default function VariationTree({ nodes, selected, onSelect, moves }: {
  nodes: StudyNode[]; selected: string; onSelect: (id: string) => void; moves: MoveAssessment[];
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [manualAt, setManualAt] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const children = useMemo(() => {
    const map = new Map<string, StudyNode[]>();
    for (const node of nodes) if (node.parent_id) map.set(node.parent_id, [...(map.get(node.parent_id) ?? []), node]);
    return map;
  }, [nodes]);
  const activePath = new Set(pathTo(nodes, selected).map(n => n.id));
  useEffect(() => {
    const container = scroller.current;
    const active = container?.querySelector<HTMLElement>('[aria-current="step"]');
    if (container && active) {
      const offset = active.getBoundingClientRect().top - container.getBoundingClientRect().top;
      if (offset < 0 || offset > container.clientHeight - 48) container.scrollTop += offset - container.clientHeight / 2;
    }
  }, [selected]);
  const moveButton = (node: StudyNode) => {
    const severity = node.original_ply ? moves[node.original_ply - 1]?.severity : null;
    return <button type="button" key={node.id} className={`tree-move ${node.id === selected ? "is-active" : ""}`}
      data-node={node.id} aria-current={node.id === selected ? "step" : undefined}
      title={`${node.original_ply ? "实战" : "分析分支"} ${node.move_number}${node.color === "white" ? "." : "..."} ${node.san}${severity ? ` · ${severityLabel(severity)}` : ""}`}
      onClick={() => onSelect(node.id)}>
      <span className="tree-number">{node.move_number}{node.color === "white" ? "." : "..."}</span>{node.san}
      {severity && ["blunder", "mistake", "inaccuracy"].includes(severity) && <span className={`move-mark ${severity}`} aria-label={severityLabel(severity)}>{severity === "blunder" ? "??" : severity === "mistake" ? "?" : "?!"}</span>}
    </button>;
  };
  function branch(first: StudyNode, depth: number): React.ReactNode[] {
    const parts: React.ReactNode[] = [moveButton(first)];
    let next = children.get(first.id) ?? [];
    while (next.length) {
      parts.push(moveButton(next[0]));
      for (const alternative of next.slice(1)) parts.push(variation(alternative, depth + 1));
      next = children.get(next[0].id) ?? [];
    }
    return parts;
  }
  function variation(first: StudyNode, depth: number): React.ReactNode {
    const closed = collapsed.has(first.id) && (manualAt === selected || !activePath.has(first.id));
    return <div className="tree-variation" key={first.id} style={{ marginLeft: depth > 4 ? 0 : undefined }}>
      <button className="branch-toggle" aria-expanded={!closed} aria-label={`${closed ? "展开" : "收起"} ${first.move_number}${first.color === "white" ? "." : "..."} ${first.san} 分支`}
        onClick={() => { setManualAt(selected); setCollapsed(prev => { const next = new Set(prev); if (closed) next.delete(first.id); else next.add(first.id); return next; }); }}>
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d={closed ? "m6 3 5 5-5 5" : "m3 6 5 5 5-5"} fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
      </button>
      <div className="tree-variation-content">{closed ? moveButton(first) : branch(first, depth)}</div>
    </div>;
  }
  const mainRows: React.ReactNode[] = [];
  let candidates = children.get("root") ?? [];
  let pair: StudyNode[] = [];
  function flush() {
    if (!pair.length) return;
    const white = pair.find(n => n.color === "white");
    const black = pair.find(n => n.color === "black");
    mainRows.push(<div className="tree-main-row" key={`row-${pair[0].id}`}>
      <span className="tree-row-number">{pair[0].move_number}</span>
      <div>{white ? moveButton(white) : <span className="tree-number px-2">…</span>}</div>
      <div>{black ? moveButton(black) : null}</div>
    </div>);
    pair = [];
  }
  while (candidates.length) {
    const main = candidates[0];
    if (pair.length && (main.color === "white" || main.move_number !== pair[0].move_number)) flush();
    pair.push(main);
    if (candidates.length > 1) {
      flush();
      mainRows.push(<Fragment key={`branches-${main.id}`}>{candidates.slice(1).map(n => variation(n, 1))}</Fragment>);
    } else if (main.color === "black") flush();
    candidates = children.get(main.id) ?? [];
  }
  flush();
  return <div className="variation-scroll" ref={scroller} aria-label="分支棋谱">
    <div className="tree-column-head"><span>回合</span><span>白方</span><span>黑方</span></div>
    {mainRows.length ? mainRows : <p className="p-4 text-sm text-[var(--muted)]">在棋盘上走第一步，开始分析。</p>}
  </div>;
}
