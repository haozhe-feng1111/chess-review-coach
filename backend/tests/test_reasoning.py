"""Phase classification, decision-error taxonomy, profile statistics and Chinese
rendering. All deterministic, no engine required.
"""

import chess
import pytest

from analysis.phase import PhaseClassifier, classify_phase
from analysis.profile import build_profile
from analysis.thresholds import THRESHOLDS
from coaching import fallback
from coaching.render import (
    ERROR_LESSON_ZH,
    concept_phrase_zh,
    key_facts_zh,
    move_label_zh,
    one_liner_zh,
)
from coaching.taxonomy import TaxonomyContext, classify_decision_errors
from models.enums import (
    ConceptType,
    DecisionErrorType,
    GamePhase,
    Severity,
)
from models.evidence import DetectedConcept
from storage.repository import ProfileInput


# ------------------------------------------------------------------- phase


def test_start_position_is_the_opening():
    assert classify_phase(chess.Board(), 1) is GamePhase.OPENING
    assert classify_phase(chess.Board(), 7) is GamePhase.OPENING


def test_developed_position_is_the_middlegame():
    board = chess.Board("r1bq1rk1/pp2bppp/2n1pn2/2pp4/3P4/2NBPN2/PPP2PPP/R1BQ1RK1 w - - 8 8")
    assert classify_phase(board, 8) is GamePhase.MIDDLEGAME


def test_bare_kings_are_an_endgame():
    assert classify_phase(chess.Board("8/5p2/6k1/8/8/6K1/4P3/8 w - - 40 40"), 40) is GamePhase.ENDGAME
    # Even at a low move number, a queenless, minorless board is an endgame.
    assert classify_phase(chess.Board("8/8/4k3/8/8/4K3/6P1/8 w - - 12 12"), 12) is GamePhase.ENDGAME


def test_phase_classifier_is_replaceable():
    always_endgame = PhaseClassifier(THRESHOLDS.phase.__class__(opening_max_fullmove=0))
    assert always_endgame.classify(chess.Board(), 1) in (GamePhase.OPENING, GamePhase.MIDDLEGAME)


# ---------------------------------------------------------------- taxonomy


def make_taxonomy_context(**overrides) -> TaxonomyContext:
    """Build a taxonomy context.

    Note that ``TaxonomyContext.evidence`` is an :class:`EngineEvidence`, not the fuller
    :class:`AnalysisEvidence` used by the LLM layer.
    """
    from tests.test_llm import build_evidence

    concepts = [
        DetectedConcept(type=ConceptType(value), confidence=confidence, evidence=["test"])
        for value, confidence in overrides.pop("concepts", [])
    ]
    engine = overrides.pop("engine", None) or build_evidence().engine
    return TaxonomyContext(
        evidence=engine,
        concepts=concepts,
        severity=overrides.pop("severity", Severity.BLUNDER),
        phase=overrides.pop("phase", GamePhase.MIDDLEGAME),
        board_context=overrides.pop("board_context", None) or __import__(
            "models.evidence", fromlist=["BoardContext"]
        ).BoardContext(),
        played_san=overrides.pop("played_san", "Nf6"),
        move_number=overrides.pop("move_number", 3),
        thresholds=THRESHOLDS,
    )


def only_types(errors):
    return {error.type for error in errors}


def test_removal_of_defender_maps_to_defender_removed():
    ctx = make_taxonomy_context(concepts=[("removal_of_defender", 0.95)])
    errors = classify_decision_errors(ctx)
    assert DecisionErrorType.DEFENDER_REMOVED in only_types(errors)
    top = errors[0]
    assert top.supporting_concepts == [ConceptType.REMOVAL_OF_DEFENDER]
    assert top.confidence > 0.8


def test_hanging_piece_requires_a_serious_severity():
    concepts = [("hanging_piece", 0.9)]
    assert DecisionErrorType.HANGING_PIECE in only_types(
        classify_decision_errors(make_taxonomy_context(concepts=concepts))
    )
    assert DecisionErrorType.HANGING_PIECE not in only_types(
        classify_decision_errors(
            make_taxonomy_context(concepts=concepts, severity=Severity.INACCURACY)
        )
    )


