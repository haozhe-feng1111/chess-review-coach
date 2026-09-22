#!/usr/bin/env python3
"""Refresh per-game metadata that lives outside the engine analysis.

Two things are recovered here, both **offline** (no engine, no network):

1. **时限** — from the PGN header (``[TimeControl "300+3"]``), which is already stored
   with every game. Needed because games analyzed before this metadata existed have an
   empty column, and an empty column silently drops them from the profile's
   "按时限看问题密度" section.
2. **主要失误原因** — from the stored review's ``decision_error_tags`` (already ranked by
   confidence). Needed because ``primary_error`` used to be read only from the handful of
   *critical* positions, so most mistakes were aggregated as "原因不明确".

Clock data (``[%clk]``) is deliberately **not** backfilled: it only exists in the PGN
text, so if the imported PGN had no clock comments there is nothing to recover — the
profile says "没有逐步剩余时间" instead of guessing.

    python scripts/backfill_game_metadata.py --dry-run
    python scripts/backfill_game_metadata.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from analysis.timecontrol import parse_time_control, speed_label_zh  # noqa: E402
from models.enums import DecisionErrorType  # noqa: E402
from models.review import GameReview  # noqa: E402
from storage.db import Database, get_database  # noqa: E402
from storage.models import Game, MistakeEvent  # noqa: E402


def backfill_time_controls(database: Database, dry_run: bool) -> Tuple[int, int, Counter]:
    """Fill the time-control columns from the stored PGN headers."""
    seen = 0
    updated = 0
    speeds: Counter = Counter()

    with database.session() as session:
        for game in session.execute(select(Game).order_by(Game.created_at)).scalars():
            seen += 1
            control = parse_time_control(game.headers or {})
            if control is None:
                continue
            speeds[control.speed] += 1
            if (
                game.time_control_speed == control.speed
                and game.time_control_base == control.base_seconds
                and game.time_control_increment == control.increment_seconds
            ):
                continue
            updated += 1
            if dry_run:
                continue
            game.time_control_speed = control.speed
            game.time_control_base = control.base_seconds
            game.time_control_increment = control.increment_seconds
        if dry_run:
            session.rollback()

    return seen, updated, speeds


def backfill_primary_errors(database: Database, dry_run: bool) -> Tuple[int, int]:
    """Re-derive ``primary_error`` for every stored mistake from the saved review.

    ``decision_error_tags`` on each move is already ordered by confidence (the taxonomy
    ranks them), so the first tag is the primary cause. Reviews analyzed before the
    ``primary_error`` field existed simply did not carry it.
    """
    scanned = 0
    updated = 0

    with database.session() as session:
        for game in session.execute(select(Game)).scalars():
            if not game.review_json:
                continue
            review = GameReview.model_validate(game.review_json)
            by_ply = {}
            for move in review.moves:
                if not move.is_player_move or not move.decision_error_tags:
                    continue
                by_ply[move.ply] = (
                    move.primary_error or move.decision_error_tags[0],
                    move.primary_error_confidence,
                )
            if not by_ply:
                continue

            for event in session.execute(
                select(MistakeEvent).where(MistakeEvent.game_id == game.id)
            ).scalars():
                scanned += 1
                found = by_ply.get(event.ply)
                if found is None:
                    continue
                error_type, confidence = found
                value = (
                    error_type.value
                    if isinstance(error_type, DecisionErrorType)
                    else str(error_type)
                )
                if event.primary_error == value and (
                    confidence is None or event.primary_error_confidence == confidence
                ):
                    continue
                updated += 1
                if dry_run:
                    continue
                event.primary_error = value
                if confidence is not None:
                    event.primary_error_confidence = confidence
        if dry_run:
            session.rollback()

    return scanned, updated


def main() -> int:
    parser = argparse.ArgumentParser(description="从已存的数据补齐对局元信息（不跑引擎）")
    parser.add_argument("--database-url", default=None, help="默认用 .env 里的配置")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写数据库")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    database = get_database(args.database_url)
    print("数据库：{}".format(database.engine.url))

    seen, updated, speeds = backfill_time_controls(database, args.dry_run)
    print("")
    print("[时限] 扫描对局 {} 盘，需要更新 {} 盘".format(seen, updated))
    if speeds:
        detail = "、".join(
            "{} {}".format(speed_label_zh(speed), count)
            for speed, count in speeds.most_common()
        )
        print("        已识别：{}".format(detail))
    else:
        print("        这些对局的 PGN 里没有 TimeControl 头，无法分档。")

    scanned, events = backfill_primary_errors(database, args.dry_run)
    print("[主因] 扫描失误 {} 条，需要更新 {} 条".format(scanned, events))

    if args.dry_run:
        print("")
        print("--dry-run：没有写入数据库。")
    print(
        "注意：逐手时钟（%clk）不在这个脚本范围内——它只存在于 PGN 原文里，"
        "导入时没有就补不回来。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
