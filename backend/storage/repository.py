"""Persistence queries.

Everything the API needs to read or write lives here, so route handlers stay thin and
the profile aggregation gets plain, DB-free inputs (``fetch_*`` returns dictionaries,
the statistics live in ``analysis/profile.py``).
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session, selectinload

from models.enums import DecisionErrorType, Severity
from models.profile import ExampleMoment
from models.puzzle import Puzzle, PuzzleAttemptResult, PuzzleStats
from models.review import GameListItem, GameReview
from storage.models import (
    AnalysisJob,
    CriticalPosition,
    DetectedConceptRow,
    Game,
    MistakeEvent,
    MoveAnalysis,
)

logger = logging.getLogger(__name__)


def make_game_id(pgn: str, player_color: str) -> str:
    """Deterministic id: re-importing the same PGN for the same side is the same game."""
    material = "{}|{}".format(_normalize_pgn(pgn), player_color)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def _normalize_pgn(pgn: str) -> str:
    return "\n".join(line.strip() for line in pgn.strip().splitlines() if line.strip())


# --------------------------------------------------------------------------- write


def save_review(session: Session, review: GameReview, pgn: str) -> Game:
    """Persist a completed review (idempotent: replaces any previous analysis)."""
    game_id = review.game_id
    existing = session.get(Game, game_id)
    if existing is not None:
        session.execute(delete(MistakeEvent).where(MistakeEvent.game_id == game_id))
        session.execute(delete(MoveAnalysis).where(MoveAnalysis.game_id == game_id))
        session.execute(delete(CriticalPosition).where(CriticalPosition.game_id == game_id))
        session.delete(existing)
        session.flush()

    counts = review.counts
    game = Game(
        id=game_id,
        white=review.white,
        black=review.black,
        result=review.result,
        player_color=review.player_color.value,
        opening=review.opening,
        pgn=pgn,
        headers=review.headers,
        move_count=len(review.moves),
        player_move_count=sum(1 for move in review.moves if move.is_player_move),
        blunders=counts.blunder,
        mistakes=counts.mistake,
        inaccuracies=counts.inaccuracy,
        critical_count=len(review.critical_moments),
        average_loss=review.average_expected_score_loss,
        engine_name=review.engine.engine_name,
        analysis_seconds=review.engine.elapsed_seconds,
        status=review.status.value,
        warnings=review.warnings,
        review_json=review.model_dump(mode="json"),
        created_at=review.created_at or datetime.utcnow(),
    )
    session.add(game)

    phase_by_ply = {move.ply: _phase_for(review, move.ply) for move in review.moves}
    concept_by_ply = {
        moment.ply: moment.evidence.concepts for moment in review.critical_moments
    }
    error_by_ply = {
        moment.ply: moment.evidence.decision_errors for moment in review.critical_moments
    }

    for move in review.moves:
        session.add(
            MoveAnalysis(
                game_id=game_id,
                ply=move.ply,
                move_number=move.move_number,
                color=move.color.value,
                san=move.san,
                uci=move.uci,
                fen_before=move.fen_before,
                fen_after=move.fen_after,
                is_player_move=move.is_player_move,
                severity=move.severity.value if move.severity else None,
                expected_score_loss=move.expected_score_loss,
                evaluation_after=move.evaluation_after,
                phase=phase_by_ply.get(move.ply),
                concept_tags=[tag.value for tag in move.concept_tags],
                decision_error_tags=[tag.value for tag in move.decision_error_tags],
                is_critical=move.is_critical,
            )
        )

    for moment in review.critical_moments:
        session.add(
            CriticalPosition(
                game_id=game_id,
                ply=moment.ply,
                move_number=moment.move_number,
                phase=moment.phase.value,
                severity=moment.severity.value,
                criticality_score=moment.criticality_score,
                reasons=[reason.value for reason in moment.reasons],
                fen=moment.fen,
                played_move_san=moment.played_move_san,
                solution_uci=moment.solution_uci,
                solution_san=moment.solution_san,
                one_liner_zh=moment.one_liner_zh,
                evidence_json=moment.evidence.model_dump(mode="json"),
            )
        )

    for move in review.moves:
        if not (move.is_player_move and move.severity is not None and move.severity.is_problem):
            continue
        moment = next((m for m in review.critical_moments if m.ply == move.ply), None)
        errors = error_by_ply.get(move.ply, [])
        primary = _primary_error(errors)
        event = MistakeEvent(
            game_id=game_id,
            ply=move.ply,
            move_number=move.move_number,
            player_color=move.color.value,
            phase=(moment.phase.value if moment else phase_by_ply.get(move.ply) or "middlegame"),
            severity=move.severity.value,
            expected_score_loss=move.expected_score_loss or 0.0,
            evaluation_before=(
                moment.evidence.engine.evaluation_before if moment else None
            ),
            evaluation_after=move.evaluation_after,
            san=move.san,
            one_liner_zh=moment.one_liner_zh if moment else "",
            primary_error=primary.type.value,
            primary_error_confidence=primary.confidence,
            decision_error_tags=[tag.value for tag in move.decision_error_tags],
            concept_tags=[tag.value for tag in move.concept_tags],
            is_critical=move.is_critical,
            created_at=review.created_at or datetime.utcnow(),
        )
        session.add(event)
        session.flush()
        for concept in concept_by_ply.get(move.ply, []):
            session.add(
                DetectedConceptRow(
                    mistake_event_id=event.id,
                    concept_type=concept.type.value,
                    confidence=concept.confidence,
                    pieces=concept.pieces,
                    squares=concept.squares,
                    evidence=concept.evidence,
                    meta=concept.metadata,
                )
            )

    session.flush()
    return game


def _phase_for(review: GameReview, ply: int) -> Optional[str]:
    moment = next((m for m in review.critical_moments if m.ply == ply), None)
    return moment.phase.value if moment else None


def _primary_error(errors):
    from models.evidence import DecisionError

    if not errors:
        return DecisionError(
            type=DecisionErrorType.UNKNOWN,
            confidence=0.0,
            rationale="no decision-error rule applied",
        )
    return max(errors, key=lambda error: error.confidence)


# ---------------------------------------------------------------------------- read


def get_game(session: Session, game_id: str) -> Optional[Game]:
    return session.get(Game, game_id)


def get_review(session: Session, game_id: str) -> Optional[GameReview]:
    game = session.get(Game, game_id)
    if game is None or not game.review_json:
        return None
    review = GameReview.model_validate(game.review_json)
    review.created_at = game.created_at
    return review

def list_games(session: Session, limit: int = 50, offset: int = 0) -> List[GameListItem]:
    rows = session.execute(
        select(Game).order_by(Game.created_at.desc()).limit(limit).offset(offset)
    ).scalars()
    return [
        GameListItem(
            game_id=game.id,
            white=game.white,
            black=game.black,
            result=game.result,
            player_color=game.player_color,
            opening=game.opening,
            created_at=game.created_at,
            move_count=game.move_count or 0,
            blunders=game.blunders or 0,
            mistakes=game.mistakes or 0,
            inaccuracies=game.inaccuracies or 0,
            average_expected_score_loss=game.average_loss or 0.0,
        )
        for game in rows
    ]


def delete_game(session: Session, game_id: str) -> bool:
    game = session.get(Game, game_id)
    if game is None:
        return False
    session.delete(game)
    return True


def known_player_names(session: Session, limit: int = 20) -> List[str]:
    """Names the user has played as, used to auto-detect the side on import."""
    names: List[str] = []
    for white, black in session.execute(
        select(Game.white, Game.black).order_by(Game.created_at.desc()).limit(limit)
    ):
        if white:
            names.append(str(white))
        if black:
            names.append(str(black))
    seen = set()
    unique = []
    for name in names:
        lowered = name.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique.append(name)
    return unique


# ------------------------------------------------------------------ profile inputs


@dataclass
class ProfileInput:
    """Plain data the profile builder turns into statistics."""

    total_games: int = 0
    total_player_moves: int = 0
    average_loss: float = 0.0
    severity_counts: Dict[str, int] = field(default_factory=dict)
    mistake_events: List[Dict[str, object]] = field(default_factory=list)
    phase_counts: List[Dict[str, object]] = field(default_factory=list)
    concept_counts: List[Dict[str, object]] = field(default_factory=list)
    game_trend: List[Dict[str, object]] = field(default_factory=list)


def collect_profile_input(session: Session) -> ProfileInput:
    data = ProfileInput()

    data.total_games = int(session.execute(select(func.count(Game.id))).scalar_one() or 0)
    data.total_player_moves = int(
        session.execute(
            select(func.count(MoveAnalysis.id)).where(MoveAnalysis.is_player_move.is_(True))
        ).scalar_one()
        or 0
    )
    data.average_loss = float(
        session.execute(
            select(func.avg(MoveAnalysis.expected_score_loss)).where(
                MoveAnalysis.is_player_move.is_(True)
            )
        ).scalar_one()
        or 0.0
    )
    for severity, count in session.execute(
        select(MistakeEvent.severity, func.count(MistakeEvent.id)).group_by(MistakeEvent.severity)
    ):
        data.severity_counts[str(severity)] = int(count)

    events = session.execute(
        select(MistakeEvent)
        .options(selectinload(MistakeEvent.concepts))
        .order_by(MistakeEvent.created_at.desc(), MistakeEvent.expected_score_loss.desc())
    ).scalars()

    games_by_id = {game.id: game for game in session.execute(select(Game)).scalars()}
    # Prefetch the board/answer for every critical position in one query instead of
    # hitting the database once per mistake event.
    criticals: Dict[tuple, Dict[str, Optional[str]]] = {}
    for game_id, ply, fen, solution in session.execute(
        select(
            CriticalPosition.game_id,
            CriticalPosition.ply,
            CriticalPosition.fen,
            CriticalPosition.solution_san,
        )
    ):
        criticals[(str(game_id), int(ply))] = {
            "fen": str(fen or ""),
            "solution_san": str(solution) if solution else None,
        }

    for event in events:
        game = games_by_id.get(event.game_id)
        data.mistake_events.append(
            {
                "game_id": event.game_id,
                "ply": event.ply,
                "move_number": event.move_number,
                "san": event.san,
                "severity": event.severity,
                "phase": event.phase,
                "expected_score_loss": event.expected_score_loss or 0.0,
                "primary_error": event.primary_error,
                "primary_error_confidence": event.primary_error_confidence or 0.0,
                "decision_error_tags": list(event.decision_error_tags or []),
                "concept_tags": list(event.concept_tags or []),
                "is_critical": bool(event.is_critical),
                "created_at": event.created_at,
                "one_liner_zh": event.one_liner_zh or "",
                "game_created_at": game.created_at if game else None,
                "opponent": _opponent_name(game, event.player_color) if game else "",
                "fen": criticals.get((event.game_id, event.ply), {}).get("fen", ""),
                "solution_san": criticals.get((event.game_id, event.ply), {}).get(
                    "solution_san"
                ),
            }
        )

    for phase, count, average in session.execute(
        select(
            MistakeEvent.phase,
            func.count(MistakeEvent.id),
            func.avg(MistakeEvent.expected_score_loss),
        ).group_by(MistakeEvent.phase)
    ):
        data.phase_counts.append(
            {
                "phase": str(phase),
                "events": int(count),
                "average_loss": float(average or 0.0),
            }
        )

    concept_counts: Dict[str, int] = {}
    for concept_type, count in session.execute(
        select(DetectedConceptRow.concept_type, func.count(DetectedConceptRow.id)).group_by(
            DetectedConceptRow.concept_type
        )
    ):
        concept_counts[str(concept_type)] = int(count)
    data.concept_counts = [
        {"concept": key, "count": value}
        for key, value in sorted(concept_counts.items(), key=lambda item: -item[1])
    ]

    for game in session.execute(select(Game).order_by(Game.created_at.asc())).scalars():
        data.game_trend.append(
            {
                "game_id": game.id,
                "created_at": game.created_at,
                "average_loss": game.average_loss or 0.0,
                "problems": (game.blunders or 0) + (game.mistakes or 0) + (game.inaccuracies or 0),
                "blunders": game.blunders or 0,
                "label": "{} vs {}".format(
                    game.white if game.player_color == "white" else game.black,
                    game.black if game.player_color == "white" else game.white,
                ),
            }
        )
    return data


def _opponent_name(game: Optional[Game], player_color: str) -> str:
    if game is None:
        return ""
    return game.black if player_color == "white" else game.white


def example_moment_from_row(row: Dict[str, object]) -> ExampleMoment:
    return ExampleMoment(
        game_id=str(row.get("game_id", "")),
        ply=int(row.get("ply", 0) or 0),
        move_number=int(row.get("move_number", 0) or 0),
        san=str(row.get("san", "")),
        opponent=str(row.get("opponent", "")),
        severity=Severity(str(row.get("severity", "mistake"))),
        one_liner_zh=str(row.get("one_liner_zh", "")),
        fen=str(row.get("fen", "")),
        solution_san=(str(row["solution_san"]) if row.get("solution_san") else None),
    )


# ------------------------------------------------------------------------ puzzles


def save_puzzles(session: Session, puzzles: List[Puzzle], game_id: str) -> int:
    """保存一盘棋提取出的题目（先清掉这盘棋的旧题目，保证可重复运行）。

    同一个**局面**只收集一次：不同对局里出现相同局面时，保留最早收集到的那条，
    避免练习时反复遇到同一道题。
    """
    from storage.models import PuzzleRow

    session.execute(delete(PuzzleRow).where(PuzzleRow.game_id == game_id))

    existing_fens = {
        row for (row,) in session.execute(select(PuzzleRow.fen_key)).all()
    }
    saved = 0
    for puzzle in puzzles:
        key = puzzle_fen_key(puzzle.fen)
        if key in existing_fens:
            continue
        existing_fens.add(key)
        session.add(
            PuzzleRow(
                id=puzzle.id,
                game_id=puzzle.game_id,
                ply=puzzle.ply,
                move_number=puzzle.move_number,
                player_color=puzzle.player_color.value,
                phase=puzzle.phase.value,
                kind=puzzle.kind.value,
                fen=puzzle.fen,
                fen_key=key,
                solution_uci=puzzle.solution_uci,
                solution_san=puzzle.solution_san,
                solution_line_uci=puzzle.solution_line_uci,
                solution_line_san=puzzle.solution_line_san,
                mate_in=puzzle.mate_in,
                material_gain=puzzle.material_gain,
                theme=puzzle.theme.value if puzzle.theme else None,
                theme_label_zh=puzzle.theme_label_zh,
                played_san=puzzle.played_san,
                severity=puzzle.severity.value,
                difficulty=puzzle.difficulty,
                concept_tags=[tag.value for tag in puzzle.concept_tags],
                created_at=puzzle.created_at or datetime.utcnow(),
            )
        )
        saved += 1
    session.flush()
    return saved


def puzzle_fen_key(fen: str) -> str:
    """局面的身份：忽略半回合计数与回合数，只比较棋盘、走子方、易位、吃过路兵。"""
    parts = fen.split()
    return " ".join(parts[:4]) if len(parts) >= 4 else fen


def _row_to_puzzle(row) -> Puzzle:
    from models.enums import Color, ConceptType, GamePhase, PuzzleKind, Severity

    return Puzzle(
        id=row.id,
        game_id=row.game_id,
        ply=row.ply,
        move_number=row.move_number,
        player_color=Color(row.player_color),
        phase=GamePhase(row.phase),
        kind=PuzzleKind(row.kind),
        fen=row.fen,
        solution_uci=row.solution_uci,
        solution_san=row.solution_san,
        solution_line_uci=list(row.solution_line_uci or []),
        solution_line_san=list(row.solution_line_san or []),
        mate_in=row.mate_in,
        material_gain=row.material_gain,
        theme=ConceptType(row.theme) if row.theme else None,
        theme_label_zh=row.theme_label_zh or "未分类",
        played_san=row.played_san or "",
        severity=Severity(row.severity),
        difficulty=row.difficulty or "medium",
        concept_tags=[ConceptType(value) for value in (row.concept_tags or [])],
        created_at=row.created_at,
    )


def list_puzzles(
    session: Session,
    limit: int = 50,
    offset: int = 0,
    kind: Optional[str] = None,
    theme: Optional[str] = None,
    game_id: Optional[str] = None,
) -> List[Puzzle]:
    from storage.models import PuzzleRow

    query = select(PuzzleRow).order_by(PuzzleRow.created_at.desc(), PuzzleRow.ply)
    if kind:
        query = query.where(PuzzleRow.kind == kind)
    if theme:
        query = query.where(PuzzleRow.theme == theme)
    if game_id:
        query = query.where(PuzzleRow.game_id == game_id)
    rows = session.execute(query.limit(limit).offset(offset)).scalars()
    return [_row_to_puzzle(row) for row in rows]


def get_puzzle(session: Session, puzzle_id: str) -> Optional[Puzzle]:
    from storage.models import PuzzleRow

    row = session.get(PuzzleRow, puzzle_id)
    return _row_to_puzzle(row) if row else None


def record_attempt(
    session: Session, puzzle_id: str, correct: bool, played_uci: Optional[str]
) -> Optional[PuzzleAttemptResult]:
    from storage.models import PuzzleAttemptRow, PuzzleRow

    if session.get(PuzzleRow, puzzle_id) is None:
        return None
    session.add(
        PuzzleAttemptRow(puzzle_id=puzzle_id, correct=correct, played_uci=played_uci)
    )
    session.flush()
    total, solved = session.execute(
        select(func.count(PuzzleAttemptRow.id), func.sum(case((PuzzleAttemptRow.correct.is_(True), 1), else_=0)))
        .where(PuzzleAttemptRow.puzzle_id == puzzle_id)
    ).one()
    return PuzzleAttemptResult(
        puzzle_id=puzzle_id,
        correct=correct,
        played_uci=played_uci,
        attempts=int(total or 0),
        solved=int(solved or 0),
    )


def puzzle_stats(session: Session) -> PuzzleStats:
    from storage.models import PuzzleAttemptRow, PuzzleRow

    total = int(session.execute(select(func.count(PuzzleRow.id))).scalar_one() or 0)
    mate = int(
        session.execute(
            select(func.count(PuzzleRow.id)).where(PuzzleRow.kind == "mate")
        ).scalar_one()
        or 0
    )
    attempted = int(
        session.execute(select(func.count(func.distinct(PuzzleAttemptRow.puzzle_id)))).scalar_one() or 0
    )
    solved = int(
        session.execute(
            select(func.count(func.distinct(PuzzleAttemptRow.puzzle_id))).where(
                PuzzleAttemptRow.correct.is_(True)
            )
        ).scalar_one()
        or 0
    )
    by_theme = [
        {"theme": str(theme), "label_zh": str(label), "count": int(count)}
        for theme, label, count in session.execute(
            select(PuzzleRow.theme, PuzzleRow.theme_label_zh, func.count(PuzzleRow.id)).group_by(
                PuzzleRow.theme, PuzzleRow.theme_label_zh
            )
        )
    ]
    by_theme.sort(key=lambda item: -item["count"])
    return PuzzleStats(
        total=total,
        mate=mate,
        material=total - mate,
        attempted=attempted,
        solved=solved,
        solved_rate=round(solved / attempted, 4) if attempted else 0.0,
        by_theme=by_theme,
    )


# ----------------------------------------------------------------------- job rows


def upsert_job(
    session: Session,
    job_id: str,
    status: str,
    progress: float = 0.0,
    message: str = "",
    game_id: Optional[str] = None,
    error: Optional[str] = None,
) -> AnalysisJob:
    job = session.get(AnalysisJob, job_id)
    if job is None:
        job = AnalysisJob(id=job_id, game_id=game_id)
        session.add(job)
    job.status = status
    job.progress = progress
    job.message = message
    if game_id:
        job.game_id = game_id
    job.error = error
    session.flush()
    return job


def get_job(session: Session, job_id: str) -> Optional[AnalysisJob]:
    return session.get(AnalysisJob, job_id)
