import json

from collector.api import LotReading
from collector.store import append_snapshot, run_file
from collector.aggregate import build_latest, build_today


def snapshot(ts: str, gmp1_stay: int, gmp2_stay: int) -> list[LotReading]:
    return [
        LotReading("김포국제공항", "국내선 제1주차장", 2279, gmp1_stay, 0, 0, ts),
        LotReading("김포국제공항", "국내선 제2주차장", 1733, gmp2_stay, 0, 0, ts),
        LotReading("김포국제공항", "화물청사", 737, 600, 0, 0, ts),
    ]


def seed(tmp_path):
    path = run_file(tmp_path, "2026-09-15 10:00:03", run_id="1000")
    append_snapshot(path, snapshot("2026-09-15 10:00:03", 2279, 1500))
    append_snapshot(path, snapshot("2026-09-15 10:30:03", 2279, 1560))
    append_snapshot(path, snapshot("2026-09-15 11:00:03", 2279, 1620))
    return tmp_path


def test_latest_excludes_cargo_lots(tmp_path, access_path):
    latest = build_latest(seed(tmp_path), "2026-09-15", access_path)
    names = [lot["name"] for lot in latest["airports"]["GMP"]["lots"]]
    assert "화물청사" not in names
    assert "국내선 제1주차장" in names


def test_latest_reports_free_and_grade(tmp_path, access_path):
    latest = build_latest(seed(tmp_path), "2026-09-15", access_path)
    lots = {lot["name"]: lot for lot in latest["airports"]["GMP"]["lots"]}
    assert lots["국내선 제1주차장"]["free"] == 0
    assert lots["국내선 제1주차장"]["grade"] == "만차"


def test_full_lot_has_no_trend(tmp_path, access_path):
    """점유율 100%에서 카운터가 고정되므로 추세를 신뢰할 수 없다(실측 근거)."""
    latest = build_latest(seed(tmp_path), "2026-09-15", access_path)
    lots = {lot["name"]: lot for lot in latest["airports"]["GMP"]["lots"]}
    assert lots["국내선 제1주차장"]["trend"] is None


def test_non_full_lot_has_trend(tmp_path, access_path):
    latest = build_latest(seed(tmp_path), "2026-09-15", access_path)
    lots = {lot["name"]: lot for lot in latest["airports"]["GMP"]["lots"]}
    assert lots["국내선 제2주차장"]["trend"]["direction"] == "up"


def test_latest_carries_access_metadata(tmp_path, access_path):
    latest = build_latest(seed(tmp_path), "2026-09-15", access_path)
    lots = {lot["name"]: lot for lot in latest["airports"]["GMP"]["lots"]}
    assert lots["국내선 제1주차장"]["access"]["walk_min"] == [5, 7]
    assert lots["국내선 제1주차장"]["terminal"] == "국내선"


def test_today_curve_is_downsampled(tmp_path, access_path):
    today = build_today(seed(tmp_path), "2026-09-15", "GMP", access_path)
    assert today["interval_min"] == 5
    assert today["times"] == ["10:00", "10:30", "11:00"]
    assert today["lots"]["국내선 제2주차장"]["occupied"] == [1500, 1560, 1620]


def test_today_excludes_cargo(tmp_path, access_path):
    today = build_today(seed(tmp_path), "2026-09-15", "GMP", access_path)
    assert "화물청사" not in today["lots"]


def test_missing_lot_is_shown_as_unknown_not_hidden(tmp_path, access_path):
    """응답에서 빠진 주차장을 숨기면 사용자가 존재 자체를 모르게 된다.

    명세 §7: 수신 건수가 기대 건수보다 적으면 해당 카드만 '정보 없음'으로 두고
    목록에서 빼지 않는다.
    """
    path = run_file(tmp_path, "2026-09-15 10:00:03", run_id="1000")
    # 국제선 주차빌딩·국제선 지하가 통째로 빠진 응답
    append_snapshot(path, snapshot("2026-09-15 10:00:03", 2279, 1500))

    latest = build_latest(tmp_path, "2026-09-15", access_path)
    lots = {lot["name"]: lot for lot in latest["airports"]["GMP"]["lots"]}

    assert "국제선 주차빌딩" in lots
    assert lots["국제선 주차빌딩"]["grade"] == "정보 없음"
    assert lots["국제선 주차빌딩"]["free"] is None
    assert lots["국제선 주차빌딩"]["trend"] is None


def test_all_passenger_lots_always_present(tmp_path, access_path):
    """수신 여부와 무관하게 김포 여객 4곳이 항상 나온다."""
    latest = build_latest(seed(tmp_path), "2026-09-15", access_path)
    assert len(latest["airports"]["GMP"]["lots"]) == 4
