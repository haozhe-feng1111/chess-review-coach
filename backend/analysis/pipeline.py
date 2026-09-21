"""The two-pass analysis pipeline.

Pass 1 sweeps every position cheaply (MultiPV=1) so that evaluation changes across the
whole game are known. Pass 2 spends real compute only on the positions that pass 1
flagged as critical (deeper search, MultiPV 3, alternative lines), and those deeper
numbers replace the shallow ones for the moves that matter.

Everything produced here is derived from engine output plus deterministic board facts —
no layer in this file makes a chess judgment of its own.

Perspective: every position is searched once, with the analyzed player as the point of
view. Severity is then reported per mover (the opponent's blunders are labelled as
theirs), which is why ``build_engine_evidence`` re-flips perspective for their moves.
"""

import logging
from dataclasses import dataclass, field
from time import monotonic
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import chess

from analysis import evidence as evidence_builder
from analysis.critical import CriticalityAssessment, assess_criticality, select_review_moments
from analysis.evidence import build_full_evidence, candidates_in_pov
from analysis.features import build_board_context
from analysis.phase import DEFAULT_PHASE_CLASSIFIER, PhaseClassifier
from analysis.thresholds import THRESHOLDS, AnalysisThresholds
from coaching.taxonomy import TaxonomyContext, classify_decision_errors
from concepts.base import DetectionContext
from concepts.registry import detect_concepts
from engine.cache import AnalysisCache, NullCache, cache_key
from engine.errors import EngineError, EngineTimeoutError
from engine.scores import display_pawns
from engine.stockfish import StockfishEngine
from models.enums import AnalysisStatus, Color, GamePhase, Severity
from models.evidence import DecisionError, DetectedConcept, EngineEvidence, PositionEval
from models.game import ParsedGame, ParsedMove
from models.review import (
    CriticalMoment,
    EngineMeta,
    GameReview,
    MoveAssessment,
    MoveCounts,
    PhaseStats,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float, str], None]


@dataclass
class PipelineConfig:
    """Engine budget for one game; mirrors the environment settings."""

    pass1_depth: int = 12
    pass1_nodes: int = 0
    pass2_depth: int = 18
    pass2_multipv: int = 3
    pass2_nodes: int = 0
    position_timeout: float = 25.0
    max_critical_moments: int = 5
    deep: bool = True
    threads: int = 1
    hash_mb: int = 64
    #: How many candidates pass 2 analyses relative to how many are finally shown.
    pass2_candidate_multiplier: int = 2
    cache_enabled: bool = True


@dataclass
class _PositionSlot:
    """One position of the game plus the engine data gathered for it."""

    board: chess.Board
    shallow: Optional[PositionEval] = None
    deep: Optional[PositionEval] = None

    @property
    def best(self) -> Optional[PositionEval]:
        return self.deep or self.shallow


@dataclass
class _MoveSlot:
    """One played move with everything computed for it so far."""

    move: ParsedMove
    before: int
    after: int
    is_player_move: bool
    mover: Color
    evidence: Optional[EngineEvidence] = None
    severity: Optional[Severity] = None
    concepts: List[DetectedConcept] = field(default_factory=list)
    errors: List[DecisionError] = field(default_factory=list)
    phase: GamePhase = GamePhase.MIDDLEGAME
    criticality: float = 0.0
    reasons: List[object] = field(default_factory=list)