def test_mating_threat_maps_to_forcing_moves_not_checked_and_king_safety():
    ctx = make_taxonomy_context(concepts=[("mating_threat", 0.95)])
    types = only_types(classify_decision_errors(ctx))
    assert DecisionErrorType.KING_SAFETY in types
    assert DecisionErrorType.FORCING_MOVES_NOT_CHECKED in types


def test_missed_check_maps_to_forcing_moves_not_checked():
    ctx = make_taxonomy_context(concepts=[("missed_check", 0.9)])
    errors = classify_decision_errors(ctx)
    assert errors[0].type is DecisionErrorType.FORCING_MOVES_NOT_CHECKED


def test_advantage_conversion_rule():
    from tests.test_llm import build_evidence

    engine = build_evidence().engine
    engine.expected_score_before = 0.93
    engine.expected_score_after = 0.45
    errors = classify_decision_errors(make_taxonomy_context(engine=engine, concepts=[]))
    assert DecisionErrorType.ADVANTAGE_CONVERSION in only_types(errors)


def test_unknown_is_reported_rather_than_guessed():
    from tests.test_llm import build_evidence

    engine = build_evidence().engine
    engine.expected_score_before = 0.55
    engine.expected_score_after = 0.42
    engine.played_line_san = ["Nf6", "a3"]
    engine.best_line_san = ["g6", "a3"]
    errors = classify_decision_errors(
        make_taxonomy_context(engine=engine, concepts=[], severity=Severity.INACCURACY)
    )
    assert only_types(errors) == {DecisionErrorType.UNKNOWN}
    assert errors[0].confidence <= 0.5


def test_at_most_three_errors_are_reported():
    ctx = make_taxonomy_context(
        concepts=[
            ("removal_of_defender", 0.95),
            ("hanging_piece", 0.9),
            ("mating_threat", 0.95),
            ("piece_activity", 0.5),
            ("undeveloped_pieces", 0.5),
        ],
        phase=GamePhase.OPENING,
    )
    errors = classify_decision_errors(ctx)
    assert 1 <= len(errors) <= 3
    confidences = [error.confidence for error in errors]
    assert confidences == sorted(confidences, reverse=True)


def test_taxonomy_never_confidently_claims_without_evidence():
    ctx = make_taxonomy_context(concepts=[])
    for error in classify_decision_errors(ctx):
        assert error.confidence <= 0.85


# ------------------------------------------------------------------ profile


def make_event(
    *,
    error: str,
    severity: str = "blunder",
    loss: float = 0.4,
    game_id: str = "g1",
    phase: str = "middlegame",
    concept: str = "hanging_piece",
    move_number: int = 20,
) -> dict:
    return {
        "game_id": game_id,
        "ply": move_number * 2,
        "move_number": move_number,
        "san": "Nf6",
        "severity": severity,
        "phase": phase,
        "expected_score_loss": loss,
        "primary_error": error,
        "primary_error_confidence": 0.8,
        "decision_error_tags": [error],
        "concept_tags": [concept],
        "is_critical": True,
        "created_at": None,
        "one_liner_zh": "测试",
        "opponent": "Beta",
        "fen": "8/8/8/8/8/8/8/K6k w - - 0 1",
        "solution_san": "g6",
    }


def make_profile_input(**overrides) -> ProfileInput:
    data = ProfileInput()
    data.total_games = overrides.pop("total_games", 3)
    data.total_player_moves = overrides.pop("total_player_moves", 90)
    data.average_loss = overrides.pop("average_loss", 0.09)
    data.severity_counts = overrides.pop("severity_counts", {"blunder": 2, "mistake": 3, "inaccuracy": 4})
    data.mistake_events = overrides.pop("mistake_events", [])
    data.phase_counts = overrides.pop("phase_counts", [])
    data.concept_counts = overrides.pop("concept_counts", [])
    data.game_trend = overrides.pop("game_trend", [])
    for key, value in overrides.items():
        setattr(data, key, value)
    return data


def test_profile_with_no_data_stays_honest():
    profile = build_profile(make_profile_input(total_games=0, mistake_events=[], severity_counts={}))
    assert profile.total_games == 0
    assert profile.weaknesses == []
    assert profile.trend.available is False
    assert "还没有分析过对局" in profile.sample_size_note_zh


