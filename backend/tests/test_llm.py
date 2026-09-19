"""LLM layer: provider isolation, grounding guards, failure handling.

Every test here uses a fake provider. The point is not to test DeepSeek but to prove
that a broken, unavailable, or hallucinating model can never corrupt a review:

* no API key  -> deterministic explanations, engine review untouched,
* invalid JSON -> rejected, deterministic fallback used,
* schema violation -> rejected,
* invented best move -> rejected,
* unsupported concept tag -> dropped with a warning.
"""

import json
from typing import Dict, Optional

import pytest

from coaching.explainer import CoachExplainer, collect_events, moment_cache_key
from coaching.grounding import validate_explanation
from coaching.provider import DeepSeekProvider, LLMResult, NullProvider, build_provider
from coaching.provider import _parse_json
from models.enums import Color, ConceptType, ExplanationSource, GamePhase, Severity
from models.evidence import (
    AnalysisEvidence,
    BoardContext,
    DetectedConcept,
    EngineEvidence,
    PlayedMove,
    PositionContext,
    WdlDistribution,
)
from models.explanation import LLMExplanation

VALID_PAYLOAD: Dict[str, object] = {
    "summary": "3...Nf6 是严重失误，它让白方立刻有一步杀棋。",
    "what_happened": "你走了 Nf6，白方的 Qxf7# 立刻将杀。",
    "why_it_matters": "期望得分从 0.775 掉到 0.00。",
    "likely_human_error": "你没有先检查对手的强制手。",
    "better_thinking_process": "1. 对手有没有将军？2. 对手有没有吃子？",
    "general_lesson": "每走一步前先检查对手的将军、吃子和威胁。",
    "best_move_explanation": "引擎推荐 g6，攻击白后。",
    "concept_tags": ["mating_threat"],
    "confidence": 0.8,
}


class FakeProvider:
    """Returns a canned response; records the prompts it received."""

    name = "fake"
    model = "fake-model"

    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.calls = []

    def complete_json(self, *, system: str, user: str, temperature: Optional[float] = None):
        self.calls.append({"system": system, "user": user})
        if not self._responses:
            return LLMResult(error="no_more_responses", model=self.model)
        return self._responses.pop(0)


def build_evidence(
    *,
    concepts=("mating_threat",),
    best_move_san: str = "g6",
    best_move_uci: str = "g7g6",
    played_san: str = "Nf6",
    played_uci: str = "g8f6",
) -> AnalysisEvidence:
    wdl_before = WdlDistribution(win=0.55, draw=0.45, loss=0.0)
    wdl_after = WdlDistribution(win=0.0, draw=0.0, loss=1.0)
    engine = EngineEvidence(
        pov_color=Color.BLACK,
        evaluation_before=0.36,
        evaluation_after=-10.0,
        mate_after=-1,
        wdl_before=wdl_before,
        wdl_after=wdl_after,
        expected_score_before=wdl_before.expected_score(),
        expected_score_after=wdl_after.expected_score(),
        expected_score_loss=0.775,
        best_move_uci=best_move_uci,
        best_move_san=best_move_san,
        best_line_uci=[best_move_uci, "d1d8"],
        best_line_san=[best_move_san, "Qxd8"],
        played_line_uci=[played_uci, "h5f7"],
        played_line_san=[played_san, "Qxf7#"],
        depth_before=12,
        depth_after=12,
    )
    return AnalysisEvidence(
        position=PositionContext(
            fen="r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 4 4",
            ply=6,
            move_number=3,
            player_color=Color.BLACK,
            phase=GamePhase.OPENING,
        ),
        played_move=PlayedMove(uci=played_uci, san=played_san),
        engine=engine,
        concepts=[
            DetectedConcept(type=ConceptType(value), confidence=0.95, evidence=["test evidence"])
            for value in concepts
        ],
        decision_errors=[],
        severity=Severity.BLUNDER,
        board_context=BoardContext(),
    )


# --------------------------------------------------------------- no API key mode


