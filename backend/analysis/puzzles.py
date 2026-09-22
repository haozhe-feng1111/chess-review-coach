"""从已分析的对局里提取题目。

只提取**有强制走法**的局面，两条规则都是确定性的、可核实的：

* **强制将杀**：走子前的局面里引擎看到了杀棋（``mate_before > 0``），而玩家没走出来
  （走完之后这个杀棋没了）。
* **赚取子力**：引擎推荐线路在若干步内净赚到子力（默认至少 2 分），且走完是明显优势。

两条都要求"玩家当时没走对"——题目来自你自己的漏着，而不是你已经找到的着法。

**刻意不做"改善局面"这类题目**：那类题目的正确答案无法客观界定，做进去就等于让系统
去猜"哪一步更好看"，和这个项目"每条结论都要能追溯到引擎或确定性事实"的前提冲突。
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import chess

from analysis.board import find_move_by_uci, material_balance
from analysis.thresholds import THRESHOLDS, AnalysisThresholds
from concepts.scan import loose_pieces
from models.enums import ConceptType, GamePhase, PuzzleKind, Severity, concept_label_zh
from models.puzzle import Puzzle
from models.review import GameReview, MoveAssessment

logger = logging.getLogger(__name__)

#: 赚子题至少要有这么多净收益（兵为单位）。2 = 一个轻子，或者两个兵。
MIN_MATERIAL_GAIN = 2

#: 赚子题要求的优势下限（期望得分）。低于这个值说明"赚了子但还是劣势"，
#: 那多半是弃子后的补偿，不适合当题目。
MIN_WINNING_EXPECTED_SCORE = 0.70

#: 战术必须在引擎线路的前若干步内兑现，否则可能只是漫长的兑换，不像"题目"。
#: 10 = 题目局面之后，玩家自己走的前 5 步之内必须把子力真正赚到手
#: （第 1、3、5、7、9 步是玩家走，2、4、6、8、10 步是引擎给的对手最佳应手）。
#: 放宽到 10 是因为对局里的组合常常是"先弃后取"：两三步之内只是交换，
#: 真正落袋在第 4、5 步。再长就不像一道题，而像整盘棋的转写了。
MAX_PLIES_TO_GAIN = 10

#: 主题优先级：越靠前越像"这道题考的是什么"。
THEME_PRIORITY = (
    "back_rank_weakness",
    "fork",
    "pin",
    "skewer",
    "discovered_attack",
    "double_attack",
    "removal_of_defender",
    "deflection",
    "overloaded_defender",
    "mating_threat",
    "trapped_piece",
    "intermediate_move",
    "missed_forcing_move",
    "missed_check",
    "exchange_sacrifice",
)


@dataclass
class MaterialSwing:
    """引擎线路上的子力净收益。

    ``gain`` 是**真的赚到手、并且扛过了对手下一手**的最大净收益（兵为单位），
    ``first_gain_ply`` 是第一次"账面就达到 gain、而且对手应手之后还有 gain"的步数
    （从 1 开始；没有就是 ``None``）。截断答案线路时用的就是它，所以报出来的数
    和线路末尾的账面是一回事。

    为什么不是"线路上出现过的最大差值"：那个差值可能只是过路财神。例如
    ``Bb7 Rxc7 Bxc7`` 走到第 3 步时白方账面上多 4 分，可对手下一手就把象吃回来，
    实际只赚了一个兵。用"必须扛过对手应手"来定义，账面上写多少就是真的有多少。
    """

    gain: int
    first_gain_ply: Optional[int]


def material_swing(fen: str, line_uci: List[str], player_is_white: bool) -> MaterialSwing:
    """沿引擎线路走一遍，算出玩家净赚到多少子、以及是第几步赚到的。

    线路走不完（出现非法着法）就停在能走到的位置——宁可不给结论，也不猜。
    """
    board = chess.Board(fen)
    start = material_balance(board, player_is_white)
    #: balances[0] 是起点（差值恒为 0），balances[i] 是走完第 i 步之后的净收益
    balances = [0]
    for uci in line_uci:
        move = find_move_by_uci(board, uci)
        if move is None:
            break
        board.push(move)
        balances.append(material_balance(board, player_is_white) - start)

    # 每一步"至少能保住多少"：自己走完时的账面值，与对手应手之后的账面值，取小的那个
    secured: List[int] = []
    for index in range(1, len(balances)):
        reply = balances[index + 1] if index + 1 < len(balances) else balances[index]
        secured.append(min(balances[index], reply))

    gain = max(secured) if secured else 0
    if gain <= 0:
        return MaterialSwing(gain=0, first_gain_ply=None)

    # 第一次"账面就达到这个数、而且对手吃回去也还剩这么多"的那一步。
    # 这样报出的步数和线路截断的位置是一致的：截到这一步，账面上正好就是 gain 分。
    first_ply = next(
        (
            index
            for index, value in enumerate(secured, start=1)
            if value == gain and balances[index] == gain
        ),
        None,
    )
    return MaterialSwing(gain=gain, first_gain_ply=first_ply)


def is_forcing_first_move(fen: str, uci: str, min_threat: int = MIN_MATERIAL_GAIN) -> bool:
    """答案的第一步是不是"具体的"：将军、吃子，或者立刻威胁白吃子。

    这一条专门用来挡掉"靠慢慢调子三步之后赢"的局面。那种局面的"正确答案"换一步走
    未必更差，做成题目只会骗人；而将军、吃子和直接威胁吃子都是可以核实的事实。

    判据是"走完之后对手是否面对一个可核实的子力威胁"，而不是"这个威胁是不是这一步
    新造出来的"：前者才是让对手必须应手的原因。而"到底赚不赚得到"由线路那条规则
    （``material_swing`` + 引擎线路）负责，两条规则各管一段。

    只看**第一步**是有意的：一个两步组合的第二步可以是安静的（叉子就是典型——
    第一步制造威胁，第二步才吃），所以要求整条线路每步都强制就太严了。
    """
    board = chess.Board(fen)
    move = find_move_by_uci(board, uci)
    if move is None:
        return False
    if board.is_capture(move) or board.gives_check(move):
        return True

    after = board.copy(stack=False)
    after.push(move)
    # 走完之后轮到对手：对手有哪个子会被"刚走完的这一方"白吃，就说明这一步带着威胁。
    for loose in loose_pieces(after, color=after.turn).values():
        if loose.best_see >= min_threat:
            return True
    return False


def _difficulty(kind: PuzzleKind, mate_in: Optional[int], gain: Optional[int], line_length: int) -> str:
    """难度只能是启发式的，这里如实按"要算多深"来分档。"""
    if kind is PuzzleKind.MATE:
        steps = mate_in or line_length
        if steps <= 1:
            return "easy"
        if steps <= 3:
            return "medium"
        return "hard"
    # 难度按"要看几步"分档：一步吃到（吃子/将军）算简单，五步以内算中等
    if line_length <= 2:
        return "easy" if (gain or 0) >= 3 else "medium"
    if line_length <= 6:
        return "medium"
    return "hard"


def _shortened(line_uci: List[str], line_san: List[str], plies: int) -> Tuple[List[str], List[str]]:
    """把线路截到"胜负已分"的那一步。

    不截断的话，一道"白吃一车"的题会带着后面十几步残局技术一起给出来，
    既不像题，也让人看不清关键点在哪儿。截到兑现的那一手为止，是整个战术本身。
    """
    if plies <= 0 or plies >= len(line_uci):
        return list(line_uci), list(line_san)
    return list(line_uci[:plies]), list(line_san[:plies])


def extract_puzzles(
    review: GameReview, thresholds: AnalysisThresholds = THRESHOLDS
) -> List[Puzzle]:
    """从一盘已分析的棋里提取所有符合条件的题目。"""
    puzzles: List[Puzzle] = []

    for move in review.moves:
        if not move.is_player_move:
            continue
        # 你当时就走对了 → 这不是给你的题目
        if move.is_engine_best:
            continue
        if not move.best_line_uci or not move.best_move_uci:
            continue

        player_is_white = move.color.value == "white"

        # ---- 规则一：强制将杀 ----
        if move.mate_before is not None and move.mate_before > 0:
            # 玩家换成别的着法之后，如果仍然有强制将杀，说明他也找到了杀棋（只是不是引擎那一条）
            still_mating = move.mate_after is not None and move.mate_after > 0
            if not still_mating:
                theme_type, theme_label = _pick_theme_from_move(move)
                # 答案线路只到将杀那一手为止（第 1、3、5… 手是自己走）
                mate_plies = 2 * move.mate_before - 1
                line_uci, line_san = _shortened(
                    move.best_line_uci, move.best_line_san, mate_plies
                )
                puzzles.append(
                    Puzzle(
                        id=puzzle_id(review.game_id, move.ply),
                        game_id=review.game_id,
                        ply=move.ply,
                        move_number=move.move_number,
                        player_color=move.color,
                        phase=_phase_of(review, move),
                        kind=PuzzleKind.MATE,
                        fen=move.fen_before,
                        solution_uci=move.best_move_uci,
                        solution_san=move.best_move_san or move.best_move_uci,
                        solution_line_uci=line_uci,
                        solution_line_san=line_san,
                        mate_in=move.mate_before,
                        theme=theme_type,
                        theme_label_zh=theme_label,
                        played_san=move.san,
                        severity=move.severity or Severity.MISTAKE,
                        difficulty=_difficulty(
                            PuzzleKind.MATE, move.mate_before, None, len(line_uci)
                        ),
                        concept_tags=list(move.concept_tags),
                        created_at=review.created_at,
                    )
                )
            # 有强制将杀的局面一律按将杀题处理：要么收成题目，要么（他已经找到别的杀法）跳过，
            # 不再往下走"赚子"规则。
            continue

        # ---- 规则二：赚取子力 ----
        if move.severity is None or not move.severity.is_problem:
            # 只有"确实走亏了"的着法才当题目；已经赢定的漏着不算
            continue
        if move.expected_score_before is None or move.expected_score_before < MIN_WINNING_EXPECTED_SCORE:
            continue

        swing = material_swing(move.fen_before, move.best_line_uci, player_is_white)
        if swing.gain < MIN_MATERIAL_GAIN:
            continue
        if swing.first_gain_ply is None or swing.first_gain_ply > MAX_PLIES_TO_GAIN:
            continue
        # 答案必须是个"具体"的着法（将军/吃子/直接威胁吃子），否则不是题
        if not is_forcing_first_move(move.fen_before, move.best_move_uci):
            continue

        theme_type, theme_label = _pick_theme_from_move(move)
        # 答案线路只到"子力真的赚到手"那一手为止
        line_uci, line_san = _shortened(
            move.best_line_uci, move.best_line_san, swing.first_gain_ply or 0
        )
        puzzles.append(
            Puzzle(
                id=puzzle_id(review.game_id, move.ply),
                game_id=review.game_id,
                ply=move.ply,
                move_number=move.move_number,
                player_color=move.color,
                phase=_phase_of(review, move),
                kind=PuzzleKind.MATERIAL,
                fen=move.fen_before,
                solution_uci=move.best_move_uci,
                solution_san=move.best_move_san or move.best_move_uci,
                solution_line_uci=line_uci,
                solution_line_san=line_san,
                material_gain=swing.gain,
                theme=theme_type,
                theme_label_zh=theme_label,
                played_san=move.san,
                severity=move.severity,
                difficulty=_difficulty(
                    PuzzleKind.MATERIAL, None, swing.gain, len(line_uci)
                ),
                concept_tags=list(move.concept_tags),
                created_at=review.created_at,
            )
        )

    return puzzles


def puzzle_id(game_id: str, ply: int) -> str:
    """稳定 id：同一盘棋的同一手永远对应同一条题目（重跑分析不会产生重复题目）。"""
    return "{}:{}".format(game_id, ply)


def _phase_of(review: GameReview, move: MoveAssessment) -> GamePhase:
    for moment in review.critical_moments:
        if moment.ply == move.ply:
            return moment.phase
    # 非关键局面没有单独记录阶段，按回合数粗略归到开局/中局，避免瞎猜
    return GamePhase.OPENING if move.move_number <= 10 else GamePhase.MIDDLEGAME


def _pick_theme_from_move(move: MoveAssessment) -> Tuple[Optional[ConceptType], str]:
    """题目的主题取自同一个局面的概念标签（关键局面才有；没有就标未分类）。"""
    if not move.concept_tags:
        return None, "未分类"
    values = {tag.value for tag in move.concept_tags}
    for value in THEME_PRIORITY:
        if value in values:
            concept = ConceptType(value)
            return concept, concept_label_zh(concept)
    concept = move.concept_tags[0]
    return concept, concept_label_zh(concept)


def extract_all(reviews: List[GameReview], **kwargs) -> List[Puzzle]:
    """批量提取（用于给已有对局补题目）。"""
    result: List[Puzzle] = []
    for review in reviews:
        result.extend(extract_puzzles(review, **kwargs))
    return result
