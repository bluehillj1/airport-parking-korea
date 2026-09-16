import json

import pytest

from collector.access import load_access


def write(tmp_path, payload):
    path = tmp_path / "lot_access.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


AIRPORTS = {"GMP": {"name_kor": "김포국제공항"}}
LOT = {"airport": "GMP", "name": "국내선 제1주차장", "terminal": "국내선",
       "passenger_use": True, "confidence": "user"}


def test_maps_airport_name_to_code(access_path):
    access = load_access(access_path)
    assert access.code_for("김포국제공항") == "GMP"
    assert access.code_for("김해국제공항") == "PUS"
    assert access.code_for("제주국제공항") == "CJU"
    assert access.code_for("청주국제공항") == "CJJ"
    # 원천은 전국 13개 공항을 주지만 앱이 다루는 곳은 위 넷뿐이다.
    assert access.code_for("대구국제공항") is None


def test_passenger_lots_exclude_cargo(access_path):
    access = load_access(access_path)
    assert access.is_passenger_lot("GMP", "국내선 제1주차장") is True
    assert access.is_passenger_lot("GMP", "화물청사") is False
    assert access.is_passenger_lot("CJU", "화물주차장") is False


def test_passenger_lot_count(access_path):
    """김포 4 · 김해 3 · 제주 2 · 청주 4 = 13곳.

    화물 전용(김포 화물청사, 제주 화물주차장) 2곳은 제외된다.
    """
    access = load_access(access_path)
    assert len(access.passenger_lots()) == 13


def test_lot_meta_carries_access_info(access_path):
    access = load_access(access_path)
    lot = access.lot_meta("GMP", "국내선 제1주차장")
    assert lot["terminal"] == "국내선"
    assert lot["walk_min"] == [5, 7]
    assert lot["confidence"] == "user"


def test_unknown_lot_returns_none(access_path):
    access = load_access(access_path)
    assert access.lot_meta("GMP", "없는주차장") is None


def test_real_file_passes_validation(access_path):
    """검증을 켜 놓고 실제 파일이 걸리면 앱 전체가 500이 된다."""
    assert len(load_access(access_path).lots) == 15


def test_lot_pointing_at_unknown_airport_is_rejected(tmp_path):
    """공항 코드 오타는 build_live 안에서 KeyError 로 터져 스택트레이스만 남았다.

    불러오는 자리에서 어느 주차장이 문제인지 이름을 붙여 거부한다.
    """
    path = write(tmp_path, {"airports": AIRPORTS,
                            "lots": [dict(LOT, airport="CHJ")]})
    with pytest.raises(ValueError, match="CHJ"):
        load_access(path)


def test_lot_missing_required_keys_is_rejected(tmp_path):
    broken = {key: value for key, value in LOT.items() if key != "passenger_use"}
    path = write(tmp_path, {"airports": AIRPORTS, "lots": [broken]})
    with pytest.raises(ValueError, match="passenger_use"):
        load_access(path)


def test_airport_without_korean_name_is_rejected(tmp_path):
    """name_kor 은 원천 응답과 맞대는 유일한 조인 키다."""
    path = write(tmp_path, {"airports": {"GMP": {}}, "lots": [LOT]})
    with pytest.raises(ValueError, match="name_kor"):
        load_access(path)


@pytest.mark.parametrize("payload", [
    {},
    {"airports": AIRPORTS},
    {"airports": {}, "lots": [LOT]},
    {"airports": AIRPORTS, "lots": []},
])
def test_structurally_empty_file_is_rejected(tmp_path, payload):
    with pytest.raises(ValueError):
        load_access(write(tmp_path, payload))
