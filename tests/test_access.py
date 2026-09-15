from collector.access import load_access


def test_maps_airport_name_to_code(access_path):
    access = load_access(access_path)
    assert access.code_for("김포국제공항") == "GMP"
    assert access.code_for("김해국제공항") == "PUS"
    assert access.code_for("제주국제공항") == "CJU"
    assert access.code_for("청주국제공항") is None


def test_passenger_lots_exclude_cargo(access_path):
    access = load_access(access_path)
    assert access.is_passenger_lot("GMP", "국내선 제1주차장") is True
    assert access.is_passenger_lot("GMP", "화물청사") is False
    assert access.is_passenger_lot("CJU", "화물주차장") is False


def test_passenger_lot_count(access_path):
    """설계 확정 사양: 여객 주차장 9곳."""
    access = load_access(access_path)
    assert len(access.passenger_lots()) == 9


def test_lot_meta_carries_access_info(access_path):
    access = load_access(access_path)
    lot = access.lot_meta("GMP", "국내선 제1주차장")
    assert lot["terminal"] == "국내선"
    assert lot["walk_min"] == [5, 7]
    assert lot["confidence"] == "user"


def test_unknown_lot_returns_none(access_path):
    access = load_access(access_path)
    assert access.lot_meta("GMP", "없는주차장") is None
