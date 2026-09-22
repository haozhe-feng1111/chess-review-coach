"""Environment-driven application settings.

Chess-judgment thresholds (severity buckets, criticality weights, phase cutoffs)
deliberately live in ``analysis/thresholds.py`` instead of here: those are *tuning*
parameters for the analysis pipeline, while this module only wires up the runtime
environment (paths, engine resources, API credentials).

Every setting has a safe default so the app runs with no configuration at all.
A missing ``DEEPSEEK_API_KEY`` is an explicitly supported mode: the app then shows
Stockfish review + deterministic concept explanations only.
"""

import os
from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
DEFAULT_STOCKFISH_PATH = BACKEND_DIR / "engine" / "bin" / "stockfish"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Stockfish ---
    # Leave empty to auto-detect: backend/engine/bin/stockfish, then $PATH.
    stockfish_path: str = ""
    # 0 => auto (half of the available cores, clamped to engine_max_threads).
    stockfish_threads: int = 0
    engine_max_threads: int = 4
    stockfish_hash_mb: int = 64
    engine_startup_timeout: float = 20.0

    # --- Two-pass analysis budget (see analysis/pipeline.py) ---
    # Pass 1: cheap sweep over every position, MultiPV=1.
    pass1_depth: int = 12
    # Optional node cap for pass 1. When > 0 it replaces the depth limit, which makes
    # total runtime far more predictable across positions of varying complexity.
    pass1_nodes: int = 0
    # Pass 2: deep re-analysis of the handful of critical positions only.
    pass2_depth: int = 18
    pass2_multipv: int = 3
    pass2_nodes: int = 0
    # Hard per-position ceiling; a position that exceeds it is reported as partial.
    position_timeout: float = 25.0

    # --- Review composition ---
    max_critical_moments: int = 5

    # --- Puzzle practice ---
    # 给"玩家实际走的那一步"打分用的深度。比复盘浅：这只是即时反馈，
    # 而且每答一次就要跑一次搜索，本地机器上得等得起。
    grade_depth: int = 12

    # --- LLM (DeepSeek, OpenAI-compatible) ---
    deepseek_api_key: str = ""
    # 需要代理才能访问外网时填这里（httpx 读的是环境变量，所以下面会导出过去）。
    https_proxy: str = ""
    http_proxy: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_timeout: float = 60.0
    llm_temperature: float = 0.2
    llm_max_tokens: int = 2000

    # --- Storage ---
    # Relative paths resolve against the backend directory.
    database_url: str = "sqlite:///data/chess_coach.db"

    # --- HTTP ---
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def llm_enabled(self) -> bool:
        """The app must work without an LLM key; this is the single source of truth."""
        return bool(self.deepseek_api_key.strip())

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_stockfish_path(self) -> Optional[Path]:
        """Locate the engine: explicit setting, then the vendored binary, then $PATH."""
        import shutil

        if self.stockfish_path.strip():
            candidate = Path(self.stockfish_path).expanduser()
            return candidate if candidate.exists() else None
        if DEFAULT_STOCKFISH_PATH.exists():
            return DEFAULT_STOCKFISH_PATH
        which = shutil.which("stockfish")
        return Path(which) if which else None

    @property
    def resolved_database_url(self) -> str:
        """Turn the default relative SQLite URL into an absolute one under backend/."""
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            raw = self.database_url[len(prefix) :]
            if raw == ":memory:" or raw.startswith("/"):
                return self.database_url
            return prefix + str(BACKEND_DIR / raw)
        return self.database_url

    @property
    def effective_threads(self) -> int:
        import os

        if self.stockfish_threads > 0:
            return self.stockfish_threads
        return max(1, min(self.engine_max_threads, (os.cpu_count() or 2) // 2))


settings = Settings()


def _export_proxy_to_environment(settings: "Settings") -> None:
    """把 .env 里的代理设置导出成环境变量。

    ``httpx`` 只认 ``HTTPS_PROXY`` / ``HTTP_PROXY`` 环境变量，不会去读我们的 .env，
    所以这里显式同步一次；已经存在的环境变量优先，不会被 .env 覆盖。
    """
    if settings.https_proxy and not os.environ.get("HTTPS_PROXY"):
        os.environ["HTTPS_PROXY"] = settings.https_proxy
        os.environ.setdefault("https_proxy", settings.https_proxy)
    if settings.http_proxy and not os.environ.get("HTTP_PROXY"):
        os.environ["HTTP_PROXY"] = settings.http_proxy
        os.environ.setdefault("http_proxy", settings.http_proxy)


_export_proxy_to_environment(settings)
