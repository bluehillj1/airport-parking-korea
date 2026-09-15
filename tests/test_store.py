from collector.api import LotReading
from collector.store import append_snapshot, load_day, run_file


def reading(lot: str, stay: int, ts: str = "2026-09-15 10:13:03") -> LotReading:
    return LotReading(airport_kor="김포국제공항", lot=lot, total=2279,
                      stay=stay, cum_in=0, cum_out=0, src_ts=ts)


def test_run_file_path_uses_source_date_not_runner_clock(tmp_path):
    """러너는 UTC다. 원천의 KST 날짜를 써야 09시에 날짜가 어긋나지 않는다."""
    path = run_file(tmp_path, "2026-09-15 10:13:03", run_id="1013")
    assert path == tmp_path / "2026-09-15" / "1013.jsonl"


def test_append_writes_one_line_per_snapshot(tmp_path):
    path = run_file(tmp_path, "2026-09-15 10:13:03", run_id="1013")
    assert append_snapshot(path, [reading("국내선 제1주차장", 2279)]) is True
    assert append_snapshot(path, [reading("국내선 제1주차장", 2270,
                                          ts="2026-09-15 10:15:03")]) is True
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_append_skips_duplicate_src_ts(tmp_path):
    """원천은 60초마다 갱신되는데 그보다 자주 폴링하면 같은 스냅샷이 온다."""
    path = run_file(tmp_path, "2026-09-15 10:13:03", run_id="1013")
    assert append_snapshot(path, [reading("국내선 제1주차장", 2279)]) is True
    assert append_snapshot(path, [reading("국내선 제1주차장", 2279)]) is False
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_load_day_dedupes_across_run_files(tmp_path):
    """실행이 겹치면 다른 파일에 같은 스냅샷이 들어간다. 로드 시 제거한다."""
    first = run_file(tmp_path, "2026-09-15 10:13:03", run_id="1000")
    second = run_file(tmp_path, "2026-09-15 10:13:03", run_id="1030")
    append_snapshot(first, [reading("국내선 제1주차장", 2279)])
    append_snapshot(second, [reading("국내선 제1주차장", 2279)])
    append_snapshot(second, [reading("국내선 제1주차장", 2270,
                                     ts="2026-09-15 10:15:03")])

    day = load_day(tmp_path, "2026-09-15")
    assert sorted(day) == ["2026-09-15 10:13:03", "2026-09-15 10:15:03"]


def test_load_day_returns_empty_when_missing(tmp_path):
    assert load_day(tmp_path, "2026-01-01") == {}
