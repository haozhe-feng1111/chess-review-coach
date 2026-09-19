"""Coach orchestration: LLM when available, deterministic templates otherwise.

Contract with the rest of the app:

* engine review never depends on this module,
* a missing API key, a timeout, an HTTP error or an ungrounded response all end in the
  same place — a deterministic explanation plus a note that the AI text is unavailable,
* every explanation (AI or rule-based) is cached, so revisiting a game costs nothing.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Protocol

from coaching import fallback, grounding
from coaching.prompts import (
    GAME_SUMMARY_SYSTEM_PROMPT,
    MOMENT_SYSTEM_PROMPT,
    build_game_summary_prompt,
    build_moment_prompt,
    build_repair_prompt,
)
from coaching.provider import LLMProvider, LLMResult, NullProvider
from coaching.render import one_liner_zh
from models.enums import DecisionErrorType, ExplanationSource
from models.evidence import AnalysisEvidence
from models.explanation import (
    GameSummaryExplanation,
    GameSummaryRecord,
    LLMExplanation,
    MomentExplanation,
)
from models.review import GameReview

logger = logging.getLogger(__name__)

#: Bumped whenever the prompts change, so cached text is never mixed across versions.
PROMPT_VERSION = "2026-09-grounding-5"

MAX_LLM_ATTEMPTS = 2


class ExplanationCache(Protocol):
    def get(self, key: str) -> Optional[dict]:  # pragma: no cover - protocol
        ...

    def put(self, key: str, value: dict) -> None:  # pragma: no cover - protocol
        ...


class NullExplanationCache:
    def get(self, key: str) -> Optional[dict]:
        return None

    def put(self, key: str, value: dict) -> None:
        return None


@dataclass
class CoachResult:
    moment: MomentExplanation
    note_zh: str = ""


class CoachExplainer:
    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        cache: Optional[ExplanationCache] = None,
    ) -> None:
        self._provider = provider if provider is not None else NullProvider()
        self._cache = cache if cache is not None else NullExplanationCache()

    @property
    def llm_available(self) -> bool:
        return not isinstance(self._provider, NullProvider)

    @property
    def model(self) -> str:
        return getattr(self._provider, "model", "") or ""

    # ------------------------------------------------------------- single moment

    def explain_moment(self, evidence: AnalysisEvidence) -> MomentExplanation:
        key = moment_cache_key(evidence, self.model if self.llm_available else "rules")
        cached = self._cache.get(key)
        if cached is not None:
            try:
                restored = MomentExplanation.model_validate(cached)
                return restored.model_copy(update={"cached": True})
            except Exception:  # pragma: no cover - corrupt cache entry
                logger.warning("Discarding unreadable cached explanation %s", key)

        result = self._generate(evidence)
        try:
            self._cache.put(key, result.model_dump(mode="json"))
        except Exception:  # pragma: no cover - caching must never break a response
            logger.debug("Could not cache explanation", exc_info=True)
        return result

    def _generate(self, evidence: AnalysisEvidence) -> MomentExplanation:
        if not self.llm_available:
            return fallback.build_rule_moment(evidence)

        user_prompt = build_moment_prompt(evidence)
        warnings: List[str] = []
        last_error: Optional[str] = None
        response: Optional[LLMResult] = None

        for attempt in range(MAX_LLM_ATTEMPTS):
            response = self._provider.complete_json(
                system=MOMENT_SYSTEM_PROMPT,
                user=user_prompt
                if attempt == 0
                else "{}\n\n{}".format(
                    user_prompt,
                    build_repair_prompt(
                        (response.raw_text if response and response.raw_text else ""),
                        last_error or "unknown",
                    ),
                ),
            )
            if not response.ok:
                last_error = response.error or "unknown_error"
                if last_error in ("missing_api_key", "llm_not_configured"):
                    break
                continue

            try:
                parsed = LLMExplanation.model_validate(response.data)
            except Exception as exc:
                last_error = "schema_validation_failed: {}".format(str(exc)[:300])
                continue

            report = grounding.validate_explanation(parsed, evidence)
            if report.rejected:
                last_error = report.reason or "grounding_failed"
                continue

            assert report.explanation is not None
            return MomentExplanation(
                source=ExplanationSource.LLM,
                explanation=report.explanation,
                model=response.model,
                generated_at=datetime.utcnow(),
                validation_warnings=report.warnings,
                grounded=True,
            )

        warnings.append("AI 解释不可用（{}）。以下为基于引擎证据的规则模板说明。".format(last_error))
        rule_based = fallback.build_rule_explanation(evidence)
        return MomentExplanation(
            source=ExplanationSource.RULES,
            explanation=rule_based,
            model=None,
            generated_at=datetime.utcnow(),
            validation_warnings=warnings,
            grounded=True,
        )

    # -------------------------------------------------------------- game summary

    def summarize_game(self, review: GameReview) -> GameSummaryRecord:
        events = collect_events(review)
        meta = {
            "white": review.white,
            "black": review.black,
            "result": review.result,
            "player_color": review.player_color.value,
            "critical_moments": len(review.critical_moments),
            "counts": review.counts.model_dump(),
            "average_expected_score_loss": review.average_expected_score_loss,
        }
        key = summary_cache_key(events, meta, self.model if self.llm_available else "rules")
        cached = self._cache.get(key)
        if cached is not None:
            try:
                restored = GameSummaryRecord.model_validate(cached)
                return restored.model_copy(update={"cached": True})
            except Exception:  # pragma: no cover
                logger.warning("Discarding unreadable cached game summary")

        record = self._generate_summary(events, meta)
        try:
            self._cache.put(key, record.model_dump(mode="json"))
        except Exception:  # pragma: no cover
            logger.debug("Could not cache game summary", exc_info=True)
        return record

    def _generate_summary(
        self, events: List[Dict[str, object]], meta: Dict[str, object]
    ) -> GameSummaryRecord:
        rule_based = fallback.build_rule_summary(events)
        if not self.llm_available or not events:
            return GameSummaryRecord(
                source=ExplanationSource.RULES,
                explanation=rule_based,
                model=None,
                generated_at=datetime.utcnow(),
            )

        response = self._provider.complete_json(
            system=GAME_SUMMARY_SYSTEM_PROMPT,
            user=build_game_summary_prompt(events, meta),
        )
        if not response.ok:
            return GameSummaryRecord(
                source=ExplanationSource.RULES,
                explanation=rule_based,
                model=None,
                generated_at=datetime.utcnow(),
            )

        try:
            parsed = GameSummaryExplanation.model_validate(response.data)
        except Exception:
            return GameSummaryRecord(
                source=ExplanationSource.RULES,
                explanation=rule_based,
                model=None,
                generated_at=datetime.utcnow(),
            )

        allowed = _allowed_summary_moves(events)
        warnings = grounding.validate_game_summary(
            " ".join([parsed.summary] + list(parsed.main_patterns) + list(parsed.practice_advice)),
            allowed, len(events), numbers={"events": events, "meta": meta},
        )
        if warnings:
            return GameSummaryRecord(source=ExplanationSource.RULES, explanation=rule_based,
                                     generated_at=datetime.utcnow(), validation_warnings=warnings)
        if len(events) < 3:
            parsed = parsed.model_copy(update={"confidence": min(parsed.confidence, 0.5)})
            warnings.append("失误样本过少，整体结论仅供参考。")
        return GameSummaryRecord(
            source=ExplanationSource.LLM,
            explanation=parsed,
            model=response.model,
            generated_at=datetime.utcnow(),
            validation_warnings=warnings,
        )


# ------------------------------------------------------------------------ helpers


def collect_events(review: GameReview) -> List[Dict[str, object]]:
    """The stored mistake events the game summary is allowed to talk about."""
    events: List[Dict[str, object]] = []
    for moment in review.critical_moments:
        evidence = moment.evidence
        events.append(
            {
                "move_number": moment.move_number,
                "played_move": moment.played_move_san,
                "severity": moment.severity.value,
                "expected_score_loss": round(evidence.engine.expected_score_loss, 4),
                "phase": moment.phase.value,
                "evaluation_before": evidence.engine.evaluation_before,
                "evaluation_after": evidence.engine.evaluation_after,
                "best_move": evidence.engine.best_move_san,
                "concept_tags": [concept.type.value for concept in evidence.concepts],
                "decision_error_tags": [error.type.value for error in evidence.decision_errors],
                "one_liner_zh": one_liner_zh(evidence),
            }
        )
    return events


def moment_cache_key(evidence: AnalysisEvidence, model: str) -> str:
    """Cache key covering everything that can change the explanation."""
    material = json.dumps(
        {
            "prompt": PROMPT_VERSION,
            "model": model,
            "evidence": evidence.to_llm_payload(),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return "moment:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def summary_cache_key(
    events: List[Dict[str, object]], meta: Dict[str, object], model: str
) -> str:
    material = json.dumps(
        {"prompt": PROMPT_VERSION, "model": model, "events": events, "meta": meta},
        sort_keys=True,
        ensure_ascii=False,
    )
    return "summary:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _allowed_summary_moves(events: List[Dict[str, object]]) -> set:
    from coaching.grounding import _normalize

    allowed = set()
    for event in events:
        for key in ("played_move", "best_move"):
            value = event.get(key)
            if isinstance(value, str) and value:
                allowed.add(_normalize(value))
    return allowed
