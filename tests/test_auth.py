import time

import pytest

from collector.auth import (
    COOKIE_NAME,
    SESSION_DAYS,
    describe_encoded,
    fingerprint,
    hash_password,
    issue_token,
    needs_renewal,
    set_cookie_header,
    token_from_cookie,
    verify_password,
    verify_token,
)

DAY = 86400

# 실제 반복수는 60만이라 테스트가 느려진다. 알고리즘 검증에는 무관한 값이다.
FAST = 1000
SECRET = "test-session-secret"


def test_password_round_trip():
    encoded = hash_password("올바른암호", iterations=FAST)
    assert verify_password("올바른암호", encoded) is True


def test_wrong_password_rejected():
    encoded = hash_password("올바른암호", iterations=FAST)
    assert verify_password("틀린암호", encoded) is False


def test_hash_is_salted():
    """같은 암호라도 저장값이 달라야 한다. 아니면 해시 비교만으로 동일 암호를 알 수 있다."""
    assert hash_password("같은암호", iterations=FAST) != hash_password("같은암호", iterations=FAST)


def test_plaintext_password_never_appears_in_hash():
    assert "올바른암호" not in hash_password("올바른암호", iterations=FAST)


@pytest.mark.parametrize("encoded", [
    "",
    None,
    "평문암호",
    "md5$1000$abc$def",              # 다른 알고리즘
    "pbkdf2_sha256$1000$abc",        # 필드 부족
    "pbkdf2_sha256$많이$abc$def",     # 반복수가 숫자가 아님
    "pbkdf2_sha256$1000$!!!$???",    # base64가 아님
])
def test_malformed_stored_hash_is_rejected(encoded):
    """환경변수가 깨졌을 때 '통과'가 아니라 '거부'로 끝나야 한다."""
    assert verify_password("아무암호", encoded) is False


def test_surrounding_whitespace_in_stored_hash_is_tolerated():
    """대시보드에 붙여넣다 줄바꿈이 섞이는 일이 실제로 흔하다.

    해시 문자열에 의미 있는 앞뒤 공백은 없으므로 버리는 것이 맞다.
    """
    encoded = hash_password("올바른암호", iterations=FAST)
    assert verify_password("올바른암호", f"  {encoded}\n") is True


def test_describe_reports_shape_of_a_healthy_hash():
    described = describe_encoded(hash_password("아무암호", iterations=600_000))
    assert "algo_ok=True" in described
    assert "iters=600000" in described
    assert "salt=16B" in described
    assert "key=32B" in described


@pytest.mark.parametrize("encoded,expected", [
    ("", "absent"),
    ("짧은값", "fields=1"),
    ("APP_PASSWORD_HASH=pbkdf2_sha256$600000$YWJj$ZGVm", "algo_ok=False"),
    ("pbkdf2_sha256$많이$YWJj$ZGVm", "iters=NOT_A_NUMBER"),
])
def test_describe_names_the_defect(encoded, expected):
    assert expected in describe_encoded(encoded)


def test_fingerprint_distinguishes_two_valid_hashes():
    """형태만 보면 둘 다 정상이라 '다른 해시가 올라갔다'를 잡을 수 없다."""
    one = hash_password("같은암호", iterations=FAST)
    other = hash_password("같은암호", iterations=FAST)
    assert describe_encoded(one) == describe_encoded(other)
    assert fingerprint(one) != fingerprint(other)


def test_fingerprint_ignores_surrounding_whitespace():
    encoded = hash_password("아무암호", iterations=FAST)
    assert fingerprint(f"  {encoded}\n") == fingerprint(encoded)


def test_fingerprint_does_not_contain_the_hash():
    encoded = hash_password("아무암호", iterations=FAST)
    assert encoded.split("$")[3] not in fingerprint(encoded)


def test_describe_never_leaks_the_stored_value():
    encoded = hash_password("아무암호", iterations=FAST)
    described = describe_encoded(encoded)
    salt_b64 = encoded.split("$")[2]
    assert salt_b64 not in described
    assert encoded.split("$")[3] not in described


def test_empty_password_rejected():
    encoded = hash_password("올바른암호", iterations=FAST)
    assert verify_password("", encoded) is False


def test_token_round_trip():
    assert verify_token(issue_token(SECRET), SECRET) is True


def test_token_rejected_with_other_secret():
    assert verify_token(issue_token(SECRET), "다른비밀키") is False


