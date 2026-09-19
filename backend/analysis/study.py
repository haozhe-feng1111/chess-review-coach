"""Legal, appendable variation trees, independent of the recorded review."""

import io

import chess
import chess.pgn

from models.workbench import SaveStudy, StudyMove


def initial_study(game) -> dict:
    review = game.review_json or {}
    recorded = review.get("moves", [])
    root_fen = recorded[0]["fen_before"] if recorded else game.headers.get("FEN", chess.STARTING_FEN)
    moves = []
    parent = "root"
    for index, move in enumerate(recorded, 1):
        node_id = f"m{index}"
        moves.append(StudyMove(id=node_id, parent_id=parent, uci=move["uci"]))
        parent = node_id
    # Keep variations supplied in an imported PGN as well as the recorded mainline.
    pgn = chess.pgn.read_game(io.StringIO(game.pgn or ""))
    if pgn and pgn.board().fen() == root_fen:
        edges = {(m.parent_id, m.uci): m.id for m in moves}
        pending = [(pgn, "root")]
        while pending and len(moves) < 2000:
            node, parent_id = pending.pop()
            for child in node.variations:
                edge = (parent_id, child.move.uci())
                node_id = edges.get(edge)
                if not node_id:
                    node_id = f"p{len(moves)+1}"
                    moves.append(StudyMove(id=node_id, parent_id=parent_id, uci=child.move.uci()))
                    edges[edge] = node_id
                pending.append((child, node_id))
    return materialize(root_fen, moves, len(recorded), "root", 0)


def materialize(root_fen, moves, original_count, selected_id, revision):
    root = chess.Board(root_fen)
    if not root.is_valid():
        raise ValueError("棋谱的初始局面无效。")
    nodes = [{"id": "root", "parent_id": None, "uci": "", "san": "起始局面", "fen": root.fen(),
              "ply": 0, "move_number": root.fullmove_number, "color": "white" if root.turn else "black", "original_ply": 0}]
    boards = {"root": root}
    plies = {"root": 0}
    edges = set()
    for item in moves:
        if item.id in boards or item.parent_id not in boards or (item.parent_id, item.uci) in edges:
            raise ValueError("分支存在重复走法、重复编号或缺少父节点。")
        board = boards[item.parent_id].copy(stack=False)
        move = chess.Move.from_uci(item.uci)
        if move not in board.legal_moves:
            raise ValueError("分支包含非法走法。")
        san, number, color = board.san(move), board.fullmove_number, "white" if board.turn else "black"
        board.push(move)
        ply = plies[item.parent_id] + 1
        original = ply if ply <= original_count and item.id == f"m{ply}" else None
        nodes.append({**item.model_dump(), "san": san, "fen": board.fen(), "ply": ply,
                      "move_number": number, "color": color, "original_ply": original})
        boards[item.id], plies[item.id] = board, ply
        edges.add((item.parent_id, item.uci))
    if selected_id not in boards:
        raise ValueError("选中的分支不存在。")
    return {"root_fen": root.fen(), "revision": revision, "selected_id": selected_id, "nodes": nodes}


def validate_study(game, request: SaveStudy) -> dict:
    initial = initial_study(game)
    originals = [n for n in initial["nodes"] if n["original_ply"]]
    by_id = {m.id: m for m in request.moves}
    for node in originals:
        item = by_id.get(node["id"])
        if not item or item.parent_id != node["parent_id"] or item.uci != node["uci"]:
            raise ValueError("实战主线需要保留；试走请添加分支。")
    # Stable mainline first also prevents an alternate move becoming the exported game.
    main_ids = {node["id"] for node in originals}
    ordered = [by_id[n["id"]] for n in originals] + [m for m in request.moves if m.id not in main_ids]
    if len(by_id) != len(request.moves) or any(m.id.startswith("m") and m.id[1:].isdigit() and m.id not in main_ids for m in request.moves):
        raise ValueError("分支编号无效。")
    return materialize(initial["root_fen"], ordered, len(originals), request.selected_id, request.revision + 1)


def export_study(game, study):
    pgn = chess.pgn.Game()
    pgn.headers.update(game.headers or {})
    pgn.setup(chess.Board(study["root_fen"]))
    pgn.headers["Result"] = game.result or "*"
    nodes = {"root": pgn}
    for node in study["nodes"][1:]:
        nodes[node["id"]] = nodes[node["parent_id"]].add_variation(chess.Move.from_uci(node["uci"]))
    return pgn.accept(chess.pgn.StringExporter(headers=True, variations=True, comments=True))
