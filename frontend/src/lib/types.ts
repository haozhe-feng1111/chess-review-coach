/**
 * Types mirrored from the backend Pydantic schemas.
 *
 * Kept deliberately hand-written and narrow: only the fields the UI actually reads.
 * The backend is the source of truth; if a field is renamed there, TypeScript will
 * point at every place that needs updating.
 */

export type Color = "white" | "black";
export type Severity = "best" | "excellent" | "good" | "inaccuracy" | "mistake" | "blunder";
export type GamePhase = "opening" | "middlegame" | "endgame";
export type AnalysisStatus = "pending" | "running" | "completed" | "failed";
export type ExplanationSource = "llm" | "rules";

export interface Wdl {
  win: number;
  draw: number;
  loss: number;
}

export interface CandidateMove {
  uci: string;
  san: string;
  cp: number | null;
  mate: number | null;
  wdl: Wdl;
  expected_score: number;
  pv_uci: string[];
  pv_san: string[];
}

export interface DetectedConcept {
  type: string;
  confidence: number;
  pieces: string[];
  squares: string[];
  evidence: string[];
  metadata: Record<string, string>;
}

export interface DecisionError {
  type: string;
  confidence: number;
  rationale: string;
  supporting_concepts: string[];
}

export interface EngineEvidence {
  pov_color: Color;
  evaluation_before: number | null;
  evaluation_after: number | null;
  mate_before: number | null;
  mate_after: number | null;
  wdl_before: Wdl;
  wdl_after: Wdl;
  expected_score_before: number;
  expected_score_after: number;
  expected_score_loss: number;
  centipawn_loss: number | null;
  best_move_uci: string | null;
  best_move_san: string | null;
  best_line_uci: string[];
  best_line_san: string[];
  played_line_uci: string[];
  played_line_san: string[];
  depth_before: number;
  depth_after: number;
  nodes_before: number | null;
  nodes_after: number | null;
  multipv_before: number;
  multipv_after: number;
  alternatives: CandidateMove[];
  is_engine_best: boolean;
  best_move_unique: boolean;
  wdl_estimated: boolean;
}

export interface AnalysisEvidence {
  position: {
    fen: string;
    ply: number;
    move_number: number;
    player_color: Color;
    phase: GamePhase;
  };
  played_move: { uci: string; san: string };
  engine: EngineEvidence;
  concepts: DetectedConcept[];
  decision_errors: DecisionError[];
  severity: Severity;
  board_context: Record<string, unknown>;
  move_history_san: string[];
}

export interface CriticalMoment {
  ply: number;
  move_number: number;
  player_color: Color;
  phase: GamePhase;
  severity: Severity;
  criticality_score: number;
  reasons: string[];
  one_liner_zh: string;
  fen: string;
  played_move_san: string;
  solution_uci: string | null;
  solution_san: string | null;
  evidence: AnalysisEvidence;
}

export interface MoveAssessment {
  ply: number;
  move_number: number;
  color: Color;
  san: string;
  uci: string;
  fen_before: string;
  fen_after: string;
  is_player_move: boolean;
  severity: Severity | null;
  expected_score_loss: number | null;
  evaluation_after: number | null;
  mate_after: number | null;
  /** 引擎推荐：每一手都有，不只是关键局面。只在 fen_before 里合法。 */
  best_move_san: string | null;
  best_move_uci: string | null;
  is_engine_best: boolean;
  evaluation_before: number | null;
  expected_score_before: number | null;
  /** 引擎推荐着法及其后续（第一个元素即 best_move_uci）。 */
  best_line_uci: string[];
  best_line_san: string[];
  /** 实战着法及其后续（第一个元素即本手 uci）。 */
  played_line_uci: string[];
  played_line_san: string[];
  concept_tags: string[];
  decision_error_tags: string[];
  is_critical: boolean;
}

export interface MoveCounts {
  best: number;
  excellent: number;
  good: number;
  inaccuracy: number;
  mistake: number;
  blunder: number;
}

export interface PhaseStats {
  phase: GamePhase;
  moves: number;
  problems: number;
  average_expected_score_loss: number;
}

export interface EngineMeta {
  engine_name: string;
  pass1_depth: number;
  pass1_nodes: number;
  pass2_depth: number;
  pass2_multipv: number;
  threads: number;
  hash_mb: number;
  positions_analyzed: number;
  cache_hits: number;
  elapsed_seconds: number;
  complete: boolean;
  warnings: string[];
}

export interface GameReview {
  game_id: string;
  white: string;
  black: string;
  result: string;
  player_color: Color;
  opening: string | null;
  headers: Record<string, string>;
  moves: MoveAssessment[];
  critical_moments: CriticalMoment[];
  counts: MoveCounts;
  average_expected_score_loss: number;
  phase_stats: PhaseStats[];
  engine: EngineMeta;
  llm_available: boolean;
  status: AnalysisStatus;
  warnings: string[];
  created_at: string | null;
}

export interface GameListItem {
  game_id: string;
  white: string;
  black: string;
  result: string;
  player_color: Color;
  opening: string | null;
  created_at: string | null;
  move_count: number;
  blunders: number;
  mistakes: number;
  inaccuracies: number;
  average_expected_score_loss: number;
}

export interface AnalysisJobStatus {
  job_id: string;
  game_id: string | null;
  status: AnalysisStatus;
  progress: number;
  message_zh: string;
  error: string | null;
  review: GameReview | null;
}

