"""FastAPI application.

Run from the ``backend`` directory:

    uvicorn api.main:app --reload --port 8000

The app is intentionally small: one service object owns the engine, the database and the
coach, and the routes are thin. No authentication, no cloud dependencies — this is a
local-first tool.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import router
from api.lichess import router as lichess_router
from api.workbench import router as workbench_router, shutdown_live
from api.service import get_service
from config import settings
from engine.errors import EngineError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    service = get_service()
    engine = service.engine_health()
    if engine["available"]:
        logger.info("Stockfish ready: %s (%s)", engine["name"], engine["path"])
    else:
        logger.warning("Stockfish unavailable: %s", engine["error"])
    logger.info(
        "LLM: %s",
        "DeepSeek configured" if service.coach.llm_available else "not configured (rules-only mode)",
    )
    yield
    shutdown_live()
    service.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Chess Review Coach API",
        version="0.1.0",
        description=(
            "Explainable chess review: Stockfish decides what is objectively good, "
            "deterministic analysis extracts verifiable concepts, and an LLM explains "
            "the verified facts in Chinese."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(lichess_router)
    app.include_router(workbench_router)

    @app.exception_handler(EngineError)
    async def engine_error_handler(_request: Request, exc: EngineError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": exc.message, "detail": exc.detail, "hint_zh": exc.hint_zh},
        )

    @app.get("/")
    def root() -> dict:
        return {
            "name": "chess-review-coach",
            "api": "/api",
            "docs": "/docs",
        }

    return app


app = create_app()