def test_missing_api_key_yields_null_provider():
    provider = build_provider("", "https://api.deepseek.com", "deepseek-chat", 30, 0.2, 1000)
    assert isinstance(provider, NullProvider)
    result = provider.complete_json(system="s", user="u")
    assert result.ok is False
    assert result.error == "llm_not_configured"


def test_explainer_without_a_key_uses_rules_and_never_calls_a_model():
    coach = CoachExplainer(provider=NullProvider())
    assert coach.llm_available is False
    explanation = coach.explain_moment(build_evidence())
    assert explanation.source is ExplanationSource.RULES
    assert explanation.explanation.summary
    assert explanation.model is None


# ---------------------------------------------------------------- happy path


def test_valid_response_is_used_and_marked_as_llm():
    provider = FakeProvider([LLMResult(data=dict(VALID_PAYLOAD), model="fake-model")])
    coach = CoachExplainer(provider=provider)
    result = coach.explain_moment(build_evidence())

    assert result.source is ExplanationSource.LLM
    assert result.explanation.summary == VALID_PAYLOAD["summary"]
    assert result.grounded is True
    assert result.model == "fake-model"

    # The prompt must carry the verified evidence, and must not ask for an evaluation.
    prompt = provider.calls[0]["user"]
    assert "\"expected_score_loss\"" in prompt
    assert "\"best_line\"" in prompt


def test_system_prompt_forbids_independent_chess_judgment():
    provider = FakeProvider([LLMResult(data=dict(VALID_PAYLOAD), model="fake-model")])
    CoachExplainer(provider=provider).explain_moment(build_evidence())
    system = provider.calls[0]["system"]
    for rule in ("不能自己评估局面", "不要与 Stockfish 的结论矛盾", "不要发明任何战术线路"):
        assert rule in system


# ------------------------------------------------------------------ failures


def test_invalid_json_falls_back_to_rules():
    provider = FakeProvider(
        [
            LLMResult(error="invalid_json", raw_text="not json", model="fake-model"),
            LLMResult(error="invalid_json", raw_text="still not json", model="fake-model"),
        ]
    )
    result = CoachExplainer(provider=provider).explain_moment(build_evidence())
    assert result.source is ExplanationSource.RULES
    assert any("AI 解释不可用" in warning for warning in result.validation_warnings)


def test_missing_required_fields_are_rejected():
    incomplete = {key: value for key, value in VALID_PAYLOAD.items() if key != "general_lesson"}
    provider = FakeProvider(
        [
            LLMResult(data=incomplete, model="fake-model"),
            LLMResult(data=incomplete, model="fake-model"),
        ]
    )
    result = CoachExplainer(provider=provider).explain_moment(build_evidence())
    assert result.source is ExplanationSource.RULES
    assert any("schema_validation_failed" in warning for warning in result.validation_warnings)


def test_timeout_falls_back_without_losing_the_review():
    provider = FakeProvider([LLMResult(error="timeout"), LLMResult(error="timeout")])
    result = CoachExplainer(provider=provider).explain_moment(build_evidence())
    assert result.source is ExplanationSource.RULES
    assert result.explanation.general_lesson


def test_repair_attempt_is_made_before_giving_up():
    provider = FakeProvider(
        [
            LLMResult(error="invalid_json", raw_text="{", model="fake-model"),
            LLMResult(data=dict(VALID_PAYLOAD), model="fake-model"),
        ]
    )
    result = CoachExplainer(provider=provider).explain_moment(build_evidence())
    assert result.source is ExplanationSource.LLM
    assert len(provider.calls) == 2
    assert "没有通过校验" in provider.calls[1]["user"]


# -------------------------------------------------------------- grounding


def test_invented_best_move_is_rejected():
    payload = dict(VALID_PAYLOAD)
    payload["best_move_explanation"] = "更好的走法是 Nc6，这样可以保护 f7。"
    evidence = build_evidence()
    report = validate_explanation(LLMExplanation.model_validate(payload), evidence)
    assert report.rejected
    assert "Nc6" in (report.reason or "")


def test_invented_move_in_a_factual_field_is_rejected():
    payload = dict(VALID_PAYLOAD)
    payload["what_happened"] = "你走了 Nf6，然后白方用 Qh5 将杀。"
    report = validate_explanation(LLMExplanation.model_validate(payload), build_evidence())
    assert report.rejected