export interface LLMExplanation {
  summary: string;
  what_happened: string;
  why_it_matters: string;
  likely_human_error: string;
  better_thinking_process: string;
  general_lesson: string;
  best_move_explanation: string;
  concept_tags: string[];
  confidence: number;
}

export interface MomentExplanation {
  source: ExplanationSource;
  explanation: LLMExplanation;
  model: string | null;
  generated_at: string | null;
  validation_warnings: string[];
  grounded: boolean;
  cached: boolean;
}

export interface GameSummaryExplanation {
  summary: string;
  main_patterns: string[];
  practice_advice: string[];
  confidence: number;
}

export interface GameSummaryRecord {
  source: ExplanationSource;
  explanation: GameSummaryExplanation;
  model: string | null;
  generated_at: string | null;
  cached: boolean;
}

export interface ExampleMoment {
  game_id: string;
  ply: number;
  move_number: number;
  san: string;
  opponent: string;
  severity: Severity;
  one_liner_zh: string;
  fen: string;
  solution_san: string | null;
}

export interface RecurringWeakness {
  error_type: string;
  label_zh: string;
  event_count: number;
  share: number;
  games: number;
  average_expected_score_loss: number;
  severity_mix: Record<string, number>;
  confidence: string;
  statement_zh: string;
  examples: ExampleMoment[];
}

export interface PhaseBreakdown {
  phase: GamePhase;
  label_zh: string;
  events: number;
  share: number;
  average_expected_score_loss: number;
}

export interface ConceptFrequency {
  concept: string;
  label_zh: string;
  count: number;
  share: number;
}

export interface TrendPoint {
  game_id: string;
  created_at: string | null;
  average_expected_score_loss: number;
  problems: number;
  blunders: number;
  label: string;
}

export interface TrendSummary {
  available: boolean;
  statement_zh: string;
  direction: string;
  recent_average_loss: number | null;
  earlier_average_loss: number | null;
}

export interface ProfileSummary {
  total_games: number;
  total_player_moves: number;
  total_problems: number;
  blunders: number;
  mistakes: number;
  inaccuracies: number;
  average_expected_score_loss: number;
  weaknesses: RecurringWeakness[];
  phases: PhaseBreakdown[];
  top_concepts: ConceptFrequency[];
  trend: TrendSummary;
  trend_points: TrendPoint[];
  sample_size_note_zh: string;
  generated_at: string | null;
}

export interface EngineHealth {
  available: boolean;
  name: string | null;
  path: string | null;
  threads: number;
  hash_mb: number;
  error: string | null;
}

export interface LLMHealth {
  available: boolean;
  provider: string;
  model: string | null;
  base_url: string | null;
}

export interface LineStep {
  uci: string;
  san: string;
  fen_after: string;
  mover: Color;
}

export interface LineWalk {
  kind: "best" | "played";
  label_zh: string;
  start_fen: string;
  final_fen: string;
  steps: LineStep[];
  complete: boolean;
  truncated: boolean;
  ends_in_mate: boolean;
}

export interface MomentLines {
  ply: number;
  move_number: number;
  played_move_san: string;
  best_move_san: string | null;
  evaluation_before: number | null;
  expected_score_before: number | null;
  best: LineWalk;
  played: LineWalk;
}

export interface LLMTestResult {
  configured: boolean;
  ok: boolean;
  model: string | null;
  message_zh: string;
  detail: string | null;
}

export interface HealthResponse {
  status: string;
  version: string;
  engine: EngineHealth;
  llm: LLMHealth;
  database: string;
  pass1_depth: number;
  pass2_depth: number;
  max_critical_moments: number;
}

// ------------------------------------------------------------------- 题目训练

export type PuzzleKind = "mate" | "material";

export type PuzzleVerdict = "correct" | "also_good" | "inaccurate" | "wrong" | "unverified";

export interface Puzzle {
  id: string;
  game_id: string;
  ply: number;
  move_number: number;
  player_color: Color;
  phase: GamePhase;
  kind: PuzzleKind;
  fen: string;
  solution_uci: string;
  solution_san: string;
  solution_line_uci: string[];
  solution_line_san: string[];
  mate_in: number | null;
  material_gain: number | null;
  theme: string | null;
  theme_label_zh: string;
  played_san: string;
  severity: Severity;
  difficulty: string;
  concept_tags: string[];
  created_at: string | null;
}

export interface PuzzleDetail {
  puzzle: Puzzle;
  steps: LineStep[];
  opponent_replies: LineStep[];
  /** 题目局面下的全部合法着法（服务端用 python-chess 算的）。 */
  legal_moves: string[];
}

export interface PuzzleAttemptResult {
  puzzle_id: string;
  correct: boolean;
  played_uci: string | null;
  played_san: string | null;
  best_san: string | null;
  is_engine_move: boolean;
  graded_by: "engine" | "answer_only";
  verdict: PuzzleVerdict;
  verdict_zh: string;
  expected_score_loss: number | null;
  played_expected_score: number | null;
  best_expected_score: number | null;
  attempts: number;
  solved: number;
}

export interface PuzzleStats {
  total: number;
  mate: number;
  material: number;
  attempted: number;
  solved: number;
  solved_rate: number;
  by_theme: { theme: string | null; label_zh: string; count: number }[];
}