def test_profile_shares_and_confidence_bands_for_a_small_sample():
    events = [
        make_event(error="forcing_moves_not_checked", game_id="g1"),
        make_event(error="forcing_moves_not_checked", game_id="g2"),
        make_event(error="hanging_piece", game_id="g2"),
    ]
    profile = build_profile(make_profile_input(mistake_events=events, total_games=2))

    top = profile.weaknesses[0]
    assert top.error_type is DecisionErrorType.FORCING_MOVES_NOT_CHECKED
    assert top.event_count == 2
    assert top.games == 2
    assert top.share == pytest.approx(2 / 3, abs=0.01)
    assert top.confidence == "insufficient"
    assert top.statement_zh.startswith("目前观察到")
    assert "你的稳定弱点" not in top.statement_zh
    assert top.examples and top.examples[0].san == "Nf6"
    assert "样本太少" in profile.sample_size_note_zh


def test_profile_reaches_medium_confidence_with_enough_data():
    events = [
        make_event(error="forcing_moves_not_checked", game_id="g{}".format(index))
        for index in range(16)
    ]
    profile = build_profile(make_profile_input(mistake_events=events, total_games=9))
    top = profile.weaknesses[0]
    assert top.confidence == "medium"
    assert top.statement_zh.startswith("从数据看")


def test_profile_share_only_counts_major_mistakes():
    events = [
        make_event(error="hanging_piece", severity="blunder"),
        make_event(error="piece_activity", severity="inaccuracy"),
    ]
    profile = build_profile(make_profile_input(mistake_events=events, total_games=2))
    hanging = next(w for w in profile.weaknesses if w.error_type is DecisionErrorType.HANGING_PIECE)
    activity = next(w for w in profile.weaknesses if w.error_type is DecisionErrorType.PIECE_ACTIVITY)
    assert hanging.share == pytest.approx(1.0)
    assert activity.share == pytest.approx(0.0)
    assert "还没有造成重大失误" in activity.statement_zh


def test_profile_phase_breakdown_and_concepts():
    events = [
        make_event(error="hanging_piece", phase="opening"),
        make_event(error="hanging_piece", phase="endgame", game_id="g2"),
    ]
    profile = build_profile(
        make_profile_input(
            mistake_events=events,
            total_games=2,
            phase_counts=[
                {"phase": "opening", "events": 1, "average_loss": 0.4},
                {"phase": "endgame", "events": 1, "average_loss": 0.2},
            ],
            concept_counts=[{"concept": "hanging_piece", "count": 2}],
        )
    )
    assert {phase.phase for phase in profile.phases} == {
        GamePhase.OPENING,
        GamePhase.MIDDLEGAME,
        GamePhase.ENDGAME,
    }
    assert profile.top_concepts[0].concept is ConceptType.HANGING_PIECE
    assert profile.top_concepts[0].label_zh == "悬子（无保护）"


def test_trend_needs_enough_games():
    few = [
        {"game_id": "g{}".format(i), "created_at": None, "average_loss": 0.1, "problems": 1, "blunders": 0, "label": "x"}
        for i in range(4)
    ]
    profile = build_profile(make_profile_input(game_trend=few))
    assert profile.trend.available is False
    assert "样本不足以判断趋势" in profile.trend.statement_zh

    many = [
        {
            "game_id": "g{}".format(i),
            "created_at": None,
            "average_loss": 0.30 if i < 3 else 0.10,
            "problems": 2,
            "blunders": 1,
            "label": "x",
        }
        for i in range(6)
    ]
    profile = build_profile(make_profile_input(game_trend=many))
    assert profile.trend.available is True
    assert profile.trend.direction == "improving"
    assert profile.trend.recent_average_loss == pytest.approx(0.10, abs=0.001)
    assert profile.trend.earlier_average_loss == pytest.approx(0.30, abs=0.001)


# ------------------------------------------------------------ 线路演示（后端展开）


def test_walk_line_returns_positions_after_each_move():
    from analysis.lines import walk_line

    walk = walk_line(
        chess.STARTING_FEN,
        ["e2e4", "e7e5", "g1f3"],
        "best",
        "测试线路",
    )
    assert [step.san for step in walk.steps] == ["e4", "e5", "Nf3"]
    assert [step.mover.value for step in walk.steps] == ["white", "black", "white"]
    assert walk.steps[-1].fen_after.startswith("rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2")
    assert walk.complete is True
    assert walk.start_fen == chess.STARTING_FEN


