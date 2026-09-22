#!/usr/bin/env python3
"""Backfill the puzzle library from games that were analyzed before this feature existed.

Adding puzzles to the app does not require re-running Stockfish: every analyzed game is
stored as a serialized ``GameReview`` (``games.review_json``), and puzzle extraction is a
pure function over that review. So this script is offline, fast, and repeated runs are
safe (``save_puzzles`` replaces a game's puzzles wholesale and skips duplicate positions).

    python scripts/backfill_puzzles.py --dry-run    # 只统计，不写库
    python scripts/backfill_puzzles.py              # 真正写库
    python scripts/backfill_puzzles.py --game-id <id>

Puzzles are only ever extracted from the games you actually played, and only from
positions with a forcing continuation (forced mate or a forced material win).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from analysis.puzzles import extract_puzzles  # noqa: E402
from models.puzzle import Puzzle  # noqa: E402
from models.review import GameReview  # noqa: E402
from storage.db import Database  # noqa: E402
from storage.models import CriticalPosition, Game  # noqa: E402
from storage.repository import get_review, save_puzzles  # noqa: E402


def fill_mate_before_from_evidence(session, review: GameReview) -> int:
    """Recover ``mate_before`` for reviews saved before that field existed.

    The engine computed it at the time and it is still in
    ``critical_positions.evidence_json`` — the older ``GameReview`` simply did not
    carry the field, which would hide every forced-mate puzzle from the backfill.
    Re-reading it keeps the backfill offline instead of re-running Stockfish.
    """
    filled = 0
    rows = session.execute(
        select(CriticalPosition).where(CriticalPosition.game_id == review.game_id)
    ).scalars()
    by_ply = {}
    for row in rows:
        engine = (row.evidence_json or {}).get("engine") or {}
        mate = engine.get("mate_before")
        if isinstance(mate, int):
            by_ply[row.ply] = mate
    for move in review.moves:
        if move.mate_before is None and move.ply in by_ply:
            move.mate_before = by_ply[move.ply]
            filled += 1
    return filled


def game_ids(database: Database, only: Optional[str] = None) -> List[str]:
    with database.session() as session:
        query = select(Game.id).order_by(Game.created_at)
        if only:
            query = query.where(Game.id == only)
        return [row for row in session.execute(query).scalars()]


def backfill(
    database: Database, only: Optional[str], dry_run: bool
) -> Tuple[int, int, List[Puzzle], int]:
    """Returns (games scanned, puzzles stored, all puzzles found, moves enriched)."""
    scanned = 0
    stored = 0
    enriched = 0
    everything: List[Puzzle] = []

    for game_id in game_ids(database, only):
        with database.session() as session:
            review = get_review(session, game_id)
            if review is not None:
                enriched += fill_mate_before_from_evidence(session, review)
        if review is None:
            print("  跳过 {}：这盘棋只有摘要，没有完整复盘数据".format(game_id))
            continue

        puzzles = extract_puzzles(review)
        scanned += 1
        everything.extend(puzzles)

        if dry_run:
            continue
        with database.session() as session:
            stored += save_puzzles(session, puzzles, game_id)

        for puzzle in puzzles:
            detail = "将杀 {} 步".format(puzzle.mate_in) if puzzle.mate_in else "赚子 {} 分".format(
                puzzle.material_gain
            )
            print(
                "  {} 第 {} 回合 {}：{}（{}/{}，实战走的是 {}）".format(
                    game_id[:8],
                    puzzle.move_number,
                    puzzle.player_color.value,
                    puzzle.theme_label_zh,
                    puzzle.kind.value,
                    detail,
                    puzzle.played_san,
                )
            )

    return scanned, stored, everything, enriched


def main() -> int:
    parser = argparse.ArgumentParser(description="从已分析的对局里补出题目")
    parser.add_argument("--database-url", default=None, help="默认用 .env 里的配置")
    parser.add_argument("--game-id", default=None, help="只处理这一盘棋")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写数据库")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from storage.db import get_database

    database = get_database(args.database_url)
    print("数据库：{}".format(database.engine.url))

    scanned, stored, found, enriched = backfill(database, args.game_id, args.dry_run)

    by_kind = Counter(puzzle.kind.value for puzzle in found)
    by_theme = Counter(puzzle.theme_label_zh for puzzle in found)
    print("")
    print("扫描对局：{} 盘".format(scanned))
    if enriched:
        print("补齐 mate_before（老版本没存的字段，从证据里读回）：{} 手".format(enriched))
    print("找到题目：{} 道（将杀 {}，赚子 {}）".format(len(found), by_kind["mate"], by_kind["material"]))
    if by_theme:
        top = "、".join("{} {}".format(label, count) for label, count in by_theme.most_common(8))
        print("主题分布：{}".format(top))
    if args.dry_run:
        print("--dry-run：没有写入数据库。")
    else:
        print("已写入数据库：{} 条（重复局面会自动去重）。".format(stored))
    if not found:
        print(
            "没有找到有强制手段的漏着。这很正常：只有漏掉将杀或漏掉明确赚子的局面才会出题，"
            "一盘中局里这类局面通常只有几个。"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
