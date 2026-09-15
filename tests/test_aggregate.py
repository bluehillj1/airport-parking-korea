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


GMP_PASSENGER_LOTS = {
    "국내선 제1주차장",
    "국내선 제2주차장",
    "국제선 주차빌딩",
    "국제선 지하",
}


def test_trend_span_reflects_actual_elapsed_time(tmp_path, access_path):
    """수집이 지연되면 점 개수가 아니라 실제 경과 시간을 보고해야 한다.

    20분 간격 스냅샷을 개수로 자르면 '60분 +N대'라고 표시되지만 실제로는
    훨씬 긴 시간의 변화다. 화면에 조용히 틀린 값이 뜨는 것은 이 프로젝트에서
    크래시보다 나쁜 실패다.
    """
    path = run_file(tmp_path, "2026-09-15 10:00:03", run_id="1000")
    # 10:00, 10:20, 10:40 — 20분 간격(수집기 지연). 실제 경과는 40분.
    for minute, stay in ((0, 1000), (20, 1150), (40, 1300)):
        ts = f"2026-09-15 10:{minute:02d}:03"
        append_snapshot(path, snapshot(ts, 2000, stay))

    latest = build_latest(tmp_path, "2026-09-15", access_path)
    lots = {lot["name"]: lot for lot in latest["airports"]["GMP"]["lots"]}
    trend = lots["국내선 제2주차장"]["trend"]

    assert trend["span_minutes"] == 40, (
        f"실제 경과 40분인데 {trend['span_minutes']}분으로 보고됨")
    assert trend["delta"] == 300


def test_trend_window_excludes_points_older_than_span(tmp_path, access_path):
    """3시간 시계열이라도 추세는 최근 60분만 봐야 한다."""
    path = run_file(tmp_path, "2026-09-15 09:00:03", run_id="0900")
    # 09:00~12:00, 10분 간격. 09:00에 100대에서 시작해 10분마다 +50대.
    # (만차가 되면 추세가 None이 되므로 total=1733 대비 여유를 남긴다.)
    for step in range(19):
        total_min = 9 * 60 + step * 10
        ts = f"2026-09-15 {total_min // 60:02d}:{total_min % 60:02d}:03"
        append_snapshot(path, snapshot(ts, 2000, 100 + step * 50))

    latest = build_latest(tmp_path, "2026-09-15", access_path)
    lots = {lot["name"]: lot for lot in latest["airports"]["GMP"]["lots"]}
    trend = lots["국내선 제2주차장"]["trend"]

    # 전체 구간(180분) 변화는 900대. 최근 60분(11:00~12:00)만 보면 300대.
    assert trend["delta"] == 300, f"전체 시계열이 섞였다: delta={trend['delta']}"
    assert trend["span_minutes"] == 60


def test_today_emits_entry_for_every_passenger_lot(tmp_path, access_path):
    """곡선 데이터가 없는 주차장도 항목은 있어야 한다.

    웹앱이 주차장 이름으로 곡선을 찾으므로, latest에는 있는데 today에 없으면
    TypeError로 페이지 전체가 죽는다. API가 한 곳을 빠뜨렸을 때
    카드 하나가 아니라 전체가 무너지는 셈이다.
    """
    path = run_file(tmp_path, "2026-09-15 10:00:03", run_id="1000")
    append_snapshot(path, [
        LotReading("김포국제공항", "국내선 제1주차장", 2279, 1500, 0, 0,
                   "2026-09-15 10:00:03"),
    ])

    today = build_today(tmp_path, "2026-09-15", "GMP", access_path)
    latest = build_latest(tmp_path, "2026-09-15", access_path)

    assert set(today["lots"]) == GMP_PASSENGER_LOTS
    assert set(today["lots"]) == {
        lot["name"] for lot in latest["airports"]["GMP"]["lots"]}


def test_today_total_is_none_when_lot_absent(tmp_path, access_path):
    """데이터가 없는 주차장의 total은 0이 아니라 None이다.

    0은 '주차면이 0개'라는 실제 값처럼 보여서 오해를 부른다.
    """
    path = run_file(tmp_path, "2026-09-15 10:00:03", run_id="1000")
    append_snapshot(path, [
        LotReading("김포국제공항", "국내선 제1주차장", 2279, 1500, 0, 0,
                   "2026-09-15 10:00:03"),
    ])

    today = build_today(tmp_path, "2026-09-15", "GMP", access_path)

    assert today["lots"]["국제선 주차빌딩"]["total"] is None
    assert today["lots"]["국내선 제1주차장"]["total"] == 2279


def test_today_occupied_has_none_for_gaps(tmp_path, access_path):
    """일부 시각에만 응답한 주차장은 빠진 자리에 None이 들어가야 한다.

    None 대신 값을 밀어 넣으면 곡선이 times와 어긋나 엉뚱한 시각의 값으로 보인다.
    """
    path = run_file(tmp_path, "2026-09-15 10:00:03", run_id="1000")
    # 10:00 — 두 곳 모두 응답
    append_snapshot(path, [
        LotReading("김포국제공항", "국내선 제1주차장", 2279, 1500, 0, 0,
                   "2026-09-15 10:00:03"),
        LotReading("김포국제공항", "국내선 제2주차장", 1733, 800, 0, 0,
                   "2026-09-15 10:00:03"),
    ])
    # 10:30 — 제1주차장만 응답 (제2주차장 누락)
    append_snapshot(path, [
        LotReading("김포국제공항", "국내선 제1주차장", 2279, 1600, 0, 0,
                   "2026-09-15 10:30:03"),
    ])
    # 11:00 — 두 곳 모두 응답
    append_snapshot(path, [
        LotReading("김포국제공항", "국내선 제1주차장", 2279, 1700, 0, 0,
                   "2026-09-15 11:00:03"),
        LotReading("김포국제공항", "국내선 제2주차장", 1733, 900, 0, 0,
                   "2026-09-15 11:00:03"),
    ])

    today = build_today(tmp_path, "2026-09-15", "GMP", access_path)

    assert today["times"] == ["10:00", "10:30", "11:00"]
    assert today["lots"]["국내선 제1주차장"]["occupied"] == [1500, 1600, 1700]
    assert today["lots"]["국내선 제2주차장"]["occupied"] == [800, None, 900]
