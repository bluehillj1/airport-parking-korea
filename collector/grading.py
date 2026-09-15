"""등급 계산. 표시 규칙의 단일 출처다.

서버에서 계산해 JSON에 담으므로 웹앱은 규칙을 알 필요가 없고, 규칙 변경은
파이썬 테스트로 검증된다.

추세는 여기에 없다. 서버가 이력을 갖지 않는 구조라 계산할 수 없고, 앱이
열려 있는 동안 브라우저가 직접 만든다(public/app.js 의 computeTrend).
"""

from __future__ import annotations

UNKNOWN = "정보 없음"


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
