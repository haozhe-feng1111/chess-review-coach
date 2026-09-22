/**
 * Chinese labels and visual tokens.
 *
 * The backend sends stable English enum values; the UI maps them here. Keeping the map
 * in one file means a new concept or error category shows up in exactly one place.
 */

import type { Color, GamePhase, PuzzleKind, PuzzleVerdict, Severity } from "./types";

export const SEVERITY_LABELS: Record<Severity, string> = {
  best: "最佳",
  excellent: "优秀",
  good: "良好",
  inaccuracy: "不够精确",
  mistake: "失误",
  blunder: "严重失误",
};

export const SEVERITY_TEXT: Record<Severity, string> = {
  best: "text-emerald-300",
  excellent: "text-emerald-300",
  good: "text-slate-300",
  inaccuracy: "text-amber-300",
  mistake: "text-orange-300",
  blunder: "text-rose-400",
};

export const SEVERITY_BADGE: Record<Severity, string> = {
  best: "bg-emerald-950 text-emerald-300 ring-emerald-800",
  excellent: "bg-emerald-950 text-emerald-300 ring-emerald-800",
  good: "bg-slate-800 text-slate-300 ring-slate-700",
  inaccuracy: "bg-amber-950 text-amber-300 ring-amber-800",
  mistake: "bg-orange-950 text-orange-300 ring-orange-800",
  blunder: "bg-rose-950 text-rose-300 ring-rose-800",
};

export const SEVERITY_DOT: Record<Severity, string> = {
  best: "bg-emerald-400",
  excellent: "bg-emerald-400",
  good: "bg-slate-500",
  inaccuracy: "bg-amber-400",
  mistake: "bg-orange-400",
  blunder: "bg-rose-500",
};

export const PHASE_LABELS: Record<GamePhase, string> = {
  opening: "开局",
  middlegame: "中局",
  endgame: "残局",
};

export const CRITICALITY_REASON_LABELS: Record<string, string> = {
  high_loss: "期望得分损失大",
  sign_flip: "局面优劣反转",
  missed_win: "漏掉胜机",
  mate_appears: "对手出现杀棋",
  mate_disappears: "自己的杀棋消失",
  position_collapse: "胜负逆转",
  forced_sequence: "进入强制序列",
  unique_best_move: "唯一好棋",
};

/** Fallback labels for concept/error values, in case the backend adds one first. */
export const CONCEPT_LABELS: Record<string, string> = {
  hanging_piece: "悬子（无保护）",
  undefended_piece: "无根子",
  attacked_piece: "被攻击的子力",
  material_loss: "丢子",
  missed_capture: "漏吃",
  missed_check: "漏将",
  missed_forcing_move: "漏掉强制手",
  fork: "叉子（双击）",
  pin: "牵制",
  skewer: "串击",
  discovered_attack: "闪击",
  double_attack: "双重攻击",
  overloaded_defender: "防守子超载",
  deflection: "引离防守子",
  removal_of_defender: "消除防守子",
  back_rank_weakness: "底线弱点",
  mating_threat: "杀棋威胁",
  trapped_piece: "被困子力",
  intermediate_move: "中间着（过渡着）",
  exchange_sacrifice: "交换弃子",
  king_safety_deterioration: "王安全下降",
  pawn_structure_damage: "兵形受损",
  isolated_pawn: "孤兵",
  doubled_pawn: "叠兵",
  passed_pawn: "通路兵",
  weak_square: "弱格",
  undeveloped_pieces: "子力未展开",
  queen_moved_repeatedly: "开局反复动后",
  piece_activity: "子力活跃度",
  open_file: "开放线",
  semi_open_file: "半开放线",
  bishop_pair: "双象",
  material_imbalance: "子力不平衡",
};

export const DECISION_ERROR_LABELS: Record<string, string> = {
  forcing_moves_not_checked: "未检查对手的强制手",
  hanging_piece: "把子力放在会被直接吃掉的位置",
  opponent_threat_ignored: "忽略了对手的威胁",
  defender_removed: "移动防守子后的战术漏洞",
  tactical_calculation: "战术计算失误",
  premature_attack: "过早进攻",
  king_safety: "王安全",
  material_judgment: "子力判断",
  piece_activity: "子力活跃度",
  opening_development: "开局出子",
  endgame_technique: "残局技术",
  advantage_conversion: "优势局面转换",
  time_pressure_unknown: "时间压力（无法判断）",
  unknown: "原因不明确",
};

export function conceptLabel(value: string): string {
  return CONCEPT_LABELS[value] ?? value;
}

export function decisionErrorLabel(value: string): string {
  return DECISION_ERROR_LABELS[value] ?? value;
}

export function severityLabel(value: Severity | null): string {
  return value ? SEVERITY_LABELS[value] : "—";
}

export function colorLabel(value: Color): string {
  return value === "white" ? "白方" : "黑方";
}

/** Format a pawns value the way a review should read it. */
export function formatEval(value: number | null, mate: number | null): string {
  if (mate !== null && mate !== undefined) {
    return mate > 0 ? `将杀 +${mate}` : `被将杀 ${mate}`;
  }
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function formatLoss(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(3);
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

// ------------------------------------------------------------------- 题目训练

export const PUZZLE_KIND_LABELS: Record<PuzzleKind, string> = {
  mate: "强制将杀",
  material: "赚取子力",
};

export const PUZZLE_DIFFICULTY_LABELS: Record<string, string> = {
  easy: "简单",
  medium: "中等",
  hard: "困难",
};

export const PUZZLE_VERDICT_LABELS: Record<PuzzleVerdict, string> = {
  correct: "走对了",
  also_good: "也算走对了",
  inaccurate: "不够好",
  wrong: "没走对",
  unverified: "无法判定",
};

export const PUZZLE_VERDICT_CLASSES: Record<PuzzleVerdict, string> = {
  correct: "bg-emerald-950 text-emerald-300 ring-emerald-800",
  also_good: "bg-emerald-950 text-emerald-200 ring-emerald-800",
  inaccurate: "bg-amber-950 text-amber-300 ring-amber-800",
  wrong: "bg-rose-950 text-rose-300 ring-rose-800",
  unverified: "bg-slate-800 text-slate-300 ring-slate-700",
};

export function puzzleKindLabel(value: PuzzleKind): string {
  return PUZZLE_KIND_LABELS[value] ?? value;
}

export function puzzleDifficultyLabel(value: string): string {
  return PUZZLE_DIFFICULTY_LABELS[value] ?? value;
}

/** 题目目标的一句话说明（将杀几步 / 净赚几分）。 */
export function puzzleGoalLabel(puzzle: {
  kind: PuzzleKind;
  mate_in: number | null;
  material_gain: number | null;
}): string {
  if (puzzle.kind === "mate") {
    return puzzle.mate_in ? `${puzzle.mate_in} 步内强制将杀` : "强制将杀";
  }
  return puzzle.material_gain ? `净赚 ${puzzle.material_gain} 分子力` : "赚取子力";
}
