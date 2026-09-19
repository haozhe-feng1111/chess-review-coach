"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { API_BASE, ApiError, api, waitForJob } from "@/lib/api";
import { formatLoss, severityLabel, SEVERITY_BADGE } from "@/lib/labels";
import type { Color, GameListItem, HealthResponse, LLMTestResult } from "@/lib/types";

const SAMPLE_PGN = `[Event "示例对局"]
[White "示例白方"]
[Black "示例黑方"]
[Result "1-0"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0`;

type SideChoice = "auto" | Color;

export default function HomePage() {
  const router = useRouter();
  const [pgn, setPgn] = useState("");
  const [side, setSide] = useState<SideChoice>("auto");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<{ value: number; message: string } | null>(null);
  const [error, setError] = useState<{ message: string; hint?: string } | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [llmTest, setLlmTest] = useState<LLMTestResult | null>(null);
  const [llmTesting, setLlmTesting] = useState(false);
  const [games, setGames] = useState<GameListItem[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);

  const refreshGames = () => {
    api
      .games(20)
      .then(({ games: list }) => setGames(list))
      .catch(() => setGames([]));
  };

  // 只在 promise 回调里更新状态：effect 里同步 setState 会触发级联渲染。
  const checkHealth = useCallback(() => {
    api
      .health()
      .then((value) => {
        setHealth(value);
        setHealthError(false);
      })
      .catch(() => {
        setHealth(null);
        setHealthError(true);
      });
  }, []);

  useEffect(() => {
    checkHealth();
    refreshGames();
  }, [checkHealth]);

  const runLlmTest = async () => {
    setLlmTesting(true);
    setLlmTest(null);
    try {
      setLlmTest(await api.testLlm());
    } catch {
      setLlmTest({
        configured: false,
        ok: false,
        model: null,
        message_zh: "无法连接到后端服务，请先确认后端已经启动。",
        detail: null,
      });
    } finally {
      setLlmTesting(false);
    }
  };

  const backendReady = health !== null && health.engine.available;

  const startAnalysis = async () => {
    setError(null);
    if (!pgn.trim()) {
      setError({ message: "请先粘贴或上传 PGN。" });
      return;
    }
    setBusy(true);
    setProgress({ value: 0, message: "正在提交…" });
    try {
      const started = await api.analyze({
        pgn,
        player_color: side === "auto" ? null : side,
        max_critical_moments: 5,
      });
      if (started.status.status === "completed") {
        router.push(`/games/${started.game_id}`);
        return;
      }
      const job = await waitForJob(started.job_id, (status) =>
        setProgress({ value: status.progress, message: status.message_zh }),
      );
      if (job.status === "failed") {
        setError({ message: job.message_zh || "分析失败", hint: job.error ?? undefined });
        setProgress(null);
        return;
      }
      refreshGames();
      router.push(`/games/${started.game_id}`);
    } catch (caught: unknown) {
      if (caught instanceof ApiError) {
        setError({ message: caught.message, hint: caught.hintZh });
      } else {
        setError({ message: "分析失败，请稍后重试。" });
      }
      setProgress(null);
    } finally {
      setBusy(false);
    }
  };

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    const text = await file.text();
    setPgn(text);
    setError(null);
  };

  return (
    <div className="space-y-5">
      <section className="panel p-5">
        <h1 className="text-xl font-semibold">导入一盘棋</h1>
        <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
          Stockfish 在本机判断好坏，确定性分析提取可核实的证据，AI 只负责把已经确认的事实讲成人话。
          没有配置 DEEPSEEK_API_KEY 也能完整使用引擎复盘。
        </p>

        {health ? (
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <span className={`tag ${health.engine.available ? "tag-engine" : "tag-coach"}`}>
              引擎：{health.engine.available ? health.engine.name : "不可用"}
              {health.engine.available && health.engine.threads
                ? ` · ${health.engine.threads} 线程`
                : ""}
            </span>
            <span className={`tag ${health.llm.available ? "tag-coach" : ""}`}>
              AI 解释：{health.llm.available ? health.llm.model ?? "已配置" : "未配置（仅规则说明）"}
            </span>
            <span className="tag">
              分析配置：快速深度 {health.pass1_depth} / 关键局面深度 {health.pass2_depth}
            </span>
          </div>
        ) : null}

        {health ? (
          <div className="panel-soft mt-3 p-3">
            {llmTest ? (
              <p className={`text-xs ${llmTest.ok ? "text-emerald-300" : "text-amber-300"}`}>
                {llmTest.ok ? "✓ " : "· "}
                {llmTest.message_zh}
                {llmTest.model ? `（模型：${llmTest.model}）` : ""}
              </p>
            ) : (
              <p className="text-xs" style={{ color: "var(--muted)" }}>
                {health.llm.available
                  ? "已填写 DEEPSEEK_API_KEY。点下面的按钮会真实调用一次 DeepSeek，确认密钥和网络都没问题。"
                  : "未配置 DEEPSEEK_API_KEY：现在只显示引擎证据 + 规则模板说明，其余功能完整可用。"}
              </p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void runLlmTest()}
                disabled={llmTesting}
                className="rounded border px-3 py-1.5 text-xs"
                style={{ borderColor: "var(--border)" }}
              >
                {llmTesting ? "正在测试…" : "测试 AI 连接"}
              </button>
              <span className="text-xs" style={{ color: "var(--muted)" }}>
                配置步骤见 README 的「配置 DeepSeek API Key」一节
              </span>
            </div>
          </div>
        ) : null}

        {healthError ? (
          <div
            className="mt-3 rounded-lg border p-3 text-sm"
            style={{ borderColor: "#7f1d1d", background: "rgba(127,29,29,0.12)" }}
          >
            <p className="font-medium text-rose-300">连接不到分析后端，现在还无法分析棋局。</p>
            <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
              界面地址是 <span className="mono">{typeof window !== "undefined" ? window.location.origin : ""}</span>
              ，它在等后端 <span className="mono">{API_BASE}</span> 响应，但那边没有应答。
            </p>
            <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
              在项目根目录的终端里运行下面这一条命令即可（会同时启动后端和前端）：
            </p>
            <pre className="mono mt-1 overflow-x-auto rounded bg-black/40 p-2 text-xs">
./scripts/dev.sh
            </pre>
            <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
              只想单独启动后端：
              <span className="mono"> cd backend && ../.venv/bin/python -m uvicorn api.main:app --port 8000</span>
            </p>
            <button
              type="button"
              onClick={() => {
                setHealthError(false);
                checkHealth();
              }}
              className="mt-2 rounded border px-3 py-1 text-xs"
              style={{ borderColor: "var(--border)" }}
            >
              重试连接
            </button>
          </div>
        ) : null}

        {health && !health.engine.available ? (
          <div
            className="mt-3 rounded-lg border p-3 text-sm"
            style={{ borderColor: "#78350f", background: "rgba(120,53,15,0.12)" }}
          >
            <p className="font-medium text-amber-300">后端正常，但找不到 Stockfish 引擎。</p>
            <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
              {health.engine.error ? `原因：${health.engine.error}` : ""}
            </p>
            <pre className="mono mt-1 overflow-x-auto rounded bg-black/40 p-2 text-xs">
.venv/bin/python backend/scripts/install_stockfish.py
            </pre>
            <p className="text-xs" style={{ color: "var(--muted)" }}>
              或者安装系统版 Stockfish，并在 <span className="mono">.env</span> 里设置{" "}
              <span className="mono">STOCKFISH_PATH=/你的/路径/stockfish</span>，然后重启后端。
            </p>
          </div>
        ) : null}

        <div className="mt-4 space-y-3">
          <textarea
            value={pgn}
            onChange={(event) => setPgn(event.target.value)}
            placeholder="把 PGN 粘贴到这里…"
            rows={9}
            spellCheck={false}
            className="mono w-full rounded-lg border bg-transparent p-3 text-xs leading-relaxed outline-none focus:border-sky-500"
            style={{ borderColor: "var(--border)" }}
          />

          <div className="flex flex-wrap items-center gap-3">
            <input
              ref={fileInput}
              type="file"
              accept=".pgn,text/plain"
              className="hidden"
              onChange={(event) => void onFile(event.target.files?.[0])}
            />
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              className="rounded border px-3 py-1.5 text-sm"
              style={{ borderColor: "var(--border)" }}
            >
              上传 PGN 文件
            </button>
            <button
              type="button"
              onClick={() => {
                setPgn(SAMPLE_PGN);
                setSide("black");
              }}
              className="rounded border px-3 py-1.5 text-sm"
              style={{ borderColor: "var(--border)" }}
            >
              填入示例
            </button>
            <button
              type="button"
              onClick={() => setPgn("")}
              className="rounded border px-3 py-1.5 text-sm"
              style={{ borderColor: "var(--border)" }}
            >
              清空
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-sm">
            <span style={{ color: "var(--muted)" }}>我执哪一方：</span>
            {(
              [
                ["auto", "自动判断"],
                ["white", "白方"],
                ["black", "黑方"],
              ] as [SideChoice, string][]
            ).map(([value, label]) => (
              <label key={value} className="flex items-center gap-1.5">
                <input
                  type="radio"
                  name="side"
                  checked={side === value}
                  onChange={() => setSide(value)}
                />
                {label}
              </label>
            ))}
            <span className="text-xs" style={{ color: "var(--muted)" }}>
              自动判断会参考你以前导入过的棋手名；无法判断时会提示你手动选择。
            </span>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void startAnalysis()}
              disabled={busy || !backendReady}
              title={backendReady ? "" : "后端或引擎不可用，请先按上面的提示启动"}
              className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
            >
              {busy ? "分析中…" : backendReady ? "开始分析" : "暂时无法分析"}
            </button>
            {progress ? (
              <div className="flex-1">
                <div className="h-2 w-full overflow-hidden rounded-full ring-1 ring-slate-700">
                  <div
                    className="h-full bg-sky-500 transition-all"
                    style={{ width: `${Math.round(progress.value * 100)}%` }}
                  />
                </div>
                <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
                  {progress.message}（{Math.round(progress.value * 100)}%）
                </p>
              </div>
            ) : null}
          </div>

          {error ? (
            <div className="rounded-lg border p-3 text-sm" style={{ borderColor: "#7f1d1d" }}>
              <p className="text-rose-300">{error.message}</p>
              {error.hint ? (
                <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
                  {error.hint}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      </section>

      <section className="panel p-5">
        <h2 className="text-base font-semibold">最近分析的对局</h2>
        {games.length === 0 ? (
          <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
            还没有分析记录。导入一盘棋开始吧。
          </p>
        ) : (
          <div className="mt-3 divide-y" style={{ borderColor: "var(--border)" }}>
            {games.map((game) => (
              <div key={game.game_id} className="flex items-center justify-between gap-4 py-2">
                <div className="min-w-0">
                  <Link href={`/games/${game.game_id}`} className="truncate text-sm hover:underline">
                    {game.white} vs {game.black}
                  </Link>
                  <p className="text-xs" style={{ color: "var(--muted)" }}>
                    {game.result} · 你执{game.player_color === "white" ? "白" : "黑"}方
                    {game.opening ? ` · ${game.opening}` : ""} · {game.move_count} 个半回合
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2 text-xs">
                  {game.inaccuracies > 0 ? (
                    <span className={`rounded px-1.5 py-0.5 ring-1 ${SEVERITY_BADGE.inaccuracy}`}>
                      不够精确 {game.inaccuracies}
                    </span>
                  ) : null}
                  {game.mistakes > 0 ? (
                    <span className={`rounded px-1.5 py-0.5 ring-1 ${SEVERITY_BADGE.mistake}`}>
                      {severityLabel("mistake")} {game.mistakes}
                    </span>
                  ) : null}
                  {game.blunders > 0 ? (
                    <span className={`rounded px-1.5 py-0.5 ring-1 ${SEVERITY_BADGE.blunder}`}>
                      {severityLabel("blunder")} {game.blunders}
                    </span>
                  ) : null}
                  <span className="mono" style={{ color: "var(--muted)" }}>
                    {formatLoss(game.average_expected_score_loss)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
