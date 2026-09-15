"""암호를 확인하고 세션 쿠키를 발급한다.

암호 원문은 어디에도 저장하지 않는다. 환경변수에는 PBKDF2 해시만 있고,
검증 1회에 수백 밀리초가 걸리는 것이 무차별 대입에 대한 방어다.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from collector.auth import (  # noqa: E402
    issue_token,
    set_cookie_header,
    verify_password,
)

MAX_BODY = 4096


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        secret = os.environ.get("SESSION_SECRET", "")
        stored = os.environ.get("APP_PASSWORD_HASH", "")
        missing = [name for name, value in
                   (("SESSION_SECRET", secret), ("APP_PASSWORD_HASH", stored))
                   if not value]
        if missing:
            # 어느 변수가 비었는지는 로그에만 적는다. 인증 전 응답에 설정 상태를
            # 실으면 밖에서 우리 구성을 들여다볼 수 있게 된다.
            print(f"missing env: {', '.join(missing)} "
                  f"(seen {len(os.environ)} vars)", file=sys.stderr)
            self._json(500, {"error": "server misconfigured"})
            return

        password = self._password()
        # 실패 사유를 구분해 알려주지 않는다. '형식이 틀렸다'와 '틀린 암호다'를
        # 나눠 주면 공격자에게 단서가 된다.
        if not password or not verify_password(password, stored):
            self._json(401, {"error": "unauthorized"})
            return

        self._json(200, {"ok": True}, cookie=set_cookie_header(issue_token(secret)))

    def do_GET(self):
        self._json(405, {"error": "method not allowed"})

    def _password(self) -> str:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return ""
        if length <= 0 or length > MAX_BODY:
            return ""
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return ""
        if not isinstance(payload, dict):
            return ""
        value = payload.get("password")
        # 문자열이 아니면 그대로 넘기지 않는다. 검증 함수가 터지는 대신 거부한다.
        return value if isinstance(value, str) else ""

    def _json(self, status: int, body: dict, cookie: str | None = None) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(raw)
