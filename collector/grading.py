"""등급·추세 계산. 표시 규칙의 단일 출처다.

서버에서 계산해 JSON에 담으므로 웹앱은 규칙을 알 필요가 없고, 규칙 변경은
파이썬 테스트로 검증된다.
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


def is_significant(delta: int, total: int) -> bool:
    """규모 대비 1% 미만(최소 3대)의 변화는 방향을 단정하지 않는다."""
    return abs(delta) >= max(3, total * 0.01)


def compute_trend(series: list[int], total: int, span_minutes: int) -> dict | None:
    """최근 구간의 순증감. 데이터가 1점뿐이면 None."""
    if len(series) < 2:
        return None
    delta = series[-1] - series[0]
    significant = is_significant(delta, total)
    if not significant:
        direction = "flat"
    else:
        direction = "up" if delta > 0 else "down"
    return {
        "delta": delta,
        "direction": direction,
        "significant": significant,
        "span_minutes": span_minutes,
    }


def downsample(points: list[tuple[str, int]], interval_min: int) -> list[tuple[str, int]]:
    """HH:MM 격자로 내려 각 구간의 시간상 마지막 값을 남긴다.

    수집은 촘촘하게 하고 앱에 내보낼 때만 성기게 한다. 휴대폰이 받는 용량을
    줄이면서 곡선 모양은 유지된다.

    입력 순서는 무관하다. 함수 내부에서 타임스탬프 기준으로 정렬하므로
    각 버킷에서 항상 시간적으로 가장 늦은 값이 선택된다.
    """
    buckets: dict[str, int] = {}
    for stamp, value in sorted(points):
        hour, minute = (int(part) for part in stamp.split(":")[:2])
        bucket_min = minute - (minute % interval_min)
        buckets[f"{hour:02d}:{bucket_min:02d}"] = value
    return sorted(buckets.items())
