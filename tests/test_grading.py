import pytest

from collector.grading import grade


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
