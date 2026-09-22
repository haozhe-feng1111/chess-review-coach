"""SQLAlchemy tables.

Two representations of the same analysis are kept, on purpose:

* ``Game.review_json`` — the full :class:`GameReview`, so opening a game never requires
  re-running or re-assembling anything,
* normalized rows (``MoveAnalysis``, ``CriticalPosition``, ``MistakeEvent``,
  ``DetectedConcept``) — the queryable projection that powers the weakness profile.

``MistakeEvent`` is the unit of long-term learning: one row per problem move, carrying
the concept tags, decision-error tags, severity, phase and time needed to answer "what
kind of mistakes does this player repeat?".
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.utcnow()


class Game(Base):
    __tablename__ = "games"

    id = Column(String(64), primary_key=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False, index=True)
    white = Column(String(128), default="White")
    black = Column(String(128), default="Black")
    result = Column(String(16), default="*")
    player_color = Column(String(8), default="white")
    opening = Column(String(128), nullable=True)
    pgn = Column(Text, default="")
    headers = Column(JSON, default=dict)
    move_count = Column(Integer, default=0)
    player_move_count = Column(Integer, default=0)
    blunders = Column(Integer, default=0)
    mistakes = Column(Integer, default=0)
    inaccuracies = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    average_loss = Column(Float, default=0.0)
    engine_name = Column(String(64), default="")
    analysis_seconds = Column(Float, default=0.0)
    status = Column(String(16), default="completed")
    warnings = Column(JSON, default=list)
    #: Serialized GameReview — the source of truth for the review screen.
    review_json = Column(JSON, nullable=True)

    moves = relationship(
        "MoveAnalysis", back_populates="game", cascade="all, delete-orphan", passive_deletes=True
    )
    criticals = relationship(
        "CriticalPosition", back_populates="game", cascade="all, delete-orphan", passive_deletes=True
    )
    # NOTE: the relationship is deliberately not called ``mistakes`` — that name is
    # already taken by the integer column above, and a relationship silently shadows a
    # column of the same name.
    mistake_events = relationship(
        "MistakeEvent", back_populates="game", cascade="all, delete-orphan", passive_deletes=True
    )
    explanations = relationship(
        "LLMExplanation", back_populates="game", cascade="all, delete-orphan", passive_deletes=True
    )


class MoveAnalysis(Base):
    __tablename__ = "move_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(String(64), ForeignKey("games.id", ondelete="CASCADE"), index=True)
    ply = Column(Integer, nullable=False)
    move_number = Column(Integer, nullable=False)
    color = Column(String(8), nullable=False)
    san = Column(String(16), nullable=False)
    uci = Column(String(8), nullable=False)
    fen_before = Column(String(128), default="")
    fen_after = Column(String(128), default="")
    is_player_move = Column(Boolean, default=False, index=True)
    severity = Column(String(16), nullable=True, index=True)
    expected_score_loss = Column(Float, nullable=True)
    evaluation_after = Column(Float, nullable=True)
    phase = Column(String(16), nullable=True)
    concept_tags = Column(JSON, default=list)
    decision_error_tags = Column(JSON, default=list)
    is_critical = Column(Boolean, default=False)

    game = relationship("Game", back_populates="moves")

    __table_args__ = (UniqueConstraint("game_id", "ply", name="uq_move_game_ply"),)


class CriticalPosition(Base):
    __tablename__ = "critical_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(String(64), ForeignKey("games.id", ondelete="CASCADE"), index=True)
    ply = Column(Integer, nullable=False)
    move_number = Column(Integer, nullable=False)
    phase = Column(String(16), nullable=False)
    severity = Column(String(16), nullable=False)
    criticality_score = Column(Float, default=0.0)
    reasons = Column(JSON, default=list)
    #: Everything needed to re-ask "what is the best move here?" (future trainer).
    fen = Column(String(128), nullable=False)
    played_move_san = Column(String(16), nullable=False)
    solution_uci = Column(String(8), nullable=True)
    solution_san = Column(String(16), nullable=True)
    one_liner_zh = Column(Text, default="")
    evidence_json = Column(JSON, nullable=False)

    game = relationship("Game", back_populates="criticals")

    __table_args__ = (UniqueConstraint("game_id", "ply", name="uq_critical_game_ply"),)


class MistakeEvent(Base):
    """One problem move by the analyzed player — the row the profile aggregates."""

    __tablename__ = "mistake_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(String(64), ForeignKey("games.id", ondelete="CASCADE"), index=True)
    ply = Column(Integer, nullable=False)
    move_number = Column(Integer, nullable=False)
    player_color = Column(String(8), nullable=False, index=True)
    phase = Column(String(16), nullable=False, index=True)
    severity = Column(String(16), nullable=False, index=True)
    expected_score_loss = Column(Float, default=0.0)
    evaluation_before = Column(Float, nullable=True)
    evaluation_after = Column(Float, nullable=True)
    san = Column(String(16), default="")
    one_liner_zh = Column(Text, default="")
    #: Highest-confidence decision error, denormalized for fast GROUP BY analytics.
    primary_error = Column(String(48), nullable=False, index=True)
    primary_error_confidence = Column(Float, default=0.0)
    decision_error_tags = Column(JSON, default=list)
    concept_tags = Column(JSON, default=list)
    is_critical = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False, index=True)

    game = relationship("Game", back_populates="mistake_events")
    concepts = relationship(
        "DetectedConceptRow",
        back_populates="mistake",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("game_id", "ply", name="uq_mistake_game_ply"),
        Index("ix_mistake_error_created", "primary_error", "created_at"),
    )


class DetectedConceptRow(Base):
    __tablename__ = "detected_concepts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mistake_event_id = Column(
        Integer, ForeignKey("mistake_events.id", ondelete="CASCADE"), index=True
    )
    concept_type = Column(String(48), nullable=False, index=True)
    confidence = Column(Float, default=0.0)
    pieces = Column(JSON, default=list)
    squares = Column(JSON, default=list)
    evidence = Column(JSON, default=list)
    meta = Column(JSON, default=dict)

    mistake = relationship("MistakeEvent", back_populates="concepts")


class LLMExplanation(Base):
    """Cached AI or rule-based explanation text."""

    __tablename__ = "llm_explanations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(String(64), ForeignKey("games.id", ondelete="CASCADE"), index=True)
    scope = Column(String(24), nullable=False, default="moment")  # moment | game_summary
    ref_key = Column(String(128), nullable=False)
    cache_key = Column(String(160), nullable=False, index=True)
    source = Column(String(16), nullable=False, default="rules")
    model = Column(String(64), nullable=True)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    game = relationship("Game", back_populates="explanations")

    __table_args__ = (UniqueConstraint("cache_key", name="uq_explanation_cache_key"),)


class AnalysisCacheEntry(Base):
    """Cached raw engine output for one position + one configuration."""

    __tablename__ = "analysis_cache"

    cache_key = Column(String(128), primary_key=True)
    fen = Column(String(128), nullable=False, index=True)
    engine_name = Column(String(64), default="")
    depth = Column(Integer, default=0)
    multipv = Column(Integer, default=1)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=_utcnow, nullable=False, index=True)


class PuzzleRow(Base):
    """一条题目。id 是"对局 id:手数"，所以重跑分析不会产生重复题目。"""

    __tablename__ = "puzzles"

    id = Column(String(64), primary_key=True)
    game_id = Column(String(64), ForeignKey("games.id", ondelete="CASCADE"), index=True)
    ply = Column(Integer, nullable=False)
    move_number = Column(Integer, nullable=False)
    player_color = Column(String(8), nullable=False)
    phase = Column(String(16), nullable=False)
    kind = Column(String(16), nullable=False, index=True)
    fen = Column(String(128), nullable=False)
    #: 同一个局面只收一次（不同对局出现同一局面时，保留最早的那条）
    fen_key = Column(String(128), nullable=False, unique=True, index=True)
    solution_uci = Column(String(8), nullable=False)
    solution_san = Column(String(16), nullable=False)
    solution_line_uci = Column(JSON, default=list)
    solution_line_san = Column(JSON, default=list)
    mate_in = Column(Integer, nullable=True)
    material_gain = Column(Integer, nullable=True)
    theme = Column(String(48), nullable=True, index=True)
    theme_label_zh = Column(String(64), default="未分类")
    played_san = Column(String(16), default="")
    severity = Column(String(16), nullable=False)
    difficulty = Column(String(16), default="medium")
    concept_tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=_utcnow, nullable=False, index=True)

    attempts = relationship(
        "PuzzleAttemptRow", back_populates="puzzle", cascade="all, delete-orphan", passive_deletes=True
    )


class PuzzleAttemptRow(Base):
    """做题记录：以后用来验证"某一类错误是否真的变少了"。"""

    __tablename__ = "puzzle_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    puzzle_id = Column(String(64), ForeignKey("puzzles.id", ondelete="CASCADE"), index=True)
    correct = Column(Boolean, default=False, index=True)
    played_uci = Column(String(8), nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False, index=True)

    puzzle = relationship("PuzzleRow", back_populates="attempts")


class AnalysisJob(Base):
    """Progress row for a running analysis, so the UI can poll it."""

    __tablename__ = "analysis_jobs"

    id = Column(String(64), primary_key=True)
    game_id = Column(String(64), nullable=True, index=True)
    status = Column(String(16), default="pending")
    progress = Column(Float, default=0.0)
    message = Column(Text, default="")
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


__all__ = [
    "Base",
    "Game",
    "MoveAnalysis",
    "CriticalPosition",
    "MistakeEvent",
    "DetectedConceptRow",
    "LLMExplanation",
    "AnalysisCacheEntry",
    "AnalysisJob",
    "PuzzleRow",
    "PuzzleAttemptRow",
]
