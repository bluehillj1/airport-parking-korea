import copy
import http.client
from unittest.mock import MagicMock, patch

import pytest

from collector.api import ApiError, LotReading, fetch, parse, representative_ts


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
    payload = copy.deepcopy(sample_payload)
    payload["response"]["body"]["items"]["item"] = \
        payload["response"]["body"]["items"]["item"][0]
    assert len(parse(payload)) == 1


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


# ---------------------------------------------------------------------------
# New tests (written before fixes — expected to FAIL until fixes are applied)
# ---------------------------------------------------------------------------

def _make_urlopen_mock(read_return_value=None, read_side_effect=None):
    """resp context manager mock where resp.read() is configurable."""
    resp_mock = MagicMock()
    if read_side_effect is not None:
        resp_mock.read.side_effect = read_side_effect
    else:
        resp_mock.read.return_value = read_return_value

    cm_mock = MagicMock()
    cm_mock.__enter__.return_value = resp_mock
    cm_mock.__exit__.return_value = False
    return cm_mock


def test_fetch_wraps_incomplete_read():
    """resp.read() raising IncompleteRead must surface as ApiError, not leak."""
    exc = http.client.IncompleteRead(b"")
    mock_cm = _make_urlopen_mock(read_side_effect=exc)
    with patch("urllib.request.urlopen", return_value=mock_cm):
        with pytest.raises(ApiError):
            fetch("DUMMY_KEY")


def test_fetch_wraps_timeout():
    """urlopen raising TimeoutError must surface as ApiError."""
    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        with pytest.raises(ApiError):
            fetch("DUMMY_KEY")


def test_fetch_wraps_non_json():
    """Non-JSON response body must surface as ApiError, not JSONDecodeError."""
    mock_cm = _make_urlopen_mock(read_return_value=b"<html>error</html>")
    with patch("urllib.request.urlopen", return_value=mock_cm):
        with pytest.raises(ApiError):
            fetch("DUMMY_KEY")


def test_parse_handles_null_body():
    """body: null in JSON must not raise AttributeError; return empty list."""
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": None,
        }
    }
    result = parse(payload)
    assert result == []


def test_parse_missing_timestamp_does_not_win_max():
    """An item missing date/time fields must not beat a real timestamp in max()."""
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": {
                "items": {
                    "item": [
                        {
                            "aprKor": "김포국제공항",
                            "parkingAirportCodeName": "국내선 제1주차장",
                            "parkingFullSpace": "100",
                            "parkingIstay": "50",
                            "parkingIincnt": "10",
                            "parkingIoutcnt": "5",
                            "parkingGetdate": "2026-09-15",
                            "parkingGettime": "10:13:03",
                        },
                        {
                            "aprKor": "제주국제공항",
                            "parkingAirportCodeName": "P1주차장",
                            "parkingFullSpace": "200",
                            "parkingIstay": "100",
                            "parkingIincnt": "20",
                            "parkingIoutcnt": "10",
                            # parkingGetdate and parkingGettime intentionally absent
                        },
                    ]
                }
            },
        }
    }
    readings = parse(payload)
    ts = representative_ts(readings)
    assert "None" not in ts
    assert ts == "2026-09-15 10:13:03"
