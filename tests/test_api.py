import pytest

from collector.api import ApiError, LotReading, parse, representative_ts


def test_parse_returns_all_rows(sample_payload):
    readings = parse(sample_payload)
    assert len(readings) == 7
    assert isinstance(readings[0], LotReading)


def test_parse_maps_fields(sample_payload):
    first = parse(sample_payload)[0]
    assert first.airport_kor == "김포국제공항"
    assert first.lot == "국내선 제1주차장"
    assert first.total == 2279
    assert first.stay == 2279
    assert first.cum_in == 1833
    assert first.cum_out == 1179
    assert first.src_ts == "2026-09-15 10:13:03"


def test_parse_accepts_single_item_as_dict(sample_payload):
    """items.item이 1건일 때 dict로 오는 경우를 방어한다."""
    sample_payload["response"]["body"]["items"]["item"] = \
        sample_payload["response"]["body"]["items"]["item"][0]
    assert len(parse(sample_payload)) == 1


def test_parse_raises_on_auth_envelope():
    payload = {"OpenAPI_ServiceResponse": {"cmmMsgHeader": {
        "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}}}
    with pytest.raises(ApiError, match="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"):
        parse(payload)


def test_parse_raises_on_error_result_code():
    payload = {"response": {"header": {"resultCode": "99", "resultMsg": "ERROR"},
                            "body": {}}}
    with pytest.raises(ApiError, match="ERROR"):
        parse(payload)


def test_representative_ts_is_max_and_order_independent(sample_payload):
    """같은 응답 안에서도 주차장마다 초가 1초씩 다르다(실측 확인).

    첫 행의 값을 쓰면 행 순서가 바뀔 때 갱신이 없어도 변화로 오인한다.
    """
    readings = parse(sample_payload)
    assert representative_ts(readings) == "2026-09-15 10:13:04"
    assert representative_ts(list(reversed(readings))) == "2026-09-15 10:13:04"
