"""collect.py 진입점 테스트.

네트워크를 치지 않는다. fetch / run_file / append_snapshot 을
unittest.mock.patch 로 대체한다.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from collector.api import LotReading


def _fake_reading() -> LotReading:
    return LotReading(
        airport_kor="김포",
        lot="일반",
        total=100,
        stay=50,
        cum_in=200,
        cum_out=150,
        src_ts="2026-09-15 10:00:00",
    )


def test_collect_survives_value_error(tmp_path, monkeypatch):
    """run_file 이 ValueError 를 던져도 루프가 멈추지 않는다.

    time.monotonic 을 제어해 루프를 정확히 2회 실행한다.

    time.monotonic() 호출 순서 (--minutes 1, deadline = call1 + 60):
        call 1: deadline 설정  → 0
        call 2: while 체크 #1  → 1   (1 < 60 → True, 1회차 시작)
        call 3: remaining 체크 → 2   (remaining=58, sleep)
        call 4: while 체크 #2  → 3   (3 < 60 → True, 2회차 시작)
        call 5: remaining 체크 → 61  (remaining=-1 → break)

    1회차: run_file → ValueError → failed 증가, 루프 계속
    2회차: run_file → 정상 경로  → written 증가
    main() → written=1 이므로 0 반환
    """
    monkeypatch.setenv("KAC_SERVICE_KEY", "FAKE_KEY_FOR_TESTING")

    # monotonic 값 순서: [0, 1, 2, 3, 61]
    mono_iter = iter([0, 1, 2, 3, 61])

    def fake_monotonic():
        return next(mono_iter)

    # run_file: 1회차 ValueError, 2회차 정상 경로
    fake_path = tmp_path / "2026-09-15" / "1000.jsonl"
    run_file_call_count = {"n": 0}

    def fake_run_file(root, src_ts, run_id):
        run_file_call_count["n"] += 1
        if run_file_call_count["n"] == 1:
            raise ValueError("bad src_ts")
        return fake_path

    with (
        patch("collector.collect.fetch", return_value=[_fake_reading()]),
        patch("collector.collect.run_file", side_effect=fake_run_file),
        patch("collector.collect.append_snapshot", return_value=True),
        patch("time.monotonic", side_effect=fake_monotonic),
        patch("time.sleep"),
    ):
        monkeypatch.setattr(sys, "argv", ["collect", "--minutes", "1", "--interval", "1"])
        from collector.collect import main
        result = main()

    # 2회차가 실제로 실행됐는지 검증: run_file 이 2번 호출돼야 한다
    assert run_file_call_count["n"] == 2, (
        f"run_file 이 {run_file_call_count['n']}회 호출됐다. "
        "ValueError 이후 2회차가 실행됐다는 증거가 없다."
    )
    # written=1 이므로 main() 은 0 을 반환해야 한다
    assert result == 0, f"main() 이 {result} 를 반환했다 (0 기대)"
