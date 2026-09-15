"""실시간 주차현황 엔드포인트.

서울(icn1)에서 실행된다. 공공데이터포털이 해외 IP를 차단하므로 리전 고정은
선택이 아니라 필수다 — vercel.json 의 regions 를 바꾸면 앱 전체가 죽는다.

서비스키는 이 함수의 환경변수에만 있고 브라우저로 나가지 않는다.
"""

from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler

# 번들 루트를 import 경로에 넣어야 collector 패키지가 보인다.
# 함수마다 반복되지만, 공유 모듈로 빼면 번들 추적에 기대게 되어 배포 환경에서만
# 터지는 실패가 생긴다. 네 줄 중복이 더 안전하다.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from collector.access import load_access          # noqa: E402
from collector.api import ApiError, fetch         # noqa: E402
from collector.auth import token_from_cookie, verify_token  # noqa: E402
from collector.live import build_live             # noqa: E402

ACCESS_PATH = os.path.join(ROOT, "data", "lot_access.json")

# 원천은 60초마다 갱신된다. 짧게 묶어두면 연타 새로고침이 호출 한도를 갉아먹지
# 않으면서도 화면은 최대 75초 이내의 값을 보게 된다.
CACHE_SECONDS = 15

# vercel.json 의 maxDuration(15초)보다 반드시 짧아야 한다. 더 길면 플랫폼이
# 함수를 먼저 죽여서, 우리가 준비한 502 대신 정체불명의 오류가 사용자에게 간다.
# 실측 응답시간은 141ms라 8초도 충분히 넉넉하다.
UPSTREAM_TIMEOUT = 8.0

_access = None
_cache: dict = {"at": 0.0, "body": None}


def _access_data():
    """정적 메타데이터. 웜 컨테이너에서는 다시 읽지 않는다."""
    global _access
    if _access is None:
        _access = load_access(ACCESS_PATH)
    return _access


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not verify_token(token_from_cookie(self.headers.get("Cookie")),
                            os.environ.get("SESSION_SECRET", "")):
            self._json(401, {"error": "unauthorized"})
            return

        service_key = os.environ.get("KAC_SERVICE_KEY", "").strip()
        if not service_key:
            print("KAC_SERVICE_KEY is not set", file=sys.stderr)
            self._json(500, {"error": "server misconfigured"})
            return

        try:
            access = _access_data()
        except OSError as exc:
            # 번들에 lot_access.json 이 안 들어간 경우다. 로컬 테스트는 전부
            # 통과하고 배포에서만 터지므로, 원인을 로그에 대놓고 적어둔다.
            print(f"lot_access.json unreadable ({exc}) — "
                  f"check includeFiles in vercel.json", file=sys.stderr)
            self._json(500, {"error": "server misconfigured"})
            return

        now = time.time()
        if _cache["body"] is not None and now - _cache["at"] < CACHE_SECONDS:
            self._json(200, _cache["body"])
            return

        try:
            readings = fetch(service_key, timeout=UPSTREAM_TIMEOUT)
        except ApiError as exc:
            # 원인은 서버 로그에만 남긴다. 응답에 내부 사정을 싣지 않는다.
            print(f"upstream failed: {exc}", file=sys.stderr)
            self._json(502, {"error": "upstream unavailable"})
            return

        body = build_live(readings, access)
        _cache["at"], _cache["body"] = now, body
        self._json(200, body)

    def _json(self, status: int, body: dict) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)
