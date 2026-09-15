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


# ── new tests: must FAIL before fixes are applied ────────────────────────────

def test_append_snapshot_survives_truncated_last_line(tmp_path):
    """CI 취소로 마지막 줄이 잘려도 다음 append_snapshot 호출이 성공해야 한다."""
    path = run_file(tmp_path, "2026-09-15 10:13:03", run_id="1013")
    # Write a valid snapshot first
    assert append_snapshot(path, [reading("국내선 제1주차장", 2279)]) is True
    # Manually append a truncated/corrupt JSON fragment (simulates CI cancel)
    with path.open("a", encoding="utf-8") as f:
        f.write('{"src_ts": "2026-09-15 10:15:03", "rows": [[\n')
    # A subsequent append with a new src_ts must succeed, not raise
    result = append_snapshot(path, [reading("국내선 제1주차장", 2270,
                                            ts="2026-09-15 10:17:03")])
    assert result is True


def test_load_day_skips_truncated_line(tmp_path):
    """잘린 줄이 있어도 load_day는 정상 줄만 반환하고 예외를 발생시키지 않아야 한다."""
    path = run_file(tmp_path, "2026-09-15 10:13:03", run_id="1013")
    # Write a valid snapshot
    assert append_snapshot(path, [reading("국내선 제1주차장", 2279)]) is True
    # Manually append a truncated fragment
    with path.open("a", encoding="utf-8") as f:
        f.write('{"src_ts": "2026-09-15 10:15:03", "rows": [[\n')
    # load_day must return the one good snapshot without raising
    day = load_day(tmp_path, "2026-09-15")
    assert list(day.keys()) == ["2026-09-15 10:13:03"]


def test_run_file_rejects_src_ts_without_space(tmp_path):
    """ISO 형식이나 빈 문자열 같은 공백 없는 src_ts는 ValueError를 발생시켜야 한다."""
    import pytest
    with pytest.raises(ValueError):
        run_file(tmp_path, "2026-09-15T10:13:03", run_id="1013")
    with pytest.raises(ValueError):
        run_file(tmp_path, "", run_id="1013")


def test_load_day_rejects_wrong_row_width(tmp_path):
    """rows 항목이 6개가 아니면 ValueError를 발생시켜야 한다 (묵시적 필드 이동 방지)."""
    import pytest
    # Write a JSONL line whose rows entry has only 5 elements
    day_dir = tmp_path / "2026-09-15"
    day_dir.mkdir(parents=True)
    bad_file = day_dir / "1013.jsonl"
    bad_file.write_text(
        '{"src_ts": "2026-09-15 10:13:03", "rows": [["김포국제공항", "국내선", 2279, 100, 50]]}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="5"):
        load_day(tmp_path, "2026-09-15")
