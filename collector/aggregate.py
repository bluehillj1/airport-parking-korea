"""raw 스냅샷을 앱용 경량 JSON으로 집계한다.

수집은 촘촘하게(2분) 하되 앱에 내보낼 때는 5분 격자로 내리고 3개 공항의
여객 주차장만 남긴다. 휴대폰이 받는 용량을 한 자릿수 KB로 유지하기 위해서다.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collector.access import load_access
from collector.grading import compute_trend, downsample, grade
from collector.store import load_day

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
INTERVAL_MIN = 5
TREND_SPAN_MIN = 60
# 수집 주기(분). 추세 창의 점 개수를 역산하는 데 쓴다.
# collect.py의 내부 루프 간격과 같아야 하며, 달라지면 추세 구간이 길거나
# 짧아진다(값 자체는 틀리지 않고 span_minutes 표기만 어긋난다).
COLLECT_INTERVAL_MIN = 2


def _series_for(snapshots: dict, airport_kor: str, lot: str) -> list[tuple[str, int]]:
    """(HH:MM, 주차대수) 시계열. 원천 타임스탬프 순으로 정렬한다."""
    points = []
    for src_ts in sorted(snapshots):
        for reading in snapshots[src_ts]:
            if reading.airport_kor == airport_kor and reading.lot == lot:
                points.append((src_ts.split(" ")[1][:5], reading.stay))
    return points


def build_latest(raw_dir: Path, day: str, access_path: Path) -> dict:
    access = load_access(access_path)
    snapshots = load_day(raw_dir, day)
    if not snapshots:
        return {"generated_at": datetime.now(KST).isoformat(timespec="seconds"),
                "source_ts": None, "airports": {}}

    newest = max(snapshots)
    # 응답에 온 것이 아니라 '있어야 할' 주차장을 기준으로 순회한다.
    # 수신된 것만 내보내면 API가 한 곳을 빠뜨렸을 때 앱에서 조용히 사라져
    # 사용자가 그 주차장의 존재 자체를 모르게 된다 (명세 §7).
    received = {(r.airport_kor, r.lot): r for r in snapshots[newest]}
    airports: dict[str, dict] = {}

    for meta in access.passenger_lots():
        code = meta["airport"]
        airport_kor = access.airports[code]["name_kor"]
        reading = received.get((airport_kor, meta["name"]))

        if reading is None or reading.total <= 0:
            total = occupied = free = None
            lot_grade = "정보 없음"
            trend = None
        else:
            total, occupied = reading.total, reading.stay
            free = total - occupied
            lot_grade = grade(free, total)
            # 만차는 카운터가 고정되어 추세를 신뢰할 수 없다
            trend = None
            if lot_grade != "만차":
                series = _series_for(snapshots, airport_kor, meta["name"])
                # 최근 TREND_SPAN_MIN 분에 해당하는 점 개수만 남긴다.
                # 수집 주기 2분이면 31점 = 60분.
                window_points = TREND_SPAN_MIN // COLLECT_INTERVAL_MIN + 1
                window = [value for _, value in series][-window_points:]
                trend = compute_trend(window, total, TREND_SPAN_MIN)

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
            "access": {
                "walk_min": meta.get("walk_min"),
                "requires_shuttle": bool(meta.get("requires_shuttle")),
                "confidence": meta["confidence"],
            },
            "trend": trend,
        })

    return {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source_ts": newest,
        "airports": airports,
    }


def build_today(raw_dir: Path, day: str, code: str, access_path: Path) -> dict:
    access = load_access(access_path)
    snapshots = load_day(raw_dir, day)
    airport_kor = access.airports[code]["name_kor"]

    lots: dict[str, dict] = {}
    all_times: set[str] = set()
    for meta in access.passenger_lots():
        if meta["airport"] != code:
            continue
        points = downsample(_series_for(snapshots, airport_kor, meta["name"]),
                            INTERVAL_MIN)
        if not points:
            continue
        total = next(
            (r.total for ts in sorted(snapshots) for r in snapshots[ts]
             if r.airport_kor == airport_kor and r.lot == meta["name"]), 0)
        lots[meta["name"]] = {"total": total, "_points": dict(points)}
        all_times.update(stamp for stamp, _ in points)

    times = sorted(all_times)
    for lot in lots.values():
        lot["occupied"] = [lot["_points"].get(stamp) for stamp in times]
        del lot["_points"]

    return {"date": day, "interval_min": INTERVAL_MIN, "times": times, "lots": lots}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", default=str(ROOT / "raw"))
    parser.add_argument("--out-dir", default=str(ROOT / "public" / "data"))
    parser.add_argument("--access", default=str(ROOT / "data" / "lot_access.json"))
    parser.add_argument("--day", default=datetime.now(KST).strftime("%Y-%m-%d"))
    args = parser.parse_args()

    raw_dir, out_dir = Path(args.raw_dir), Path(args.out_dir)
    access_path = Path(args.access)
    out_dir.mkdir(parents=True, exist_ok=True)

    latest = build_latest(raw_dir, args.day, access_path)
    (out_dir / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=1), encoding="utf-8")

    for code in load_access(access_path).airports:
        today = build_today(raw_dir, args.day, code, access_path)
        (out_dir / f"today-{code}.json").write_text(
            json.dumps(today, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")

    print(f"집계 완료 — {args.day}, 공항 {len(latest['airports'])}곳")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
