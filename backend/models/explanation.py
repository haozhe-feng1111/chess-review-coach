"""LLM-facing schemas.

The LLM must return exactly this shape. Everything is validated before it reaches
the UI, and the LLM can never change an engine value: these models contain prose
and tags only, never an evaluation.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from models.enums import ExplanationSource


class LLMExplanation(BaseModel):
    """Structured coaching text.

    Required fields are the ones a useful explanation cannot omit; if they are
    missing the response is rejected and the deterministic fallback is used instead
    of showing half an explanation.
    """

    summary: str = Field(min_length=1)
    what_happened: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    better_thinking_process: str = Field(min_length=1)
    general_lesson: str = Field(min_length=1)

    likely_human_error: str = ""
    best_move_explanation: str = ""
    concept_tags: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("summary", "what_happened", "why_it_matters", "better_thinking_process", "general_lesson")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field must not be blank")
        return cleaned


class MomentExplanation(BaseModel):
    """One explanation attached to one critical moment, whatever produced it."""

    source: ExplanationSource
    explanation: LLMExplanation
    model: Optional[str] = None
    generated_at: Optional[datetime] = None
    validation_warnings: List[str] = Field(default_factory=list)
    # False when the deterministic grounding checks had to drop or flag something.
    grounded: bool = True
    cached: bool = False


class GameSummaryExplanation(BaseModel):
    """Game-level summary of already-established mistake events."""

    summary: str = Field(min_length=1)
    main_patterns: List[str] = Field(default_factory=list)
    practice_advice: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class GameSummaryRecord(BaseModel):
    source: ExplanationSource
    explanation: GameSummaryExplanation
    model: Optional[str] = None
    generated_at: Optional[datetime] = None
    cached: bool = False
    validation_warnings: List[str] = Field(default_factory=list)
