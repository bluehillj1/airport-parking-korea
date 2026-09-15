"""수집 진입점.

GitHub Actions의 schedule은 5분 미만 간격을 지원하지 않고 지연도 잦다.
그래서 한 번 실행되면 지정한 시간 동안 내부 루프를 돌며 수집한다.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collector.api import ApiError, fetch, representative_ts
from collector.store import append_snapshot, run_file

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=int, default=35, help="수집 지속 시간(분)")
    parser.add_argument("--interval", type=int, default=120, help="수집 간격(초)")
    parser.add_argument("--raw-dir", default=str(ROOT / "raw"))
    args = parser.parse_args()

    service_key = os.environ.get("KAC_SERVICE_KEY", "").strip()
    if not service_key:
        print("KAC_SERVICE_KEY 환경변수가 없습니다.", file=sys.stderr)
        return 1

    run_id = datetime.now(KST).strftime("%H%M")
    deadline = time.monotonic() + args.minutes * 60
    written = skipped = failed = 0

    while time.monotonic() < deadline:
        try:
            readings = fetch(service_key)
            path = run_file(Path(args.raw_dir), representative_ts(readings), run_id)
            if append_snapshot(path, readings):
                written += 1
            else:
                skipped += 1
        except ApiError as exc:
            failed += 1
            print(f"수집 실패: {exc}", file=sys.stderr)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(args.interval, remaining))

    print(f"수집 완료 — 신규 {written}건, 중복 {skipped}건, 실패 {failed}건")
    # 한 건도 못 받았으면 실패로 끝내 워크플로가 빨간불이 되게 한다
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