def test_walk_line_stops_at_an_illegal_move_and_says_so():
    from analysis.lines import walk_line

    walk = walk_line(chess.STARTING_FEN, ["e2e4", "e7e5", "e2e4"], "best", "坏线路")
    assert [step.san for step in walk.steps] == ["e4", "e5"]
    assert walk.complete is False


def test_walk_line_detects_checkmate():
    from analysis.lines import walk_line

    # 学者将杀：走完整条线路就是以将杀结束
    walk = walk_line(
        "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4",
        ["h5f7"],
        "played",
        "实战线路",
    )
    assert walk.ends_in_mate is True
    assert walk.steps[0].san == "Qxf7#"


# --------------------------------------------------------------- rendering


def test_concept_phrase_is_specific_for_defender_removal():
    concept = DetectedConcept(
        type=ConceptType.REMOVAL_OF_DEFENDER,
        confidence=0.9,
        squares=["f4", "e1"],
        pieces=["Bf4", "Re1"],
        metadata={"vacated_square": "f4", "undefended_piece": "Re1"},
    )
    phrase = concept_phrase_zh(concept)
    assert "f4" in phrase and "Re1" in phrase


def test_discovered_attack_phrase_uses_whole_square_names():
    """回归测试：曾经把拼接后的字符串当成列表索引，输出过「闪击：5 让出线路后 d 被攻击」。"""
    concept = DetectedConcept(
        type=ConceptType.DISCOVERED_ATTACK,
        confidence=0.7,
        pieces=["Ba6"],
        squares=["d3", "b5"],
        metadata={"side": "opponent"},
    )
    phrase = concept_phrase_zh(concept)
    assert "d3" in phrase and "b5" in phrase
    assert "闪击" in phrase


def test_deflection_phrase_uses_whole_square_names():
    concept = DetectedConcept(
        type=ConceptType.DEFLECTION,
        confidence=0.8,
        squares=["e2", "d5"],
        metadata={},
    )
    phrase = concept_phrase_zh(concept)
    assert "d5" in phrase


def test_concept_phrase_falls_back_to_the_chinese_label():
    concept = DetectedConcept(type=ConceptType.ISOLATED_PAWN, confidence=0.5, squares=["d4"])
    assert "孤兵" in concept_phrase_zh(concept)


def test_key_facts_include_engine_numbers_and_the_recommendation():
    from tests.test_llm import build_evidence

    evidence = build_evidence()
    facts = key_facts_zh(evidence.engine, evidence.concepts)
    joined = " ".join(facts)
    assert "引擎推荐" in joined
    assert "g6" in joined
    assert "期望得分" in joined


def test_one_liner_uses_the_primary_decision_error():
    from tests.test_llm import build_evidence
    from models.evidence import DecisionError

    evidence = build_evidence(concepts=("removal_of_defender",))
    evidence.decision_errors = [
        DecisionError(
            type=DecisionErrorType.DEFENDER_REMOVED,
            confidence=0.9,
            rationale="test",
            supporting_concepts=[ConceptType.REMOVAL_OF_DEFENDER],
        )
    ]
    line = one_liner_zh(evidence)
    assert "防守" in line


def test_one_liner_is_honest_when_no_motif_was_detected():
    from tests.test_llm import build_evidence

    evidence = build_evidence(concepts=())
    evidence.decision_errors = []
    assert "没有检测到可靠的战术 motif" in one_liner_zh(evidence)


def test_move_label_marks_blunders_with_double_question_marks():
    from tests.test_llm import build_evidence

    evidence = build_evidence()
    label = move_label_zh(evidence)
    assert label.startswith("3. Nf6??")
    assert "严重失误" in label


# ---------------------------------------------------------------- fallback


def test_rule_explanation_is_chinese_and_reusable():
    from tests.test_llm import build_evidence
    from models.evidence import DecisionError

    evidence = build_evidence(concepts=("mating_threat", "hanging_piece"))
    evidence.decision_errors = [
        DecisionError(
            type=DecisionErrorType.FORCING_MOVES_NOT_CHECKED,
            confidence=0.9,
            rationale="test",
            supporting_concepts=[ConceptType.MATING_THREAT],
        )
    ]
    explanation = fallback.build_rule_explanation(evidence)

    assert explanation.summary
    assert "Nf6" in explanation.summary
    assert explanation.general_lesson == ERROR_LESSON_ZH[DecisionErrorType.FORCING_MOVES_NOT_CHECKED]
    assert "1." in explanation.better_thinking_process
    assert explanation.confidence > 0
    # The explanation must never claim a concept that was not detected.
    assert "pin" not in explanation.concept_tags


