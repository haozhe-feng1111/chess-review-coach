#!/usr/bin/env node
/**
 * Frontend ↔ backend contract check.
 *
 * Runs a real analysis against a running backend and asserts that every field the UI
 * reads is present with the right shape. This exists because the frontend types are
 * hand-written: without a browser in CI, this is what catches a renamed or dropped
 * field before it becomes a blank screen.
 *
 * Usage (backend must be running):
 *   node scripts/check-api-contract.mjs [apiBase]
 */

const API = (process.argv[2] ?? process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const PGN = `[Event "合约检查"]
[White "Contract"]
[Black "Check"]
[Result "1-0"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0`;

let failures = 0;
let checks = 0;

function check(path, value, predicate, label) {
  checks += 1;
  const ok = predicate(value);
  if (!ok) {
    failures += 1;
    console.error(`  ✗ ${path}: ${label} (got ${JSON.stringify(value)?.slice(0, 120)})`);
  }
  return ok;
}

const isString = (v) => typeof v === "string";
const isNumber = (v) => typeof v === "number" && Number.isFinite(v);
const isBool = (v) => typeof v === "boolean";
const isArray = (v) => Array.isArray(v);
const nullableString = (v) => v === null || isString(v);

function section(title) {
  console.log(`\n${title}`);
}

async function get(path) {
  const response = await fetch(`${API}${path}`);
  if (!response.ok) throw new Error(`GET ${path} -> ${response.status}`);
  return response.json();
}

async function main() {
  section(`后端: ${API}`);

  const health = await get("/api/health");
  check("health.status", health.status, isString, "string");
  check("health.engine.available", health.engine?.available, isBool, "boolean");
  check("health.engine.name", health.engine?.name, nullableString, "string|null");
  check("health.llm.available", health.llm?.available, isBool, "boolean");
  check("health.pass1_depth", health.pass1_depth, isNumber, "number");
  if (!health.engine?.available) {
    console.error("  ✗ 引擎不可用，无法继续合约检查");
    process.exitCode = 1;
    return;
  }

  section("提交分析");
  const started = await fetch(`${API}/api/games/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pgn: PGN, player_color: "black", max_critical_moments: 3 }),
  }).then((r) => r.json());
  check("analyze.job_id", started.job_id, isString, "string");
  check("analyze.game_id", started.game_id, isString, "string");
  check("analyze.status.status", started.status?.status, isString, "string");

  let job = started.status;
  const deadline = Date.now() + 10 * 60 * 1000;
  while (job.status !== "completed" && job.status !== "failed") {
    if (Date.now() > deadline) throw new Error("分析超时");
    await new Promise((resolve) => setTimeout(resolve, 1500));
    job = (await get(`/api/jobs/${started.job_id}`)).job;
    check("job.progress", job.progress, isNumber, "number");
    check("job.message_zh", job.message_zh, isString, "string");
  }
  if (job.status !== "completed") throw new Error(`分析失败: ${job.message_zh} ${job.error ?? ""}`);
  console.log(`  分析完成，用时进度消息: ${job.message_zh}`);

  section("复盘结果 (GET /api/games/{id})");
  const { review } = await get(`/api/games/${started.game_id}`);
  check("review.game_id", review.game_id, isString, "string");
  check("review.white", review.white, isString, "string");
  check("review.black", review.black, isString, "string");
  check("review.result", review.result, isString, "string");
  check("review.player_color", review.player_color, (v) => v === "white" || v === "black", "white|black");
  check("review.opening", review.opening, nullableString, "string|null");
  check("review.moves", review.moves, isArray, "array");
  check("review.critical_moments", review.critical_moments, isArray, "array");
  check("review.counts", review.counts, (v) => isNumber(v?.blunder), "object with counts");
  check("review.average_expected_score_loss", review.average_expected_score_loss, isNumber, "number");
  check("review.engine.engine_name", review.engine?.engine_name, isString, "string");
  check("review.engine.elapsed_seconds", review.engine?.elapsed_seconds, isNumber, "number");
  check("review.llm_available", review.llm_available, isBool, "boolean");

  const move = review.moves[0];
  for (const field of ["ply", "move_number", "san", "uci", "fen_before", "fen_after"]) {
    check(`review.moves[0].${field}`, move?.[field], field === "san" || field === "uci" || field.startsWith("fen") ? isString : isNumber, "typed field");
  }
  check("review.moves[0].is_player_move", move?.is_player_move, isBool, "boolean");

  if (review.critical_moments.length === 0) {
    console.error("  ✗ 预期至少一个关键局面（这盘棋有一步送杀）");
    failures += 1;
  }

  for (const moment of review.critical_moments) {
    for (const field of ["ply", "move_number", "severity", "fen", "played_move_san", "one_liner_zh"]) {
      check(`critical.${field}`, moment[field], isString(moment[field]) || isNumber(moment[field]) ? (v) => v !== undefined && v !== null : isString, "present");
    }
    check("critical.solution_uci", moment.solution_uci, nullableString, "string|null");
    check("critical.reasons", moment.reasons, isArray, "array");
    const engine = moment.evidence?.engine;
    for (const field of [
      "evaluation_before",
      "evaluation_after",
      "expected_score_before",
      "expected_score_after",
      "expected_score_loss",
    ]) {
      check(`evidence.engine.${field}`, engine?.[field], isNumber, "number");
    }
    check("evidence.engine.wdl_before", engine?.wdl_before, (v) => isNumber(v?.win), "wdl");
    check("evidence.engine.best_move_san", engine?.best_move_san, nullableString, "string|null");
    check("evidence.engine.best_line_san", engine?.best_line_san, isArray, "array");
    check("evidence.engine.played_line_san", engine?.played_line_san, isArray, "array");
    check("evidence.engine.alternatives", engine?.alternatives, isArray, "array");
    check("evidence.concepts", moment.evidence?.concepts, isArray, "array");
    check("evidence.decision_errors", moment.evidence?.decision_errors, isArray, "array");
    check("evidence.position.fen", moment.evidence?.position?.fen, isString, "string");

    for (const concept of moment.evidence.concepts) {
      check("concept.type", concept.type, isString, "string");
      check("concept.confidence", concept.confidence, isNumber, "number");
      check("concept.squares", concept.squares, isArray, "array");
    }
    for (const error of moment.evidence.decision_errors) {
      check("decision_error.type", error.type, isString, "string");
      check("decision_error.confidence", error.confidence, isNumber, "number");
    }
  }

  section("解释 (GET /api/games/{id}/moments/{ply}/explanation)");
  const firstMoment = review.critical_moments[0];
  const { explanation } = await get(`/api/games/${started.game_id}/moments/${firstMoment.ply}/explanation`);
  check("explanation.source", explanation.source, (v) => v === "llm" || v === "rules", "llm|rules");
  check("explanation.model", explanation.model, nullableString, "string|null");
  check("explanation.grounded", explanation.grounded, isBool, "boolean");
  check("explanation.validation_warnings", explanation.validation_warnings, isArray, "array");
  for (const field of [
    "summary",
    "what_happened",
    "why_it_matters",
    "better_thinking_process",
    "general_lesson",
  ]) {
    check(`explanation.explanation.${field}`, explanation.explanation?.[field], (v) => isString(v) && v.length > 0, "non-empty string");
  }
  check("explanation.explanation.confidence", explanation.explanation?.confidence, isNumber, "number");
  check("explanation.concept_tags", explanation.explanation?.concept_tags, isArray, "array");

  section("整盘总结 (GET /api/games/{id}/summary)");
  const { summary } = await get(`/api/games/${started.game_id}/summary`);
  check("summary.source", summary.source, (v) => v === "llm" || v === "rules", "llm|rules");
  check("summary.explanation.summary", summary.explanation?.summary, (v) => isString(v) && v.length > 0, "non-empty");
  check("summary.explanation.main_patterns", summary.explanation?.main_patterns, isArray, "array");
  check("summary.explanation.practice_advice", summary.explanation?.practice_advice, isArray, "array");

  section("档案 (GET /api/profile)");
  const profile = await get("/api/profile");
  check("profile.total_games", profile.total_games, isNumber, "number");
  check("profile.total_player_moves", profile.total_player_moves, isNumber, "number");
  check("profile.average_expected_score_loss", profile.average_expected_score_loss, isNumber, "number");
  check("profile.weaknesses", profile.weaknesses, isArray, "array");
  check("profile.phases", profile.phases, isArray, "array");
  check("profile.top_concepts", profile.top_concepts, isArray, "array");
  check("profile.trend", profile.trend, (v) => isBool(v?.available), "object with available");
  check("profile.trend_points", profile.trend_points, isArray, "array");
  check("profile.sample_size_note_zh", profile.sample_size_note_zh, (v) => isString(v) && v.length > 0, "non-empty");
  for (const weakness of profile.weaknesses) {
    check("weakness.label_zh", weakness.label_zh, isString, "string");
    check("weakness.share", weakness.share, isNumber, "number");
    check("weakness.confidence", weakness.confidence, isString, "string");
    check("weakness.statement_zh", weakness.statement_zh, (v) => isString(v) && v.length > 0, "non-empty");
    check("weakness.examples", weakness.examples, isArray, "array");
  }
  for (const phase of profile.phases) {
    check("phase.label_zh", phase.label_zh, isString, "string");
    check("phase.share", phase.share, isNumber, "number");
  }

  section("对局列表 (GET /api/games)");
  const { games } = await get("/api/games");
  check("games", games, isArray, "array");
  check("games[0].game_id", games[0]?.game_id, isString, "string");
  check("games[0].created_at", games[0]?.created_at, nullableString, "string|null");

  console.log(
    `\n${failures === 0 ? "✓" : "✗"} 合约检查结束：${checks - failures}/${checks} 项通过`,
  );
  process.exitCode = failures === 0 ? 0 : 1;
}

main().catch((error) => {
  console.error(`\n✗ 合约检查失败: ${error.message}`);
  process.exitCode = 1;
});
