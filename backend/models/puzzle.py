"""题目（puzzle）模型。

题目**只从已经分析过的对局里提取**，而且只提取有强制走法的局面：

* ``MATE`` —— 引擎在走子前的局面里看到了强制将杀（``mate_before > 0``），
* ``MATERIAL`` —— 引擎推荐线路能在若干步内净赚到子力（默认至少 2 分），并且走完是明显优势。

不做"改善局面"这类抽象题：它的答案无法客观界定，会破坏这个项目"结论必须可核实"的前提。
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from models.enums import Color, ConceptType, GamePhase, PuzzleKind, Severity


class Puzzle(BaseModel):
    """一条题目：一个局面 + 一个可核实的答案。"""

    id: str
    game_id: str
    ply: int
    move_number: int
    player_color: Color
    phase: GamePhase
    kind: PuzzleKind

    #: 题目局面（走子之前）——做题时看到的就是它。
    fen: str
    #: 答案第一步与完整线路（都来自引擎，不是我们自己算的）。
    solution_uci: str
    solution_san: str
    solution_line_uci: List[str] = Field(default_factory=list)
    solution_line_san: List[str] = Field(default_factory=list)

    #: MATE 题：将杀步数；MATERIAL 题：净赚的子力（兵为单位）。
    mate_in: Optional[int] = None
    material_gain: Optional[int] = None

    #: 主题取自同一次分析里检测到的概念（叉子/牵制/底线……），没有就是 unknown。
    theme: Optional[ConceptType] = None
    theme_label_zh: str = "未分类"

    #: 当时实际走的那一手，以及它的严重程度。
    played_san: str
    severity: Severity
    difficulty: str = "medium"

    concept_tags: List[ConceptType] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class PuzzleStep(BaseModel):
    """题目线路里的一步（含走完之后的局面，前端据此播放）。"""

    uci: str
    san: str
    fen_after: str
    mover: Color


class PuzzleDetail(BaseModel):
    """练习时需要的全部数据：题目 + 展开好的线路。"""

    puzzle: Puzzle
    steps: List[PuzzleStep] = Field(default_factory=list)
    opponent_replies: List[PuzzleStep] = Field(default_factory=list)
    #: 题目局面下的**全部合法着法**（UCI）。前端只允许下这些着法，
    #: 棋规判定留在 python-chess 这一侧，前端永远不自己判合法性。
    legal_moves: List[str] = Field(default_factory=list)


class PuzzleAttemptResult(BaseModel):
    """一次作答的判定结果。

    判定分两层：答案对不对（和引擎推荐着法是否一致），以及**这一步到底亏不亏**
    （用引擎对"他走的这一步"和"引擎自己的着法"分别算期望得分再相减）。
    第二层才是真正有用的反馈：答案之外的着法也可能一样好，而"猜中答案"不等于下得好。
    """

    puzzle_id: str
    correct: bool
    played_uci: Optional[str] = None
    played_san: Optional[str] = None
    best_san: Optional[str] = None
    is_engine_move: bool = False
    #: engine / answer_only（引擎不可用时只能按答案比对，并如实说明）
    graded_by: str = "answer_only"
    verdict: str = "unknown"
    verdict_zh: str = ""
    expected_score_loss: Optional[float] = None
    played_expected_score: Optional[float] = None
    best_expected_score: Optional[float] = None
    attempts: int = 0
    solved: int = 0


class PuzzleStats(BaseModel):
    total: int = 0
    mate: int = 0
    material: int = 0
    attempted: int = 0
    solved: int = 0
    solved_rate: float = 0.0
    by_theme: List[dict] = Field(default_factory=list)