def test_rule_explanation_reports_missing_evidence_instead_of_inventing_it():
    from tests.test_llm import build_evidence

    evidence = build_evidence(concepts=())
    evidence.decision_errors = []
    explanation = fallback.build_rule_explanation(evidence)
    assert "没有检测到可靠的战术 motif" in explanation.likely_human_error
    assert explanation.confidence <= 0.4


def test_rule_game_summary_groups_repeated_errors():
    events = [
        {"decision_error_tags": ["forcing_moves_not_checked"], "severity": "blunder"},
        {"decision_error_tags": ["forcing_moves_not_checked"], "severity": "mistake"},
        {"decision_error_tags": ["hanging_piece"], "severity": "blunder"},
    ]
    summary = fallback.build_rule_summary(events)
    assert "未检查对手的强制手" in summary.summary
    assert summary.main_patterns[0].startswith("未检查对手的强制手")
    assert summary.practice_advice
    assert summary.confidence <= 0.6


def test_rule_game_summary_for_a_clean_game():
    summary = fallback.build_rule_summary([])
    assert "没有出现" in summary.summary
    assert summary.confidence <= 0.5


# ------------------------------------------- 档案：置信区间 / 趋势 / 时间维度


def test_weakness_carries_a_confidence_interval():
    """百分比必须带区间：3/5 和 30/50 的占比一样，可信度差得远。"""
    events = [make_event(error="hanging_piece", game_id="g{}".format(i)) for i in range(3)]
    events += [make_event(error="king_safety", game_id="g{}".format(i)) for i in range(7)]
    profile = build_profile(
        make_profile_input(total_games=10, mistake_events=events, severity_counts={"blunder": 10})
    )
    top = next(item for item in profile.weaknesses if item.error_type.value == "king_safety")
    assert top.event_count == 7
    assert top.share == pytest.approx(0.7)
    # 7/10 的 95% Wilson 区间约 (0.40, 0.89)：界面要把这个宽度显示出来
    assert top.share_low == pytest.approx(0.397, abs=0.01)
    assert top.share_high == pytest.approx(0.892, abs=0.01)
    assert top.share_low < top.share < top.share_high


def test_weakness_records_phase_mix_and_seen_range():
    events = [
        make_event(error="hanging_piece", game_id="g1", phase="opening"),
        make_event(error="hanging_piece", game_id="g2", phase="endgame"),
        make_event(error="hanging_piece", game_id="g3", phase="endgame"),
    ]
    profile = build_profile(
        make_profile_input(total_games=3, mistake_events=events, severity_counts={"blunder": 3})
    )
    top = profile.weaknesses[0]
    assert top.by_phase == {"opening": 1, "endgame": 2}
    assert top.trend.available is False  # 3 局还不够判断趋势
    assert "样本不足" in top.trend.statement_zh


def test_trend_needs_enough_games_and_says_so():
    events = [make_event(error="hanging_piece", game_id="g{}".format(i)) for i in range(12)]
    profile = build_profile(
        make_profile_input(
            total_games=12,
            mistake_events=events,
            severity_counts={"blunder": 12},
            game_trend=[{"game_id": "g{}".format(i), "player_moves": 20} for i in range(12)],
        )
    )
    top = profile.weaknesses[0]
    # 12 局 × 20 手 = 每半 6 局 120 手，刚好够
    assert top.trend.available is True
    assert top.trend.compared_types == 1
    # 只检验一个类型时不收紧，如实写 0.05
    assert top.trend.significance_level == 0.05


def test_trend_tightens_the_threshold_when_many_types_are_tested():
    """同时检验多个错误类型会放大假阳性，门槛要按 Bonferroni 收紧并写在结果里。"""
    events = []
    for index in range(12):
        events.append(make_event(error="hanging_piece", game_id="g{}".format(index)))
        events.append(make_event(error="king_safety", game_id="g{}".format(index)))
    profile = build_profile(
        make_profile_input(
            total_games=12,
            mistake_events=events,
            severity_counts={"blunder": len(events)},
            game_trend=[{"game_id": "g{}".format(i), "player_moves": 20} for i in range(12)],
        )
    )
    assert len(profile.weaknesses) == 2
    for weakness in profile.weaknesses:
        assert weakness.trend.compared_types == 2
        assert weakness.trend.significance_level == pytest.approx(0.025)
    # 校正这件事要写进方法说明里，别让用户以为门槛还是 0.05
    assert "Bonferroni" in profile.evidence_note_zh


