"""Enumerations shared across every layer, plus their Chinese UI labels.

Internal identifiers stay English (they are stored in SQLite and sent to the LLM);
Chinese labels live here so the UI never has to hardcode translations and so a
second language can be added without touching analysis code.
"""

from enum import Enum
from typing import Dict


class Color(str, Enum):
    WHITE = "white"
    BLACK = "black"


class Severity(str, Enum):
    """Move quality buckets. Boundaries live in analysis/thresholds.py."""

    BEST = "best"
    EXCELLENT = "excellent"
    GOOD = "good"
    INACCURACY = "inaccuracy"
    MISTAKE = "mistake"
    BLUNDER = "blunder"

    @property
    def is_problem(self) -> bool:
        """True for moves a player should actually review."""
        return self in (Severity.INACCURACY, Severity.MISTAKE, Severity.BLUNDER)


class GamePhase(str, Enum):
    OPENING = "opening"
    MIDDLEGAME = "middlegame"
    ENDGAME = "endgame"


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ConceptType(str, Enum):
    """Objective, deterministically detectable chess concepts.

    Adding a concept means adding an enum member plus one detector module; nothing
    else in the pipeline needs to change.
    """

    # --- concrete / tactical ---
    HANGING_PIECE = "hanging_piece"
    UNDEFENDED_PIECE = "undefended_piece"
    ATTACKED_PIECE = "attacked_piece"
    MATERIAL_LOSS = "material_loss"
    MISSED_CAPTURE = "missed_capture"
    MISSED_CHECK = "missed_check"
    MISSED_FORCING_MOVE = "missed_forcing_move"
    FORK = "fork"
    PIN = "pin"
    SKEWER = "skewer"
    DISCOVERED_ATTACK = "discovered_attack"
    DOUBLE_ATTACK = "double_attack"
    OVERLOADED_DEFENDER = "overloaded_defender"
    DEFLECTION = "deflection"
    REMOVAL_OF_DEFENDER = "removal_of_defender"
    BACK_RANK_WEAKNESS = "back_rank_weakness"
    MATING_THREAT = "mating_threat"
    TRAPPED_PIECE = "trapped_piece"
    INTERMEDIATE_MOVE = "intermediate_move"
    EXCHANGE_SACRIFICE = "exchange_sacrifice"

    # --- strategic / contextual ---
    KING_SAFETY_DETERIORATION = "king_safety_deterioration"
    PAWN_STRUCTURE_DAMAGE = "pawn_structure_damage"
    ISOLATED_PAWN = "isolated_pawn"
    DOUBLED_PAWN = "doubled_pawn"
    PASSED_PAWN = "passed_pawn"
    WEAK_SQUARE = "weak_square"
    UNDEVELOPED_PIECES = "undeveloped_pieces"
    QUEEN_MOVED_REPEATEDLY = "queen_moved_repeatedly"
    PIECE_ACTIVITY = "piece_activity"
    OPEN_FILE = "open_file"
    SEMI_OPEN_FILE = "semi_open_file"
    BISHOP_PAIR = "bishop_pair"
    MATERIAL_IMBALANCE = "material_imbalance"


class DecisionErrorType(str, Enum):
    """The *human* decision failure behind a bad move, not the board consequence.

    Kept deliberately separate from ConceptType: "lost a bishop" (consequence) and
    "moved a defender without checking forcing moves" (decision error) are different
    claims and carry different evidence requirements.
    """

    FORCING_MOVES_NOT_CHECKED = "forcing_moves_not_checked"
    HANGING_PIECE = "hanging_piece"
    OPPONENT_THREAT_IGNORED = "opponent_threat_ignored"
    DEFENDER_REMOVED = "defender_removed"
    TACTICAL_CALCULATION = "tactical_calculation"
    PREMATURE_ATTACK = "premature_attack"
    KING_SAFETY = "king_safety"
    MATERIAL_JUDGMENT = "material_judgment"
    PIECE_ACTIVITY = "piece_activity"
    OPENING_DEVELOPMENT = "opening_development"
    ENDGAME_TECHNIQUE = "endgame_technique"
    ADVANTAGE_CONVERSION = "advantage_conversion"
    TIME_PRESSURE_UNKNOWN = "time_pressure_unknown"
    UNKNOWN = "unknown"


class PuzzleKind(str, Enum):
    """题目类型：只收集有强制走法的局面。

    刻意**不做**"改善局面"这类抽象题——那类题目的答案很难客观界定，
    而这个项目的前提是"每条结论都能追溯到引擎或确定性事实"。
    """

    MATE = "mate"          # 引擎看到强制将杀
    MATERIAL = "material"  # 引擎线路能净赚子力


PUZZLE_KIND_LABELS_ZH: Dict[PuzzleKind, str] = {
    PuzzleKind.MATE: "强制将杀",
    PuzzleKind.MATERIAL: "赚取子力",
}