class GameAnalyzer:
    def __init__(
        self,
        engine: StockfishEngine,
        cache: Optional[AnalysisCache] = None,
        config: Optional[PipelineConfig] = None,
        thresholds: AnalysisThresholds = THRESHOLDS,
        phase_classifier: Optional[PhaseClassifier] = None,
        progress: Optional[ProgressCallback] = None,
    ) -> None:
        self._engine = engine
        # ``cache or NullCache()`` would be wrong here: an *empty* cache object with a
        # __len__ is falsy, which would silently disable caching.
        self._cache = cache if cache is not None else NullCache()
        self._config = config or PipelineConfig()
        self._thresholds = thresholds
        self._phase = phase_classifier or DEFAULT_PHASE_CLASSIFIER
        self._progress = progress
        self._pov_color = Color.WHITE
        self._cache_hits = 0
        self._warnings: List[str] = []
        self._positions_analyzed = 0

    # ------------------------------------------------------------------ public API

    def analyze(self, game: ParsedGame, game_id: str) -> GameReview:
        started = monotonic()
        self._pov_color = game.player_color
        positions, move_slots = self._build_slots(game)
        self._notify(0.02, "准备分析…")

        self._pass_one(positions)
        self._assemble_and_classify(positions, move_slots, deep=False)
        self._notify(0.68, "定位关键局面…")

        if self._config.deep:
            self._pass_two(positions, move_slots)
            self._assemble_and_classify(positions, move_slots, deep=True)

        review = self._build_review(
            game=game,
            game_id=game_id,
            positions=positions,
            move_slots=move_slots,
            elapsed=monotonic() - started,
        )
        self._notify(1.0, "分析完成")
        return review

    # -------------------------------------------------------------- slot building

    def _build_slots(self, game: ParsedGame) -> Tuple[List[_PositionSlot], List[_MoveSlot]]:
        """Replay the PGN once, keeping a board (with history) for every position."""
        board = chess.Board(game.initial_fen) if game.initial_fen else chess.Board()
        positions: List[_PositionSlot] = [_PositionSlot(board=board.copy())]
        slots: List[_MoveSlot] = []

        for parsed_move in game.moves:
            before_index = len(positions) - 1
            move = next((m for m in board.legal_moves if m.uci() == parsed_move.uci), None)
            if move is None:  # pragma: no cover - parse_pgn already validated legality
                raise EngineError("PGN move is not legal on the replayed board")
            board.push(move)
            positions.append(_PositionSlot(board=board.copy()))
            slots.append(
                _MoveSlot(
                    move=parsed_move,
                    before=before_index,
                    after=before_index + 1,
                    is_player_move=parsed_move.color == game.player_color,
                    mover=parsed_move.color,
                )
            )
        for slot in slots:
            slot.phase = self._phase.classify(positions[slot.before].board, slot.move.move_number)
        return positions, slots

    # ------------------------------------------------------------------- pass one

    def _pass_one(self, positions: List[_PositionSlot]) -> None:
        total = len(positions)
        for index, slot in enumerate(positions):
            slot.shallow = self._analyse_position(
                slot.board,
                depth=self._config.pass1_depth,
                nodes=self._config.pass1_nodes,
                multipv=1,
            )
            if index % 6 == 0:
                self._notify(0.05 + 0.6 * (index / max(1, total)), "快速扫描全部局面…")

    # ------------------------------------------------------------------- pass two

    def _pass_two(self, positions: List[_PositionSlot], slots: List[_MoveSlot]) -> None:
        candidates = self._critical_candidates(slots)
        limit = max(1, self._config.max_critical_moments * self._config.pass2_candidate_multiplier)
        selected = candidates[:limit]
        if not selected:
            return

        for done, slot in enumerate(selected):
            positions[slot.before].deep = self._analyse_position(
                positions[slot.before].board,
                depth=self._config.pass2_depth,
                nodes=self._config.pass2_nodes,
                multipv=self._config.pass2_multipv,
            )
            positions[slot.after].deep = self._analyse_position(
                positions[slot.after].board,
                depth=self._config.pass2_depth,
                nodes=self._config.pass2_nodes,
                multipv=1,
            )
            self._notify(
                0.70 + 0.22 * ((done + 1) / len(selected)),
                "深入分析关键局面 {}/{}…".format(done + 1, len(selected)),
            )

    # ---------------------------------------------------- evidence + classification

    def _assemble_and_classify(
        self, positions: List[_PositionSlot], slots: List[_MoveSlot], deep: bool
    ) -> None:
        for slot in slots:
            before_slot = positions[slot.before]
            after_slot = positions[slot.after]
            before_eval = before_slot.best if deep else before_slot.shallow
            after_eval = after_slot.best if deep else after_slot.shallow
            deep_eval = before_slot.deep if deep else None

            played_move = self._played_move(before_slot.board, slot)
            evidence = evidence_builder.build_engine_evidence(
                board_before=before_slot.board,
                board_after=after_slot.board,
                before_eval=before_eval,
                after_eval=after_eval,
                played_move=played_move,
                played_san=slot.move.san,
                pov=slot.mover,
                deep_eval=deep_eval,
                thresholds=self._thresholds,
            )
            if evidence is None:
                if slot.evidence is None:
                    self._warn(
                        "第 {} 手（{}）缺少引擎数据，未计入评估。".format(
                            slot.move.move_number, slot.move.san
                        )
                    )
                continue

            slot.evidence = evidence
            slot.severity = self._thresholds.severity.classify(
                evidence.expected_score_loss, evidence.is_engine_best
            )
            assessment = assess_criticality(evidence, slot.severity, self._thresholds)
            slot.criticality = assessment.score
            slot.reasons = list(assessment.reasons)

            if not slot.is_player_move:
                # Concepts and the decision taxonomy describe the analyzed player's
                # decisions only; opponent moves still appear in the move list with their
                # own severity.
                continue
            if not slot.severity.is_problem:
                # A good move gets a severity label and nothing else. Running the
                # detectors here only produces noise: a low-confidence "king safety
                # worsened" tag on a move the engine rates as best actively misleads.
                continue

            detection_context = DetectionContext(
                board_before=before_slot.board,
                board_after=after_slot.board,
                played_move=played_move,
                played_san=slot.move.san,
                player_color=self._pov_color,
                evidence=evidence,
                severity=slot.severity,
                phase=slot.phase,
                move_number=slot.move.move_number,
                move_history=self._move_history_before(slots, slot),
                thresholds=self._thresholds.detection,
            )
            slot.concepts = detect_concepts(detection_context)
            slot.errors = classify_decision_errors(
                TaxonomyContext(
                    evidence=evidence,
                    concepts=slot.concepts,
                    severity=slot.severity,
                    phase=slot.phase,
                    board_context=build_board_context(before_slot.board, self._pov_color),
                    played_san=slot.move.san,
                    move_number=slot.move.move_number,
                    thresholds=self._thresholds,
                )
            )

    # ------------------------------------------------------------------- review

    def _build_review(
        self,
        game: ParsedGame,
        game_id: str,
        positions: List[_PositionSlot],
        move_slots: List[_MoveSlot],
        elapsed: float,
    ) -> GameReview:
        assessments = [
            self._to_assessment(slot, positions) for slot in move_slots
        ]

        candidates = [
            (
                slot.move.ply,
                CriticalityAssessment(score=slot.criticality, reasons=list(slot.reasons)),
                slot.severity,
            )
            for slot in move_slots
            if slot.is_player_move and slot.severity is not None and slot.evidence is not None
        ]
        selected = select_review_moments(candidates, self._config.max_critical_moments)
        selected_plies = {ply for ply, _assessment, _severity in selected}
        for assessment in assessments:
            assessment.is_critical = assessment.ply in selected_plies

        moments: List[CriticalMoment] = []
        for ply, _assessment, _severity in selected:
            slot = next(s for s in move_slots if s.move.ply == ply)
            moments.append(self._to_critical_moment(slot, positions, move_slots))

        losses = [
            slot.evidence.expected_score_loss
            for slot in move_slots
            if slot.is_player_move and slot.evidence is not None
        ]

        return GameReview(
            game_id=game_id,
            white=game.white,
            black=game.black,
            result=game.result,
            player_color=game.player_color,
            opening=game.opening,
            headers=game.headers,
            moves=assessments,
            critical_moments=moments,
            counts=self._counts(move_slots),
            average_expected_score_loss=round(sum(losses) / len(losses), 4) if losses else 0.0,
            phase_stats=self._phase_stats(move_slots),
            engine=EngineMeta(
                engine_name=self._engine.name,
                pass1_depth=self._config.pass1_depth,
                pass1_nodes=self._config.pass1_nodes,
                pass2_depth=self._config.pass2_depth if self._config.deep else 0,
                pass2_multipv=self._config.pass2_multipv if self._config.deep else 0,
                threads=self._config.threads,
                hash_mb=self._config.hash_mb,
                positions_analyzed=self._positions_analyzed,
                cache_hits=self._cache_hits,
                elapsed_seconds=round(elapsed, 2),
                complete=not self._warnings,
                warnings=list(dict.fromkeys(self._warnings)),
            ),
            status=AnalysisStatus.COMPLETED,
            warnings=list(dict.fromkeys(self._warnings + list(game.warnings))),
        )

    def _to_assessment(
        self, slot: _MoveSlot, positions: List[_PositionSlot]
    ) -> MoveAssessment:
        evaluation_after: Optional[float] = None
        mate_after: Optional[int] = None
        after_view = candidates_in_pov(positions[slot.after].best, self._pov_color)
        if after_view:
            evaluation_after = display_pawns(after_view[0].cp, after_view[0].mate)
            mate_after = after_view[0].mate
        elif slot.evidence is not None and slot.evidence.evaluation_after is not None:
            # Terminal position (this move ended the game): the engine has no PV, but the
            # evidence already carries the final evaluation from the mover's point of view.
            sign = 1.0 if slot.mover == self._pov_color else -1.0
            evaluation_after = sign * slot.evidence.evaluation_after
            mate_after = (
                None
                if slot.evidence.mate_after is None
                else int(sign * slot.evidence.mate_after)
            )

        engine = slot.evidence
        return MoveAssessment(
            ply=slot.move.ply,
            move_number=slot.move.move_number,
            color=slot.move.color,
            san=slot.move.san,
            uci=slot.move.uci,
            fen_before=slot.move.fen_before,
            fen_after=slot.move.fen_after,
            is_player_move=slot.is_player_move,
            severity=slot.severity,
            expected_score_loss=(
                round(slot.evidence.expected_score_loss, 4) if slot.evidence else None
            ),
            evaluation_after=evaluation_after,
            mate_after=mate_after,
            # 引擎推荐对每一手都保留：只有关键局面才会展开解释，但"应该走什么"人人都有。
            best_move_san=engine.best_move_san if engine else None,
            best_move_uci=engine.best_move_uci if engine else None,
            is_engine_best=bool(engine.is_engine_best) if engine else False,
            evaluation_before=engine.evaluation_before if engine else None,
            expected_score_before=(
                round(engine.expected_score_before, 4) if engine else None
            ),
            # 引擎 PV 保存时已经截断到 PV_MAX_PLIES，这里直接带上，前端就能逐步演示。
            best_line_uci=list(engine.best_line_uci) if engine else [],
            best_line_san=list(engine.best_line_san) if engine else [],
            played_line_uci=list(engine.played_line_uci) if engine else [],
            played_line_san=list(engine.played_line_san) if engine else [],
            concept_tags=[concept.type for concept in slot.concepts],
            decision_error_tags=[error.type for error in slot.errors],
        )

    def _to_critical_moment(
        self,
        slot: _MoveSlot,
        positions: List[_PositionSlot],
        move_slots: List[_MoveSlot],
    ) -> CriticalMoment:
        assert slot.evidence is not None and slot.severity is not None
        before_board = positions[slot.before].board
        return CriticalMoment(
            ply=slot.move.ply,
            move_number=slot.move.move_number,
            player_color=slot.mover,
            phase=slot.phase,
            severity=slot.severity,
            criticality_score=round(slot.criticality, 4),
            reasons=list(slot.reasons),
            one_liner_zh="",
            fen=slot.move.fen_before,
            played_move_san=slot.move.san,
            solution_uci=slot.evidence.best_move_uci,
            solution_san=slot.evidence.best_move_san,
            evidence=build_full_evidence(
                position_fen=slot.move.fen_before,
                ply=slot.move.ply,
                move_number=slot.move.move_number,
                player_color=slot.mover,
                phase=slot.phase,
                played_move_uci=slot.move.uci,
                played_san=slot.move.san,
                engine=slot.evidence,
                concepts=slot.concepts,
                errors=slot.errors,
                board_context=build_board_context(before_board, slot.mover),
                move_history_san=[
                    s.move.san for s in move_slots if s.move.ply < slot.move.ply
                ],
                severity=slot.severity,
            ),
        )

    # -------------------------------------------------------------------- helpers

    def _analyse_position(
        self, board: chess.Board, depth: int, nodes: int, multipv: int
    ) -> Optional[PositionEval]:
        key = cache_key(
            fen=board.fen(),
            engine_name=self._engine.name,
            depth=depth,
            nodes=nodes,
            multipv=multipv,
            threads=self._config.threads,
            hash_mb=self._config.hash_mb,
            pov=self._pov_color.value,
        )
        cached = self._cache.get(key) if self._config.cache_enabled else None
        if cached is not None:
            self._cache_hits += 1
            return cached

        try:
            result = self._engine.analyse(
                board,
                pov_color=self._pov_color,
                depth=depth,
                nodes=nodes,
                multipv=multipv,
                timeout=self._config.position_timeout,
            )
        except EngineTimeoutError as exc:
            self._warn("某个局面分析超时（{}），已跳过该局面。".format(exc.detail or "timeout"))
            return None
        except EngineError as exc:
            self._warn("引擎错误：{}".format(exc.message))
            return None

        self._positions_analyzed += 1
        if self._config.cache_enabled:
            self._cache.put(key, result)
        return result

    def _critical_candidates(self, slots: List[_MoveSlot]) -> List[_MoveSlot]:
        candidates = [
            slot
            for slot in slots
            if slot.is_player_move
            and slot.severity is not None
            and slot.severity.is_problem
            and slot.evidence is not None
        ]
        candidates.sort(key=lambda slot: -slot.criticality)
        return candidates

    @staticmethod
    def _played_move(board: chess.Board, slot: _MoveSlot) -> chess.Move:
        for move in board.legal_moves:
            if move.uci() == slot.move.uci:
                return move
        raise EngineError("move {} is not legal in the recorded position".format(slot.move.uci))

    @staticmethod
    def _move_history_before(slots: List[_MoveSlot], target: _MoveSlot):
        return [(slot.mover, slot.move.san) for slot in slots if slot.move.ply < target.move.ply]

    def _counts(self, slots: List[_MoveSlot]) -> MoveCounts:
        counts = MoveCounts()
        for slot in slots:
            if not slot.is_player_move or slot.severity is None:
                continue
            field_name = slot.severity.value
            setattr(counts, field_name, getattr(counts, field_name) + 1)
        return counts

    def _phase_stats(self, slots: List[_MoveSlot]) -> List[PhaseStats]:
        stats: Dict[GamePhase, PhaseStats] = {
            phase: PhaseStats(phase=phase) for phase in GamePhase
        }
        for slot in slots:
            if not slot.is_player_move or slot.evidence is None:
                continue
            entry = stats[slot.phase]
            entry.moves += 1
            entry.average_expected_score_loss += slot.evidence.expected_score_loss
            if slot.severity is not None and slot.severity.is_problem:
                entry.problems += 1
        result: List[PhaseStats] = []
        for phase in GamePhase:
            entry = stats[phase]
            if entry.moves:
                entry.average_expected_score_loss = round(
                    entry.average_expected_score_loss / entry.moves, 4
                )
            result.append(entry)
        return result

    def _warn(self, message: str) -> None:
        if message not in self._warnings:
            logger.warning(message)
            self._warnings.append(message)

    def _notify(self, progress: float, message: str) -> None:
        if self._progress is not None:
            try:
                self._progress(min(1.0, max(0.0, progress)), message)
            except Exception:  # pragma: no cover - progress must never break analysis
                logger.debug("progress callback failed", exc_info=True)