def test_moves_that_only_appear_in_concept_evidence_are_accepted():
    """回归测试：概念证据里的句子提到的着法（例如 "Ba6 now attacks Rd3"）不算编造。

    这正是最初把一条本来正确的 AI 解释误判成幻觉的原因：校验只看引擎线路，
    而模型是从我们给它的概念证据里读到这些着法的。
    """
    evidence = build_evidence(concepts=("discovered_attack", "open_file"))
    evidence.concepts[0].evidence = [
        "the opponent discovered an attack: Ba6 now attacks Rd3 after the piece left b5."
    ]
    evidence.concepts[1].evidence = ["Rd1 moves to the fully open d file."]
    evidence.move_history_san = ["e4", "e5", "Nf3"]

    payload = dict(VALID_PAYLOAD)
    payload["what_happened"] = (
        "对手走 Ba6 之后，Rd3 受到攻击；你走了 Rd1，但引擎推荐 g6。"
    )
    report = validate_explanation(LLMExplanation.model_validate(payload), evidence)
    assert report.ok, report.reason


def test_engine_best_move_claim_still_rejects_a_move_from_concept_evidence():
    """即使那个着法在概念证据里出现过，也不能被说成是"引擎推荐"。"""
    evidence = build_evidence(concepts=("discovered_attack",))
    evidence.concepts[0].evidence = ["the opponent discovered an attack: Ba6 attacks Rd3."]

    payload = dict(VALID_PAYLOAD)
    payload["best_move_explanation"] = "更好的走法是 Ba6。"
    report = validate_explanation(LLMExplanation.model_validate(payload), evidence)
    assert report.rejected
    assert "Ba6" in (report.reason or "")


def test_contrasting_the_played_move_with_the_engine_move_is_allowed():
    """「引擎推荐 g6，而不是你走的 Nf6」是正常对比，不该被判成幻觉。"""
    payload = dict(VALID_PAYLOAD)
    payload["best_move_explanation"] = "引擎推荐 g6，而不是你走的 Nf6；g6 先给王留出退路。"
    report = validate_explanation(LLMExplanation.model_validate(payload), build_evidence())
    assert report.ok, report.reason


def test_mentioning_the_opponents_move_is_not_a_contradiction():
    payload = dict(VALID_PAYLOAD)
    payload["best_move_explanation"] = "在被 Qxf7# 将杀之前，你应该先处理 f7 的防守。"
    payload["what_happened"] = "对手的 Qxf7# 说明 f7 早就该防。"
    report = validate_explanation(LLMExplanation.model_validate(payload), build_evidence())
    assert report.ok, report.reason


def test_recommending_an_engine_move_is_allowed():
    for text in ("推荐 g6。", "更好的走法是 g6。", "应该走 g6。", "正着是 g6。"):
        payload = dict(VALID_PAYLOAD)
        payload["best_move_explanation"] = text
        report = validate_explanation(LLMExplanation.model_validate(payload), build_evidence())
        assert report.ok, (text, report.reason)


def test_recommending_a_move_outside_the_engine_lines_is_rejected():
    for text in ("推荐 Nc6。", "更好的走法是 Nc6。", "应该走 Nc6。", "其实 Kg8 更好。"):
        payload = dict(VALID_PAYLOAD)
        payload["best_move_explanation"] = text
        report = validate_explanation(LLMExplanation.model_validate(payload), build_evidence())
        assert report.rejected, text


def test_move_history_is_an_acceptable_reference():
    evidence = build_evidence()
    evidence.move_history_san = ["e4", "e5", "Nf3"]
    payload = dict(VALID_PAYLOAD)
    payload["what_happened"] = "前面 Nf3 很正常，问题出在这一步。"
    report = validate_explanation(LLMExplanation.model_validate(payload), evidence)
    assert report.ok, report.reason


def test_unsupported_concept_tag_is_dropped_with_a_warning():
    payload = dict(VALID_PAYLOAD)
    payload["concept_tags"] = ["mating_threat", "positional_squeeze"]
    report = validate_explanation(LLMExplanation.model_validate(payload), build_evidence())
    assert report.ok
    assert report.explanation is not None
    assert report.explanation.concept_tags == ["mating_threat"]
    assert any("positional_squeeze" in warning for warning in report.warnings)


