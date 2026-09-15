"""1분 사이에 주차 대수가 실제로 얼마나 움직이는지 측정한다.

원천이 1분마다 갱신된다는 건 확인됐지만, 그게 곧 '1분마다 수집할 가치가 있다'는
뜻은 아니다. 1분 변화량이 한두 대뿐이라면 5분 수집으로도 곡선이 사실상 같고,
수집 인프라를 훨씬 단순하게 가져갈 수 있다. 그 판단 근거를 숫자로 만든다.

대상은 앱이 다루는 3개 공항의 여객 주차장이다.
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "probe/refresh_log.jsonl"


def main() -> None:
    meta = json.loads((ROOT / "data/lot_access.json").read_text(encoding="utf-8"))
    code_of = {a["name_kor"]: c for c, a in meta["airports"].items()}
    passenger = {
        (lot["airport"], lot["name"]) for lot in meta["lots"] if lot["passenger_use"]
    }

    if not LOG.exists():
        sys.exit("refresh_log.jsonl이 없습니다.")

    # 원천 타임스탬프별로 마지막 관측만 남긴다 (같은 값을 여러 번 폴링했으므로)
    by_src: dict[str, dict[str, int]] = {}
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if not rec.get("ok") or not rec.get("src_ts"):
            continue
        snapshot = {}
        for row in rec["rows"]:
            airport = code_of.get(row["airport"])
            if airport and (airport, row["lot"]) in passenger and row["stay"] is not None:
                snapshot[f"{airport} {row['lot']}"] = row["stay"]
        if snapshot:
            by_src[rec["src_ts"]] = snapshot

    stamps = sorted(by_src)
    if len(stamps) < 3:
        sys.exit(f"스냅샷이 {len(stamps)}개뿐입니다. 측정을 더 돌리세요.")

    print(f"스냅샷 {len(stamps)}개 ({stamps[0]} ~ {stamps[-1]})")
    print(f"여객 주차장 {len(passenger)}곳\n")

    per_lot: dict[str, list[int]] = {}
    for i in range(1, len(stamps)):
        prev, curr = by_src[stamps[i - 1]], by_src[stamps[i]]
        elapsed = (
            datetime.fromisoformat(stamps[i]) - datetime.fromisoformat(stamps[i - 1])
        ).total_seconds()
        if not 50 <= elapsed <= 70:      # 1분 간격이 아닌 구간은 건너뛴다
            continue
        for lot, value in curr.items():
            if lot in prev:
                per_lot.setdefault(lot, []).append(value - prev[lot])

    header = f"{'주차장':<28} {'1분 변화 중앙값':>14} {'최대':>6} {'무변화 비율':>10}"
    print(header)
    print("-" * len(header))
    all_abs: list[int] = []
    for lot in sorted(per_lot):
        deltas = per_lot[lot]
        magnitudes = [abs(d) for d in deltas]
        all_abs.extend(magnitudes)
        zero_pct = 100 * sum(1 for d in deltas if d == 0) / len(deltas)
        print(f"{lot:<28} {statistics.median(magnitudes):>14.1f}대 "
              f"{max(magnitudes):>5}대 {zero_pct:>9.0f}%")

    print()
    if all_abs:
        zero_pct = 100 * sum(1 for d in all_abs if d == 0) / len(all_abs)
        print(f"전체: 1분 변화 중앙값 {statistics.median(all_abs):.1f}대, "
              f"평균 {statistics.mean(all_abs):.1f}대, 최대 {max(all_abs)}대")
        print(f"      1분간 아무 변화 없던 비율 {zero_pct:.0f}%")


if __name__ == "__main__":
    main()
