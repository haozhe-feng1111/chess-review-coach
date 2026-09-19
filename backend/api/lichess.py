"""Lichess login and the human-game explorer API."""

from functools import lru_cache
from html import escape
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from config import settings
from explorer.auth import LichessAuth
from explorer.client import LichessExplorer
from models.explorer import ExplorerQuery, ExplorerResponse
from storage.db import get_database

router = APIRouter(prefix="/api/lichess")
COOKIE = "lichess_oauth_state"


@lru_cache(maxsize=1)
def auth() -> LichessAuth:
    return LichessAuth(Path(settings.lichess_token_file), settings.lichess_api_token)


@lru_cache(maxsize=1)
def explorer() -> LichessExplorer:
    return LichessExplorer(get_database(), auth(), timeout=settings.lichess_timeout)


@router.post("/explorer", response_model=ExplorerResponse)
def explore(query: ExplorerQuery, service: LichessExplorer = Depends(explorer)):
    return service.query(query)


@router.get("/status")
def status(account: LichessAuth = Depends(auth)):
    return {"connected": bool(account.token()), "configured_by_environment": bool(account.configured_token)}


@router.get("/connect")
def connect(request: Request, account: LichessAuth = Depends(auth)):
    if request.url.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise HTTPException(400, "浏览器授权仅支持本机地址；服务器部署请使用 LICHESS_API_TOKEN。")
    state, url = account.begin(str(request.url_for("lichess_callback")), settings.lichess_login_hint)
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(COOKIE, state, max_age=600, httponly=True, samesite="lax", path="/api/lichess")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/callback", name="lichess_callback")
def callback(request: Request, state: str = "", code: str = "", account: LichessAuth = Depends(auth)):
    # Parameters have already been parsed; do not put the authorization code in
    # Uvicorn's access log when it later formats this request's ASGI scope.
    request.scope["query_string"] = b""
    try:
        account.finish(state, request.cookies.get(COOKIE), code)
        message = "Lichess 已连接。返回复盘页，点击真人统计面板的刷新即可。"
        status_code = 200
    except (ValueError, OSError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "无法保存授权，请检查本地数据目录的权限后重试。"
        status_code = 400
    back = settings.cors_origin_list[0] if settings.cors_origin_list else "http://localhost:3000"
    response = HTMLResponse(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>Lichess 连接</title><body><h1>Lichess 连接</h1><p>' + escape(message) + '</p><p><a href="'
        + escape(back, quote=True) + '">返回复盘教练</a></p><p><a href="/api/lichess/connect">重新连接</a></p></body></html>',
        status_code=status_code,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "Content-Security-Policy": "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"},
    )
    response.delete_cookie(COOKIE, path="/api/lichess")
    return response


@router.delete("/connection")
def disconnect(request: Request, account: LichessAuth = Depends(auth)):
    if request.headers.get("origin") not in settings.cors_origin_list:
        raise HTTPException(403, "只能从本机复盘界面断开连接。")
    if account.configured_token:
        raise HTTPException(409, "当前令牌由环境变量配置，请移除 LICHESS_API_TOKEN 后重启后端。")
    account.disconnect()
    return {"connected": False}
