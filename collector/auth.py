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

# 1년. 차 안에서 급히 여는 앱이라 로그인 화면이 뜨는 것 자체가 실패에 가깝다.
#
# 전에는 5년(1825일)이었지만 지켜지지 않는 약속이었다. 크롬·엣지는 쿠키 수명을
# 400일에서 자르므로 서버가 5년을 적어 보내도 브라우저가 13개월 만에 버렸다.
# 400일 아래로 내려 두면 적은 값과 실제 값이 같아진다.
#
# 짧아진 만큼은 갱신으로 메운다 — 요청이 올 때마다 남은 수명을 보고 절반 아래로
# 내려갔으면 쿠키를 새로 내린다(needs_renewal). 앱을 쓰는 한 만료가 오지 않고,
# 1년 넘게 손대지 않았을 때만 한 번 다시 로그인한다.
#
# 기기를 잃었을 때는 SESSION_SECRET 을 바꾸면 발급된 모든 세션이 한 번에 끊긴다.
SESSION_DAYS = 365


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


def fingerprint(encoded: str) -> str:
    """저장된 해시가 '어느 것인지'만 식별하는 짧은 지문.

    해시를 한 번 더 해싱한 값의 앞 8자라 되돌릴 수 없다. 이 PC에서 만든 값과
    서버에 실제로 들어간 값이 같은 것인지 대조하는 용도다. 형태만 보는
    describe_encoded 로는 '정상이지만 다른 해시'를 구분할 수 없다.
    """
    if not encoded:
        return "none"
    return hashlib.sha256(encoded.strip().encode("utf-8")).hexdigest()[:8]


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


def _signed_expiry(token: str, secret: str) -> int | None:
    """서명이 맞는 토큰의 만료시각. 아니면 None.

    만료 여부는 여기서 보지 않는다 — 판단은 부르는 쪽 몫이다. 갱신 여부를
    따지려면 '서명은 맞는데 언제까지인가'를 알아야 하는데, 통과·거부만 돌려주는
    함수로는 그 값을 꺼낼 수 없다.

    secret이 비어 있으면 무조건 None이다. 환경변수 누락이 '아무 토큰이나 통과'
    로 이어지면 안 된다.
    """
    if not token or not secret:
        return None
    try:
        payload, separator, signature_b64 = token.partition(".")
        if not separator:
            return None
        signature = _b64d(signature_b64)
    except (AttributeError, ValueError, binascii.Error):
        return None

    if not hmac.compare_digest(signature, _sign(payload, secret)):
        return None

    try:
        return int(payload)
    except ValueError:
        return None


def verify_token(token: str, secret: str, *, now: float | None = None) -> bool:
    """서명이 맞고 아직 만료되지 않았을 때만 True."""
    expires = _signed_expiry(token, secret)
    if expires is None:
        return False
    return expires > (time.time() if now is None else now)


def needs_renewal(token: str, secret: str, *, now: float | None = None,
                  days: int = SESSION_DAYS) -> bool:
    """남은 수명이 지금 정책의 창을 벗어났으면 True.

    두 방향 모두 갱신 대상이다.

    절반 아래로 내려간 경우 — 요청마다 쿠키를 다시 내리면 60초 주기의 갱신
    요청마다 Set-Cookie가 붙는다. 절반을 기준으로 두면 갱신은 반년에 한 번쯤
    일어나면서도, 앱을 쓰는 한 만료가 계속 밀려나 로그인 화면을 다시 보지 않는다.

    창보다 긴 경우 — 옛 정책(1825일)으로 발급된 토큰이다. 브라우저는 그 쿠키를
    이미 400일로 잘라 두었는데 토큰의 만료는 5년 뒤라, 가만두면 절반 규칙이
    걸리기 한참 전에 브라우저가 쿠키를 버린다. 첫 요청에 지금 정책으로 다시
    발급해 그 어긋남을 없앤다.

    이미 만료된 토큰은 갱신하지 않는다. 만료된 세션을 연장해 주면 만료가 아무
    의미도 없어진다.
    """
    expires = _signed_expiry(token, secret)
    if expires is None:
        return False
    now = time.time() if now is None else now
    if expires <= now:
        return False
    window = days * 86400
    remaining = expires - now
    return remaining < window / 2 or remaining > window


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
