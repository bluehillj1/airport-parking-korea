"""측정 로그로 앱 화면을 그려본다.

설계 확정 전에 실제 데이터로 화면을 확인하기 위한 도구다. 숫자를 지어내면
"만차인데 추세가 안 보인다" 같은 실제 동작을 검증할 수 없다.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "probe/refresh_log.jsonl"
SPARK = "▁▂▃▄▅▆▇█"
WIDTH = 46


def load():
    meta = json.loads((ROOT / "data/lot_access.json").read_text(encoding="utf-8"))
    code_of = {a["name_kor"]: c for c, a in meta["airports"].items()}

    snapshots: dict[str, dict[str, tuple[int, int]]] = {}
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if not rec.get("ok") or not rec.get("src_ts"):
            continue
        snap = {}
        for row in rec["rows"]:
            code = code_of.get(row["airport"])
            if code and row["stay"] is not None and row["total"]:
                snap[f"{code}|{row['lot']}"] = (row["stay"], row["total"])
        snapshots[rec["src_ts"]] = snap
    return meta, snapshots


def grade(free: int, pct: float) -> str:
    """면수와 비율을 함께 본다. 작은 주차장이 비율만으로 여유해 보이는 걸 막는다."""
    if free <= 0:
        return "만차"
    if free <= 30 or pct >= 95:
        return "혼잡"
    if pct >= 80:
        return "보통"
    return "여유"


def sparkline(values: list[int], total: int) -> str:
    """주차장 규모 대비 최소 진폭을 두고 그린다.

    자기 min/max로 정규화하면 1763면 중 15대(0.8%) 변화가 화면 가득 출렁이는
    그래프가 되어 없는 추세를 만들어낸다. 총 주차면의 5%를 최소 진폭으로 잡아,
    그보다 작은 변화는 평평하게 보이도록 한다.
    """
    lo, hi = min(values), max(values)
    floor = max(2.0, total * 0.05)
    if hi - lo < floor:
        mid = (lo + hi) / 2
        lo, hi = mid - floor / 2, mid + floor / 2
    return "".join(
        SPARK[round((v - lo) / (hi - lo) * (len(SPARK) - 1))] for v in values
    )


def access_label(lot: dict, shuttle: dict | None) -> str:
    if lot.get("requires_shuttle"):
        if shuttle and shuttle.get("headway_min"):
            lo, hi = shuttle["headway_min"]
            return f"셔틀 {lo}분 간격" if lo == hi else f"셔틀 {lo}~{hi}분 간격"
        return "셔틀 이용"
    if lot.get("walk_min"):
        lo, hi = lot["walk_min"]
        return f"도보 {lo}~{hi}분"
    return "도보권"


def render(meta, snapshots) -> None:
    stamps = sorted(snapshots)
    latest, first = stamps[-1], stamps[0]
    span = (datetime.fromisoformat(latest) - datetime.fromisoformat(first)).total_seconds() / 60

    for code, airport in meta["airports"].items():
        lots = [l for l in meta["lots"] if l["airport"] == code and l["passenger_use"]]
        if not lots:
            continue

        print("┌" + "─" * WIDTH + "┐")
        print(f"│ {airport['name_kor']:<{WIDTH - 12}}{'김포 김해 제주':>9} │")
        print(f"│ {'방금 전 정보 · ' + latest[11:16]:<{WIDTH - 2}} │")

        # 청사별로 묶는다. 청사가 다르면 셔틀을 타야 하므로 같은 줄에 세우면 안 된다.
        for terminal in dict.fromkeys(l["terminal"] for l in lots):
            group = [l for l in lots if l["terminal"] == terminal]
            rows = []
            for lot in group:
                key = f"{code}|{lot['name']}"
                series = [snapshots[s][key][0] for s in stamps if key in snapshots[s]]
                if not series:
                    continue
                stay, total = snapshots[latest][key]
                free = total - stay
                pct = stay / total * 100
                rows.append((lot, free, pct, stay - series[0], series, total))
            if not rows:
                continue
            # 접근성이 먼저다. 도보권이 비어 있으면 셔틀 주차장은 볼 이유가 없고,
            # 만차는 선택지가 아니므로 맨 뒤로 보낸다.
            rows.sort(key=lambda r: (r[1] <= 0, bool(r[0].get("requires_shuttle")), -r[1]))

            print("├" + "─" * WIDTH + "┤")
            if len(set(l["terminal"] for l in lots)) > 1:
                need = terminal != "국내선"
                tag = f"  ({airport['shuttle']['name'] if need else '도보 이동'})" if need else ""
                print(f"│ ■ {terminal + '청사' + tag:<{WIDTH - 4}} │")

            for lot, free, pct, delta, series, total in rows:
                g = grade(free, pct)
                print(f"│ {lot['name']:<{WIDTH - 12}}{g:>7} │")
                print(f"│   {str(free) + '면':<8}{access_label(lot, airport.get('shuttle')):<{WIDTH - 13}} │")
                if g == "만차":
                    note = "만차 — 입출차 정보 없음"
                else:
                    # 규모 대비 미미한 변화는 방향을 단정하지 않는다
                    significant = abs(delta) >= max(3, total * 0.01)
                    arrow = ("↗" if delta > 0 else "↘") if significant else "→"
                    trend = f"{arrow} {span:.0f}분 {delta:+d}대" if significant else "→ 큰 변화 없음"
                    note = f"{sparkline(series[-14:], total)}  {trend}"
                print(f"│   {note:<{WIDTH - 5}} │")
        print("└" + "─" * WIDTH + "┘\n")


def main() -> None:
    if not LOG.exists():
        sys.exit("refresh_log.jsonl이 없습니다.")
    meta, snapshots = load()
    if not snapshots:
        sys.exit("로그에 정상 응답이 없습니다.")
    render(meta, snapshots)


if __name__ == "__main__":
    main()
