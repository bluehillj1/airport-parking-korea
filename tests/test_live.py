import pytest

from collector.access import load_access
from collector.api import LotReading
from collector.live import build_live


def reading(airport_kor, lot, total, stay, src_ts="2026-09-15 10:13:03"):
    return LotReading(airport_kor=airport_kor, lot=lot, total=total, stay=stay,
                      cum_in=0, cum_out=0, src_ts=src_ts)


@pytest.fixture
def access(access_path):
    return load_access(access_path)


def lots_of(result, code):
    return {lot["name"]: lot for lot in result["airports"][code]["lots"]}


def test_computes_free_and_grade(access):
    result = build_live([reading("김포국제공항", "국내선 제1주차장", 2279, 1800)], access)
    lot = lots_of(result, "GMP")["국내선 제1주차장"]
    assert (lot["total"], lot["occupied"], lot["free"]) == (2279, 1800, 479)
    assert lot["grade"] == "여유"


def test_missing_lot_stays_visible_as_unknown(access):
    """응답에서 빠진 주차장이 화면에서 사라지면 사용자는 그 존재조차 모른다.

    하필 API가 불안정할 때 일어나는 일이라, 조용히 빠지는 대신 '정보 없음'으로
    남아 있어야 한다.
    """
    result = build_live([reading("김포국제공항", "국내선 제1주차장", 2279, 1800)], access)
    absent = lots_of(result, "GMP")["국내선 제2주차장"]
    assert absent["grade"] == "정보 없음"
    assert absent["total"] is None
    assert absent["occupied"] is None
    assert absent["free"] is None


def test_all_passenger_lots_present_even_with_no_readings(access):
    result = build_live([], access)
    names = {code: set(lots_of(result, code))
             for code in ("GMP", "PUS", "CJU", "CJJ")}
    assert len(names["GMP"]) == 4      # 화물청사는 여객용이 아니라 제외
    assert len(names["PUS"]) == 3
    assert len(names["CJU"]) == 2
    assert len(names["CJJ"]) == 4
    assert result["source_ts"] is None


def test_cheongju_third_lot_is_listed_despite_zero_capacity(access):
    """원천이 전체 면수를 0으로 준다(실측). 목록에서 빼면 값이 들어오기 시작해도
    영영 보이지 않는다."""
    result = build_live([reading("청주국제공항", "여객 제3주차장", 0, 0)], access)
    lot = lots_of(result, "CJJ")["여객 제3주차장"]
    assert lot["grade"] == "정보 없음"
    assert lot["free"] is None


def test_cargo_lots_are_excluded(access):
    result = build_live([reading("김포국제공항", "화물청사", 100, 10)], access)
    assert "화물청사" not in lots_of(result, "GMP")


def test_zero_capacity_is_unknown_not_full(access):
    """전체 면수 0은 '만차'가 아니라 '모른다'다. 0으로 나누어서도 안 된다."""
    result = build_live([reading("제주국제공항", "P1주차장", 0, 0)], access)
    lot = lots_of(result, "CJU")["P1주차장"]
    assert lot["grade"] == "정보 없음"
    assert lot["free"] is None


def test_source_ts_takes_the_latest_row(access):
    """같은 응답 안에서도 주차장마다 초가 다르다(실측 10:13:03 / :04).

    행 순서에 흔들리면 신선도 표시가 들쭉날쭉해진다.
    """
    result = build_live([
        reading("김포국제공항", "국내선 제1주차장", 2279, 1800, "2026-09-15 10:13:04"),
        reading("김포국제공항", "국내선 제2주차장", 1763, 900, "2026-09-15 10:13:03"),
    ], access)
    assert result["source_ts"] == "2026-09-15 10:13:04"


def test_access_metadata_is_joined(access):
    result = build_live([reading("김해국제공항", "P3 여객(화물)", 500, 100)], access)
    lot = lots_of(result, "PUS")["P3 여객(화물)"]
    assert lot["access"]["requires_shuttle"] is True
    assert lot["terminal"] == "국내선"
    assert result["airports"]["PUS"]["shuttle"]["headway_min"] == [10, 10]


def test_unverified_walk_time_is_not_invented(access):
    """근거 없는 도보시간을 숫자로 내보내면 앱이 그대로 표시해버린다."""
    result = build_live([reading("김포국제공항", "국제선 주차빌딩", 400, 100)], access)
    lot = lots_of(result, "GMP")["국제선 주차빌딩"]
    assert lot["access"]["walk_min"] is None
    assert lot["access"]["confidence"] == "unverified"


def test_no_trend_field_is_emitted(access):
    """서버는 이력을 모른다. 추세를 담는 척하면 앱이 빈 값을 그린다."""
    result = build_live([reading("김포국제공항", "국내선 제1주차장", 2279, 1800)], access)
    assert "trend" not in lots_of(result, "GMP")["국내선 제1주차장"]