def test_extending_expiry_is_rejected():
    """세션을 영구히 늘리는 것이 이 토큰에 대한 실질적인 공격이다."""
    _, _, signature = issue_token(SECRET).partition(".")
    forged = f"{int(time.time()) + 3650 * 86400}.{signature}"
    assert verify_token(forged, SECRET) is False


def test_token_payload_is_readable_expiry():
    """만료시각은 숨길 정보가 아니다. 평문이라 인코딩 모호함이 생기지 않는다."""
    token = issue_token(SECRET, now=1_792_000_000, days=30)
    assert token.partition(".")[0] == str(1_792_000_000 + 30 * 86400)


def test_expired_token_rejected():
    old = issue_token(SECRET, now=time.time() - 40 * 86400, days=30)
    assert verify_token(old, SECRET) is False


def test_empty_secret_never_authorizes():
    """환경변수 누락이 '아무나 통과'로 이어지면 안 된다."""
    assert verify_token(issue_token(SECRET), "") is False
    with pytest.raises(ValueError):
        issue_token("")


@pytest.mark.parametrize("token", ["", None, "형식이없음", "a.b.c", "!!!.???"])
def test_malformed_token_rejected(token):
    assert verify_token(token, SECRET) is False


def test_session_stays_under_the_browser_cookie_cap():
    """크롬·엣지는 쿠키 수명을 400일에서 자른다.

    상한을 넘겨 적으면 서버가 약속한 기간과 브라우저가 지키는 기간이 갈라지고,
    그 차이는 사용자가 예고 없이 로그아웃될 때에야 드러난다. 적은 값이 곧
    실제 값이어야 한다.
    """
    assert SESSION_DAYS < 400
    max_age = int(set_cookie_header("sometoken").split("Max-Age=")[1].split(";")[0])
    assert max_age == SESSION_DAYS * DAY


def test_fresh_token_is_not_renewed():
    """막 발급한 세션까지 갱신하면 요청마다 Set-Cookie가 붙는다."""
    now = time.time()
    assert needs_renewal(issue_token(SECRET, now=now), SECRET, now=now) is False


def test_token_past_halfway_is_renewed():
    issued = time.time()
    token = issue_token(SECRET, now=issued)
    assert needs_renewal(token, SECRET, now=issued + 200 * DAY) is True


def test_renewal_pushes_the_expiry_further_out():
    """갱신의 값어치는 만료가 실제로 밀려나는 데 있다."""
    issued = time.time()
    old = issue_token(SECRET, now=issued)
    new = issue_token(SECRET, now=issued + 200 * DAY)
    assert int(new.partition(".")[0]) > int(old.partition(".")[0])
    assert verify_token(new, SECRET, now=issued + 400 * DAY) is True


def test_legacy_long_token_is_renewed_on_sight():
    """옛 정책(1825일)으로 발급된 토큰은 첫 요청에 지금 정책으로 갈아탄다.

    브라우저는 그 쿠키를 이미 400일로 잘라 두었는데 토큰 만료는 5년 뒤라,
    절반 규칙만으로는 갱신이 걸리기 전에 쿠키가 먼저 사라진다.
    """
    now = time.time()
    legacy = issue_token(SECRET, now=now, days=1825)
    assert verify_token(legacy, SECRET, now=now) is True
    assert needs_renewal(legacy, SECRET, now=now) is True


def test_expired_token_is_never_renewed():
    """만료된 세션을 연장해 주면 만료가 아무 의미도 없어진다."""
    issued = time.time()
    token = issue_token(SECRET, now=issued)
    later = issued + (SESSION_DAYS + 1) * DAY
    assert verify_token(token, SECRET, now=later) is False
    assert needs_renewal(token, SECRET, now=later) is False


@pytest.mark.parametrize("token", ["", None, "형식이없음", "a.b.c", "!!!.???"])
def test_forged_token_is_never_renewed(token):
    """갱신은 검증을 건너뛰는 뒷문이 되면 안 된다."""
    assert needs_renewal(token, SECRET) is False


def test_renewal_requires_a_secret():
    assert needs_renewal(issue_token(SECRET), "") is False


def test_cookie_is_httponly_and_secure():
    """자바스크립트가 읽을 수 없어야 XSS가 나도 세션이 새지 않는다."""
    header = set_cookie_header("sometoken")
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=Lax" in header


def test_token_extracted_from_crowded_cookie_header():
    header = f"other=1; {COOKIE_NAME}=abc.def; another=2"
    assert token_from_cookie(header) == "abc.def"


@pytest.mark.parametrize("header", [None, "", "other=1", "xaps=notours"])
def test_missing_cookie_returns_empty(header):
    assert token_from_cookie(header) == ""
