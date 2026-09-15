import pytest

from collector.grading import compute_trend, downsample, grade


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


def test_trend_reports_direction_when_significant():
    trend = compute_trend(series=[1500, 1520, 1560], total=1733, span_minutes=60)
    assert trend["direction"] == "up"
    assert trend["delta"] == 60
    assert trend["significant"] is True


def test_trend_is_insignificant_below_one_percent():
    """2005면 주차장의 12대 증가(0.6%)를 상승 추세로 보여주면 없는 추세를 만든다."""
    trend = compute_trend(series=[1900, 1912], total=2005, span_minutes=60)
    assert trend["significant"] is False
    assert trend["direction"] == "flat"


def test_trend_minimum_absolute_threshold():
    """작은 주차장에서 1%는 1~2대다. 최소 3대는 움직여야 방향을 말한다."""
    trend = compute_trend(series=[100, 102], total=200, span_minutes=60)
    assert trend["significant"] is False


def test_trend_is_none_with_single_point():
    """수집 시작 직후에는 추세가 없다."""
    assert compute_trend(series=[1500], total=1733, span_minutes=60) is None


def test_downsample_keeps_last_value_in_each_bucket():
    points = [("10:00", 10), ("10:02", 11), ("10:04", 12), ("10:06", 20)]
    assert downsample(points, interval_min=5) == [("10:00", 12), ("10:05", 20)]


def test_downsample_keeps_final_bucket():
    """마지막 값이 누락되면 지금 상황이 화면에서 빠진다."""
    points = [("10:00", 10), ("10:07", 25)]
    assert downsample(points, interval_min=5)[-1] == ("10:05", 25)
