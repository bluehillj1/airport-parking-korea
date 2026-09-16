"""실시간 응답 1건을 앱이 그릴 수 있는 형태로 바꾼다.

저장소가 없는 구조라 서버는 이력을 모른다. 그래서 추세를 계산하지 않는다.
'지금 차오르는 중'은 앱이 열려 있는 동안 브라우저가 직전 값과 비교해 만든다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from collector.access import Access
from collector.api import LotReading
from collector.grading import UNKNOWN, grade, key_for

KST = timezone(timedelta(hours=9))


def build_live(
    readings: list[LotReading],
    access: Access,
    now: datetime | None = None,
) -> dict:
    """응답에 온 것이 아니라 '있어야 할' 주차장을 기준으로 순회한다.

    수신된 것만 내보내면 API가 한 곳을 빠뜨렸을 때 앱에서 카드가 조용히
    사라져 사용자가 그 주차장의 존재 자체를 모르게 된다. 빠진 곳은 '정보 없음'
    으로 남아 있어야 한다.
    """
    received = {(r.airport_kor, r.lot): r for r in readings}
    # 같은 응답 안에서도 주차장마다 초가 1초씩 다르다. 행 순서에 흔들리지
    # 않도록 최댓값을 쓴다.
    source_ts = max((r.src_ts for r in readings), default=None)

    airports: dict[str, dict] = {}
    for meta in access.passenger_lots():
        code = meta["airport"]
        airport_kor = access.airports[code]["name_kor"]
        reading = received.get((airport_kor, meta["name"]))

        if reading is None or reading.total <= 0:
            total = occupied = free = None
            lot_grade = UNKNOWN
        else:
            # 원천은 점유율이 100%에 닿으면 카운터를 고정하는데, 고정되기 직전에
            # 정원을 넘겨 보고하는 일이 있다. 그대로 흘려보내면 화면에 '-5면'과
            # '104% 사용'이 찍히고, 음수가 공항 합계까지 오염시킨다.
            total = reading.total
            occupied = min(reading.stay, total)
            free = total - occupied
            lot_grade = grade(free, total)

        airports.setdefault(code, {
            "name": airport_kor,
            "shuttle": access.shuttle_for(code),
            "lots": [],
        })["lots"].append({
            "name": meta["name"],
            "terminal": meta["terminal"],
            "total": total,
            "occupied": occupied,
            "free": free,
            "grade": lot_grade,
            # 앱은 이 토큰으로 색을 고른다. 등급 문자열에서 앱이 직접 만들게
            # 두면 규칙이 두 곳으로 갈라진다.
            "grade_key": key_for(lot_grade),
            "access": {
                "walk_min": meta.get("walk_min"),
                "requires_shuttle": bool(meta.get("requires_shuttle")),
                "confidence": meta["confidence"],
            },
        })

    return {
        "generated_at": (now or datetime.now(KST)).isoformat(timespec="seconds"),
        "source_ts": source_ts,
        "airports": airports,
    }
