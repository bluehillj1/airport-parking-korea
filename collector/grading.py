"""등급 계산. 표시 규칙의 단일 출처다.

서버에서 계산해 JSON에 담으므로 웹앱은 규칙을 알 필요가 없고, 규칙 변경은
파이썬 테스트로 검증된다.

추세는 여기에 없다. 서버가 이력을 갖지 않는 구조라 계산할 수 없고, 앱이
열려 있는 동안 브라우저가 직접 만든다(public/app.js 의 computeTrend).
"""

from __future__ import annotations

UNKNOWN = "정보 없음"

# 표시 문자열과 기계용 토큰을 한자리에 둔다.
#
# 등급 문자열을 그대로 CSS 클래스로 쓰면 '정보 없음'의 공백에서 classList가
# 터진다. 그렇다고 앱 쪽에 같은 표를 하나 더 두면, 여기서 등급을 고치거나
# 늘릴 때 앱은 아무 말 없이 회색으로 떨어진다 — 실제로 '보통'이 그랬다.
# 토큰을 등급과 같은 자리에서 정의하고 서버가 함께 실어 보낸다.
KEYS = {
    "여유": "calm",
    "보통": "ok",
    "혼잡": "busy",
    "만차": "full",
    UNKNOWN: "unknown",
}


def key_for(grade_text: str) -> str:
    """등급 문자열에 대응하는 CSS 토큰. 모르는 등급은 '정보 없음'과 같이 다룬다."""
    return KEYS.get(grade_text, KEYS[UNKNOWN])


def grade(free: int, total: int) -> str:
    """면수와 비율을 함께 본다.

    비율만 쓰면 작은 주차장이 여유해 보이고, 면수만 쓰면 큰 주차장이 과대평가된다.
    """
    if total <= 0:
        return UNKNOWN
    if free <= 0:
        return "만차"
    occupancy = (total - free) / total * 100
    if free <= 30 or occupancy >= 95:
        return "혼잡"
    if occupancy >= 80:
        return "보통"
    return "여유"
