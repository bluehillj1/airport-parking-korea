"""접근 제어.

정적 파일(HTML·CSS·JS)은 누구나 받을 수 있지만 데이터 API는 서버에서 막는다.
브라우저가 보내는 어떤 값도 신뢰하지 않으며, 판단이 애매하면 거부한다.

암호는 평문으로 저장하지 않는다. PBKDF2-HMAC-SHA256 해시만 환경변수에 둔다.
세션은 서버 비밀키로 서명한 쿠키라 브라우저에서 위조할 수 없고, 쿠키에는
만료시각 외에 아무것도 담지 않는다.

표준 라이브러리만 쓴다 — 서버리스 함수에 설치할 패키지가 없어야 한다.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import time

ALGORITHM = "pbkdf2_sha256"
# 느린 것이 목적이다. 서버리스에서는 저장소 없이 시도 횟수를 셀 수 없으므로,
# 1회 검증에 드는 시간 자체가 무차별 대입에 대한 유일한 방어선이다.
ITERATIONS = 600_000
COOKIE_NAME = "aps"
SESSION_DAYS = 30


def _b64e(raw: bytes) -> str:
    """패딩을 뗀 urlsafe base64. 쿠키 값에 '='가 섞이는 것을 피한다."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str, *, iterations: int = ITERATIONS,
                  salt: bytes | None = None) -> str:
    """`pbkdf2_sha256$반복수$솔트$해시` 형태의 한 줄 문자열."""
    if salt is None:
        salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${_b64e(salt)}${_b64e(derived)}"


def describe_encoded(encoded: str) -> str:
    """저장된 해시의 '모양'만 설명한다. 값은 절대 담지 않는다.

    설정이 잘못됐을 때 로그만 보고 원인을 가르기 위한 것이다. 전체 길이, 필드
    수, 반복수는 비밀이 아니고, 솔트와 키는 길이만 적는다.
    """
    if not encoded:
        return "absent"
    encoded = encoded.strip()
    parts = encoded.split("$")
    if len(parts) != 4:
        return f"len={len(encoded)} fields={len(parts)} (expected 4)"

    algorithm, iterations, salt_b64, hash_b64 = parts
    detail = [f"len={len(encoded)}", f"algo_ok={algorithm == ALGORITHM}",
              f"iters={iterations}" if iterations.isdigit() else "iters=NOT_A_NUMBER"]
    for label, text in (("salt", salt_b64), ("key", hash_b64)):
        try:
            detail.append(f"{label}={len(_b64d(text))}B")
        except (binascii.Error, ValueError):
            detail.append(f"{label}=NOT_BASE64")
    return " ".join(detail)


def verify_password(password: str, encoded: str) -> bool:
    """어떤 이유로든 해석할 수 없으면 거부한다.

    저장값의 앞뒤 공백은 버린다. 해시 문자열에 의미 있는 공백은 없고, 대시보드에
    붙여넣다 줄바꿈이 섞이는 일이 실제로 흔하다.
    """
    if not password or not encoded:
        return False
    encoded = encoded.strip()
    try:
        algorithm, iterations, salt_b64, hash_b64 = encoded.split("$")
        if algorithm != ALGORITHM:
            return False
        salt = _b64d(salt_b64)
        expected = _b64d(hash_b64)
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations))
    except (AttributeError, ValueError, binascii.Error):
        return False
    return hmac.compare_digest(derived, expected)


def _sign(payload: str, secret: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"),
                    hashlib.sha256).digest()


def issue_token(secret: str, *, now: float | None = None,
                days: int = SESSION_DAYS) -> str:
    """`만료시각.서명` — 만료시각 외에는 아무것도 담지 않는다.

    만료시각을 base64로 감싸지 않는다. base64는 같은 값으로 디코딩되는 표현이
    여럿이라(끝자리 비트가 버려진다), 디코딩된 바이트에 서명하면 서로 다른
    문자열이 모두 통과한다. 평문 숫자에 서명하면 그 모호함이 없어진다.
    """
    if not secret:
        raise ValueError("session secret is empty")
    expires = int((time.time() if now is None else now) + days * 86400)
    payload = str(expires)
    return f"{payload}.{_b64e(_sign(payload, secret))}"


def verify_token(token: str, secret: str, *, now: float | None = None) -> bool:
    """서명이 맞고 아직 만료되지 않았을 때만 True.

    secret이 비어 있으면 무조건 거부한다. 환경변수 누락이 '아무 토큰이나 통과'
    로 이어지면 안 된다.
    """
    if not token or not secret:
        return False
    try:
        payload, separator, signature_b64 = token.partition(".")
        if not separator:
            return False
        signature = _b64d(signature_b64)
    except (AttributeError, ValueError, binascii.Error):
        return False

    if not hmac.compare_digest(signature, _sign(payload, secret)):
        return False

    try:
        expires = int(payload)
    except ValueError:
        return False
    return expires > (time.time() if now is None else now)


def set_cookie_header(token: str, *, days: int = SESSION_DAYS) -> str:
    """HttpOnly라 자바스크립트가 읽을 수 없다 — XSS가 나도 세션은 못 훔친다."""
    return (
        f"{COOKIE_NAME}={token}; Max-Age={days * 86400}; Path=/; "
        "HttpOnly; Secure; SameSite=Lax"
    )


def token_from_cookie(header: str | None) -> str:
    """Cookie 헤더에서 세션 값만 꺼낸다. 없으면 빈 문자열."""
    if not header:
        return ""
    for part in header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE_NAME:
            return value.strip('"')
    return ""
