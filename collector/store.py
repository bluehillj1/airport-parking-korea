"""원본 스냅샷 저장소.

실행 1회당 파일 1개를 쓴다. 하나의 큰 파일에 append하면 커밋마다 전체 blob이
다시 저장되어 git이 급격히 커진다.

중복 제거 키는 원천이 스스로 찍은 타임스탬프(src_ts)다. 덕분에 수집기를
겹쳐 돌려도 데이터가 오염되지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

from collector.api import LotReading, representative_ts


def run_file(root: Path, src_ts: str, run_id: str) -> Path:
    """raw/YYYY-MM-DD/HHMM.jsonl

    날짜는 반드시 원천 타임스탬프(KST)에서 가져온다. Actions 러너는 UTC라
    러너 시계를 쓰면 매일 09:00 KST에 날짜가 하루 어긋난다.
    """
    day = src_ts.split(" ")[0]
    return Path(root) / day / f"{run_id}.jsonl"


def append_snapshot(path: Path, readings: list[LotReading]) -> bool:
    """스냅샷 1건을 한 줄로 덧붙인다. 이미 있는 src_ts면 건너뛰고 False를 반환한다."""
    if not readings:
        return False
    src_ts = representative_ts(readings)

    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and json.loads(line)["src_ts"] == src_ts:
                return False

    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "src_ts": src_ts,
        "rows": [
            [r.airport_kor, r.lot, r.total, r.stay, r.cum_in, r.cum_out]
            for r in readings
        ],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return True


def load_day(root: Path, day: str) -> dict[str, list[LotReading]]:
    """그날의 모든 실행 파일을 읽어 src_ts로 중복 제거한 스냅샷 맵을 돌려준다."""
    directory = Path(root) / day
    if not directory.is_dir():
        return {}

    snapshots: dict[str, list[LotReading]] = {}
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            snapshots[record["src_ts"]] = [
                LotReading(airport_kor=row[0], lot=row[1], total=row[2],
                           stay=row[3], cum_in=row[4], cum_out=row[5],
                           src_ts=record["src_ts"])
                for row in record["rows"]
            ]
    return snapshots