def test_trend_detects_a_real_improvement():
    """前半段每局都有这类失误，后半段几乎没有了 → 应该敢说"在变少"。"""
    games = ["g{}".format(i) for i in range(10)]
    events = [make_event(error="hanging_piece", game_id=game) for game in games[:5] for _ in range(4)]
    events += [make_event(error="hanging_piece", game_id=games[5])]
    profile = build_profile(
        make_profile_input(
            total_games=10,
            mistake_events=events,
            severity_counts={"blunder": len(events)},
            game_trend=[{"game_id": game, "player_moves": 120} for game in games],
        )
    )
    top = profile.weaknesses[0]
    assert top.trend.available is True
    assert top.trend.direction == "improving"
    assert top.trend.late_rate < top.trend.early_rate
    assert "在变少" in top.trend.statement_zh


def test_trend_refuses_to_call_noise_a_change():
    """前后各 2 次 vs 1 次这种差别必须写成"没有明显差别"。"""
    games = ["g{}".format(i) for i in range(10)]
    events = [make_event(error="hanging_piece", game_id=games[0]), make_event(error="hanging_piece", game_id=games[1])]
    events += [make_event(error="hanging_piece", game_id=games[5])]
    profile = build_profile(
        make_profile_input(
            total_games=10,
            mistake_events=events,
            severity_counts={"blunder": len(events)},
            game_trend=[{"game_id": game, "player_moves": 120} for game in games],
        )
    )
    top = profile.weaknesses[0]
    assert top.trend.available is True
    assert top.trend.direction == "flat"
    assert "没有明显差别" in top.trend.statement_zh


def test_time_dimension_and_next_focus_on_the_profile():
    events = [
        make_event(error="hanging_piece", game_id="g{}".format(index), severity="blunder")
        for index in range(5)
    ]
    events[0].update({"clock_seconds": 12.0, "time_pressure": True})
    events[1].update({"clock_seconds": 200.0, "time_pressure": False})
    profile = build_profile(
        make_profile_input(
            total_games=6,
            mistake_events=events,
            severity_counts={"blunder": 5},
            game_trend=[
                {"game_id": "g{}".format(i), "player_moves": 30, "speed": "blitz"} for i in range(6)
            ],
            time_control_counts=[
                {"speed": "blitz", "games": 4, "problems": 6, "average_loss": 0.12},
                {"speed": "bullet", "games": 2, "problems": 8, "average_loss": 0.2},
            ],
            clocked_problem_moves=2,
            problems_under_pressure=1,
        )
    )
    # 逐手时钟：2 个能判断，其中 1 个紧张
    assert profile.clocked_problem_moves == 2
    assert profile.problems_under_pressure == 1
    assert profile.under_time_pressure_share == pytest.approx(0.5)
    assert "1 个（50%）发生在时间紧张时" in profile.clock_note_zh

    # 时限分档按快慢排序，并给出每局问题密度
    assert [item.speed for item in profile.time_controls] == ["bullet", "blitz"]
    bullet = profile.time_controls[0]
    assert bullet.label_zh == "子弹"
    assert bullet.problems_per_game == 4.0

    # 先改哪一件：要有样本支撑才敢推荐，且必须带上练法
    assert profile.next_focus is not None
    assert profile.next_focus.error_type.value == "hanging_piece"
    assert "先改这一件" in profile.next_focus.statement_zh
    assert profile.next_focus.drill_zh

    # 方法说明必须写清楚分母和区间（只检验一个类型时不需要提多重比较校正）
    assert "95% Wilson 区间" in profile.evidence_note_zh
    assert "Bonferroni" not in profile.evidence_note_zh


def test_no_clocks_means_no_time_claim():
    profile = build_profile(
        make_profile_input(
            mistake_events=[make_event(error="hanging_piece", game_id="g1")],
            severity_counts={"blunder": 1},
            clocked_problem_moves=0,
            problems_under_pressure=0,
        )
    )
    assert profile.under_time_pressure_share is None
    assert "没有逐步剩余时间" in profile.clock_note_zh
    assert "Include clock times" in profile.clock_note_zh
