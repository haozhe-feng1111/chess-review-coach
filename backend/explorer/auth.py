"""Public-client OAuth with PKCE. Credentials stay in the local backend."""

import base64
import hashlib
import json
import os
import secrets
import threading
import tempfile
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx

CLIENT_ID = "chess-review-coach"


class LichessAuth:
    def __init__(self, token_file: Path, configured_token: str = "", transport=None):
        self.token_file = token_file
        self.configured_token = configured_token.strip()
        self.transport = transport
        self._pending = {}
        self._lock = threading.Lock()

    def token(self) -> str:
        if self.configured_token:
            return self.configured_token
        try:
            data = json.loads(self.token_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return ""
            if data.get("expires_at", 0) <= time.time():
                return ""
            token = data.get("access_token")
            return token if isinstance(token, str) else ""
        except (OSError, ValueError, TypeError):
            return ""

    def begin(self, redirect_uri: str, login_hint: str = ""):
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(32)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        with self._lock:
            self._pending = {key: value for key, value in self._pending.items() if value[2] > time.time()}
            if len(self._pending) >= 32:
                self._pending.pop(next(iter(self._pending)))
            self._pending[state] = (verifier, redirect_uri, time.time() + 600)
        params = dict(response_type="code", client_id=CLIENT_ID, redirect_uri=redirect_uri,
                      code_challenge_method="S256", code_challenge=challenge, state=state)
        if login_hint:
            params["username"] = login_hint
        return state, "https://lichess.org/oauth?" + urlencode(params)

    def finish(self, state: str, cookie_state: Optional[str], code: str) -> None:
        if not cookie_state or not secrets.compare_digest(state, cookie_state):
            raise ValueError("授权校验失败，请重新点击连接 Lichess。")
        with self._lock:
            pending = self._pending.pop(state, None)
        if not pending or pending[2] <= time.time() or not code:
            raise ValueError("授权已过期或被取消，请重新连接。")
        verifier, redirect_uri, _ = pending
        try:
            with httpx.Client(timeout=15, transport=self.transport, follow_redirects=False) as client:
                response = client.post("https://lichess.org/api/token", data={
                    "grant_type": "authorization_code", "client_id": CLIENT_ID,
                    "code": code, "code_verifier": verifier, "redirect_uri": redirect_uri,
                })
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("invalid token response")
                token = payload.get("access_token")
                token_type = payload.get("token_type")
                if not isinstance(token, str) or not token or not isinstance(token_type, str) or token_type.lower() != "bearer":
                    raise ValueError("invalid token response")
                expires = int(payload.get("expires_in", 31536000))
                if expires <= 0:
                    raise ValueError("expired token")
        except (httpx.HTTPError, ValueError, TypeError):
            # Never return remote bodies, codes or tokens in an error or a log.
            raise ValueError("Lichess 授权未完成，请检查网络后重新连接。") from None
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp = tempfile.mkstemp(dir=self.token_file.parent, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"access_token": token, "expires_at": time.time() + expires}, handle)
            os.replace(temp, self.token_file)
        finally:
            Path(temp).unlink(missing_ok=True)

    def disconnect(self) -> None:
        self.token_file.unlink(missing_ok=True)
