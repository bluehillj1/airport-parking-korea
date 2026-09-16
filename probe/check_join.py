"""lot_access.json이 실제 API 응답과 조인되는지 검증한다.

주차장명이 한 글자라도 어긋나면 앱에서 접근성 정보가 조용히 사라지므로,
메타데이터를 고칠 때마다 이 스크립트를 돌린다.
API를 새로 호출하지 않고 probe/refresh_log.jsonl의 마지막 정상 응답을 쓴다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    meta = json.loads((ROOT / "data/lot_access.json").read_text(encoding="utf-8"))
    name_to_code = {a["name_kor"]: code for code, a in meta["airports"].items()}
    known = {(lot["airport"], lot["name"]) for lot in meta["lots"]}

    log_path = ROOT / "probe/refresh_log.jsonl"
    if not log_path.exists():
        sys.exit("refresh_log.jsonl이 없습니다. 먼저 measure_refresh.py를 돌리세요.")

    last = None
    for line in log_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("ok"):
            last = record
    if last is None:
        sys.exit("로그에 정상 응답이 없습니다.")

    rows = last["rows"]
    target = [r for r in rows if r["airport"] in name_to_code]
    print(f"기준 응답: {last['polled_at']}")
    print(f"전체 {len(rows)}건 중 대상 {len(name_to_code)}개 공항 {len(target)}건\n")

    missing = sorted(
        (r["airport"], r["lot"]) for r in target
        if (name_to_code[r["airport"]], r["lot"]) not in known
    )
    extra = sorted(known - {(name_to_code[r["airport"]], r["lot"]) for r in target})

    print(f"메타데이터에 없는 주차장 : {missing if missing else '없음'}")
    print(f"응답에 없는 메타데이터   : {extra if extra else '없음'}")

    if missing or extra:
        print("\n조인 불일치가 있습니다. lot_access.json을 고치세요.")
        return 1

    passenger = {
        (lot["airport"], lot["name"]) for lot in meta["lots"] if lot["passenger_use"]
    }
    print(f"\n조인 OK — 여객용 {len(passenger)}곳 / 화물 등 제외 {len(known) - len(passenger)}곳")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