def test_confidence_is_capped_so_prose_is_never_full_certainty():
    payload = dict(VALID_PAYLOAD)
    payload["confidence"] = 1.0
    report = validate_explanation(LLMExplanation.model_validate(payload), build_evidence())
    assert report.explanation is not None
    assert report.explanation.confidence <= 0.9


def test_evidence_free_position_lowers_confidence_and_says_so():
    report = validate_explanation(
        LLMExplanation.model_validate(VALID_PAYLOAD), build_evidence(concepts=())
    )
    assert report.explanation is not None
    assert report.explanation.confidence <= 0.5
    assert any("没有检测到可靠的概念" in warning for warning in report.warnings)


def test_allowed_move_tokens_accept_engine_lines():
    payload = dict(VALID_PAYLOAD)
    payload["best_move_explanation"] = "引擎推荐 g6，之后是 Qxd8。"
    report = validate_explanation(LLMExplanation.model_validate(payload), build_evidence())
    assert report.ok


def test_grounding_rejects_a_response_that_contradicts_the_engine():
    payload = dict(VALID_PAYLOAD)
    payload["best_move_explanation"] = "其实 Kg8 也可以。"
    report = validate_explanation(LLMExplanation.model_validate(payload), build_evidence())
    assert report.rejected


# ------------------------------------------------------------------- caching


def test_explanations_are_cached():
    class Cache:
        def __init__(self):
            self.store = {}

        def get(self, key):
            return self.store.get(key)

        def put(self, key, value):
            self.store[key] = value

    provider = FakeProvider([LLMResult(data=dict(VALID_PAYLOAD), model="fake-model")])
    coach = CoachExplainer(provider=provider, cache=Cache())
    evidence = build_evidence()

    first = coach.explain_moment(evidence)
    second = coach.explain_moment(evidence)

    assert first.cached is False
    assert second.cached is True
    assert len(provider.calls) == 1, "the second call must not hit the provider"


def test_cache_key_changes_when_the_evidence_changes():
    model = "fake-model"
    key_a = moment_cache_key(build_evidence(), model)
    assert moment_cache_key(build_evidence(), model) == key_a
    assert moment_cache_key(build_evidence(best_move_san="d6", best_move_uci="d7d6"), model) != key_a
    assert moment_cache_key(build_evidence(), "another-model") != key_a
    assert moment_cache_key(build_evidence(concepts=()), model) != key_a


# ------------------------------------------------------------ game summary


def test_game_summary_uses_rules_without_a_key():
    from models.review import GameReview

    review = GameReview(
        game_id="g",
        white="A",
        black="B",
        result="1-0",
        player_color=Color.BLACK,
    )
    record = CoachExplainer(provider=NullProvider()).summarize_game(review)
    assert record.source is ExplanationSource.RULES
    assert "没有出现" in record.explanation.summary


def test_collect_events_only_uses_stored_mistakes():
    review = _review_with_one_moment()
    events = collect_events(review)
    assert len(events) == 1
    event = events[0]
    assert event["move_number"] == 3
    assert event["played_move"] == "Nf6"
    assert event["severity"] == "blunder"
    assert event["decision_error_tags"] == []
    assert "one_liner_zh" in event


def test_game_summary_with_llm_provider():
    provider = FakeProvider(
        [
            LLMResult(
                data={
                    "summary": "两次失误都发生在没有检查对手强制手的时候。",
                    "main_patterns": ["未检查对手强制手"],
                    "practice_advice": ["每步先看将军和吃子"],
                    "confidence": 0.6,
                },
                model="fake-model",
            )
        ]
    )
    record = CoachExplainer(provider=provider).summarize_game(_review_with_one_moment())
    assert record.source is ExplanationSource.LLM
    assert record.explanation.main_patterns


