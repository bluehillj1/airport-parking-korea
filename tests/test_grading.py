import re
from pathlib import Path

import pytest

from collector.grading import KEYS, UNKNOWN, grade, key_for

STYLE_CSS = Path(__file__).parent.parent / "public" / "style.css"


@pytest.mark.parametrize("free,total,expected", [
    (0, 2279, "만차"),
    (-3, 2279, "만차"),        # 음수 방어
    (1, 2279, "혼잡"),
    (30, 2279, "혼잡"),
    (31, 2279, "혼잡"),        # 31면이어도 점유율 98.6%라 혼잡
    (200, 1000, "보통"),       # 점유율 80%. 면수도 비율도 혼잡 기준에 못 미친다
    (31, 200, "보통"),         # 점유율 84.5%
    (100, 200, "여유"),        # 점유율 50%
])
def test_grade_boundaries(free, total, expected):
    assert grade(free, total) == expected


def test_grade_handles_zero_total():
    """청주 여객 제3주차장은 전체 면수가 0이다(실측). 0으로 나누면 안 된다."""
    assert grade(0, 0) == "정보 없음"


def test_every_grade_grade_can_produce_has_a_token():
    """등급을 새로 만들면서 토큰을 빠뜨리면 그 등급은 화면에서 회색이 된다."""
    produced = {grade(free, total)
                for total in (0, 200, 1000, 2279)
                for free in range(-1, total + 1, 7)}
    produced.add(UNKNOWN)
    assert produced <= set(KEYS), f"토큰 없는 등급: {produced - set(KEYS)}"


def test_unknown_grade_falls_back_to_unknown_token():
    assert key_for("듣도보도 못한 등급") == KEYS[UNKNOWN]


def test_every_token_is_styled():
    """토큰마다 style.css 에 규칙이 있어야 한다.

    이 검사가 없어서 '보통'이 오랫동안 회색으로 나왔다. KEYS 에 'ok' 는 있는데
    .lot.ok 규칙이 없었고, 어긋남은 아무 데서도 소리를 내지 않았다. 파이썬과
    CSS는 서로를 모르므로 둘을 맞대어 보는 자리가 한 곳은 있어야 한다.
    """
    css = STYLE_CSS.read_text(encoding="utf-8")
    missing = [token for token in set(KEYS.values())
               if not re.search(rf"\.lot\.{re.escape(token)}\b", css)]
    assert not missing, f"style.css 에 규칙이 없는 토큰: {missing}"