PUZZLE_DIFFICULTY_LABELS_ZH: Dict[str, str] = {
    "easy": "简单",
    "medium": "中等",
    "hard": "困难",
}


class ExplanationSource(str, Enum):
    LLM = "llm"
    RULES = "rules"  # deterministic template fallback, used when no API key is set


SEVERITY_LABELS_ZH: Dict[Severity, str] = {
    Severity.BEST: "最佳",
    Severity.EXCELLENT: "优秀",
    Severity.GOOD: "良好",
    Severity.INACCURACY: "不够精确",
    Severity.MISTAKE: "失误",
    Severity.BLUNDER: "严重失误",
}

PHASE_LABELS_ZH: Dict[GamePhase, str] = {
    GamePhase.OPENING: "开局",
    GamePhase.MIDDLEGAME: "中局",
    GamePhase.ENDGAME: "残局",
}

COLOR_LABELS_ZH: Dict[Color, str] = {
    Color.WHITE: "白方",
    Color.BLACK: "黑方",
}

CONCEPT_LABELS_ZH: Dict[ConceptType, str] = {
    ConceptType.HANGING_PIECE: "悬子（无保护）",
    ConceptType.UNDEFENDED_PIECE: "无根子",
    ConceptType.ATTACKED_PIECE: "被攻击的子力",
    ConceptType.MATERIAL_LOSS: "丢子",
    ConceptType.MISSED_CAPTURE: "漏吃",
    ConceptType.MISSED_CHECK: "漏将",
    ConceptType.MISSED_FORCING_MOVE: "漏掉强制手",
    ConceptType.FORK: "叉子（双击）",
    ConceptType.PIN: "牵制",
    ConceptType.SKEWER: "串击",
    ConceptType.DISCOVERED_ATTACK: "闪击",
    ConceptType.DOUBLE_ATTACK: "双重攻击",
    ConceptType.OVERLOADED_DEFENDER: "防守子超载",
    ConceptType.DEFLECTION: "引离防守子",
    ConceptType.REMOVAL_OF_DEFENDER: "消除防守子",
    ConceptType.BACK_RANK_WEAKNESS: "底线弱点",
    ConceptType.MATING_THREAT: "杀棋威胁",
    ConceptType.TRAPPED_PIECE: "被困子力",
    ConceptType.INTERMEDIATE_MOVE: "中间着（过渡着）",
    ConceptType.EXCHANGE_SACRIFICE: "交换弃子",
    ConceptType.KING_SAFETY_DETERIORATION: "王安全下降",
    ConceptType.PAWN_STRUCTURE_DAMAGE: "兵形受损",
    ConceptType.ISOLATED_PAWN: "孤兵",
    ConceptType.DOUBLED_PAWN: "叠兵",
    ConceptType.PASSED_PAWN: "通路兵",
    ConceptType.WEAK_SQUARE: "弱格",
    ConceptType.UNDEVELOPED_PIECES: "子力未展开",
    ConceptType.QUEEN_MOVED_REPEATEDLY: "开局反复动后",
    ConceptType.PIECE_ACTIVITY: "子力活跃度",
    ConceptType.OPEN_FILE: "开放线",
    ConceptType.SEMI_OPEN_FILE: "半开放线",
    ConceptType.BISHOP_PAIR: "双象",
    ConceptType.MATERIAL_IMBALANCE: "子力不平衡",
}

DECISION_ERROR_LABELS_ZH: Dict[DecisionErrorType, str] = {
    DecisionErrorType.FORCING_MOVES_NOT_CHECKED: "未检查对手的强制手",
    DecisionErrorType.HANGING_PIECE: "把子力放在会被直接吃掉的位置",
    DecisionErrorType.OPPONENT_THREAT_IGNORED: "忽略了对手的威胁",
    DecisionErrorType.DEFENDER_REMOVED: "移动/消除防守子后出现战术漏洞",
    DecisionErrorType.TACTICAL_CALCULATION: "战术计算失误",
    DecisionErrorType.PREMATURE_ATTACK: "过早进攻",
    DecisionErrorType.KING_SAFETY: "王安全",
    DecisionErrorType.MATERIAL_JUDGMENT: "子力判断",
    DecisionErrorType.PIECE_ACTIVITY: "子力活跃度",
    DecisionErrorType.OPENING_DEVELOPMENT: "开局出子",
    DecisionErrorType.ENDGAME_TECHNIQUE: "残局技术",
    DecisionErrorType.ADVANTAGE_CONVERSION: "优势局面转换",
    DecisionErrorType.TIME_PRESSURE_UNKNOWN: "时间压力（无法判断）",
    DecisionErrorType.UNKNOWN: "原因不明确",
}


def concept_label_zh(concept: ConceptType) -> str:
    return CONCEPT_LABELS_ZH.get(concept, concept.value)


def decision_error_label_zh(error: DecisionErrorType) -> str:
    return DECISION_ERROR_LABELS_ZH.get(error, error.value)