def _review_with_one_moment():
    from models.review import CriticalMoment, GameReview

    evidence = build_evidence()
    moment = CriticalMoment(
        ply=6,
        move_number=3,
        player_color=Color.BLACK,
        phase=GamePhase.OPENING,
        severity=Severity.BLUNDER,
        criticality_score=1.0,
        reasons=[],
        one_liner_zh="你漏掉了对手的杀棋。",
        fen=evidence.position.fen,
        played_move_san="Nf6",
        solution_uci="g7g6",
        solution_san="g6",
        evidence=evidence,
    )
    return GameReview(
        game_id="g",
        white="A",
        black="B",
        result="1-0",
        player_color=Color.BLACK,
        critical_moments=[moment],
    )


# ------------------------------------------------------------- json parsing


def test_provider_parses_fenced_and_padded_json():
    assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_json('Here you go:\n{"a": 2}') == {"a": 2}
    assert _parse_json("no json here") is None
    assert _parse_json("[1, 2, 3]") is None


def test_deepseek_provider_without_key_never_calls_the_network():
    provider = DeepSeekProvider(api_key="", base_url="http://127.0.0.1:1", model="m")
    result = provider.complete_json(system="s", user="u")
    assert result.error == "missing_api_key"


def test_deepseek_provider_reports_network_errors():
    provider = DeepSeekProvider(
        api_key="dummy", base_url="http://127.0.0.1:9", model="m", timeout=0.5
    )
    result = provider.complete_json(system="s", user="u")
    assert result.ok is False
    assert result.error and ("network_error" in result.error or "timeout" in result.error)


@pytest.mark.parametrize("text", ["推荐a6。", "应该走exd5。", "最佳走法是Nf6。", "推荐Qxd8。", "a6是更好的走法。"])
def test_root_recommendation_cannot_be_invented_played_or_a_continuation(text):
    report = validate_explanation(LLMExplanation.model_validate({**VALID_PAYLOAD, "best_move_explanation": text}), build_evidence())
    assert report.rejected


@pytest.mark.parametrize("field,text", [
    ("what_happened", "你走了a6。"), ("summary", "之后是exd5。"),
    ("general_lesson", "白方的Qh7#会将杀。"),
    ("why_it_matters", "期望得分从0.99掉到0.98。"),
    ("why_it_matters", "期望得分从0.00升到0.775。"),
])
def test_unknown_moves_and_numbers_in_any_prose_fall_back(field, text):
    payload = {**VALID_PAYLOAD, field: text}
    provider = FakeProvider([LLMResult(data=payload), LLMResult(data=payload)])
    result = CoachExplainer(provider=provider).explain_moment(build_evidence())
    assert result.source is ExplanationSource.RULES
    assert result.validation_warnings


def test_square_references_and_rounded_scores_remain_valid():
    payload = {**VALID_PAYLOAD, "what_happened": "a6 格子为空；你走了Nf6。", "why_it_matters": "期望得分从77.5%降到0%。"}
    assert validate_explanation(LLMExplanation.model_validate(payload), build_evidence()).ok


@pytest.mark.parametrize("change", ["score", "pv", "concept", "history"])
def test_cache_includes_complete_prompt_evidence(change):
    evidence = build_evidence()
    original = moment_cache_key(evidence, "model")
    if change == "score":
        evidence.engine.evaluation_before = 0.45
    elif change == "pv":
        evidence.engine.best_line_san.append("Rxd8")
    elif change == "concept":
        evidence.concepts[0].evidence.append("new verified observation")
    else:
        evidence.move_history_san.append("e4")
    assert moment_cache_key(evidence, "model") != original


@pytest.mark.parametrize("field,text", [("summary", "你错过了Qh7#。"), ("practice_advice", "推荐a6。"), ("main_patterns", "期望得分损失0.99。")])
def test_summary_grounding_failures_are_not_silently_ignored(field, text):
    payload = {"summary": "这次漏掉了强制手。", "main_patterns": [], "practice_advice": [], "confidence": 0.6}
    payload[field] = text if field == "summary" else [text]
    result = CoachExplainer(provider=FakeProvider([LLMResult(data=payload)])).summarize_game(_review_with_one_moment())
    assert result.source is ExplanationSource.RULES
    assert result.validation_warnings
