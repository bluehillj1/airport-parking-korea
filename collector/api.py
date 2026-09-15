"""한국공항공사 전국공항 실시간 주차정보 API.

네트워크를 아는 유일한 모듈이다. 나머지 모듈은 LotReading 리스트만 다룬다.
"""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

ENDPOINT = "https://apis.data.go.kr/B551178/parking-realtime-status/info"


class ApiError(Exception):
    """API가 정상 응답을 주지 않았다."""


@dataclass(frozen=True)
class LotReading:
    airport_kor: str
    lot: str
    total: int
    stay: int
    cum_in: int
    cum_out: int
    src_ts: str


def _as_int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def parse(payload: dict) -> list[LotReading]:
    # 인증 실패는 전혀 다른 봉투로 온다
    if "OpenAPI_ServiceResponse" in payload:
        header = payload["OpenAPI_ServiceResponse"].get("cmmMsgHeader", {})
        raise ApiError(header.get("errMsg", "unknown auth error"))

    response = payload.get("response") or {}
    header = response.get("header", {})
    if header.get("resultCode") != "00":
        raise ApiError(header.get("resultMsg", "unknown error"))

    body = response.get("body") or {}
    items = body.get("items") or {}
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):  # 1건일 때 dict로 오는 경우
        items = [items]

    readings: list[LotReading] = []
    for item in items:
        date_part = item.get("parkingGetdate") or ""
        time_part = item.get("parkingGettime") or ""
        readings.append(
            LotReading(
                airport_kor=item.get("aprKor", ""),
                lot=item.get("parkingAirportCodeName", ""),
                total=_as_int(item.get("parkingFullSpace")),
                stay=_as_int(item.get("parkingIstay")),
                cum_in=_as_int(item.get("parkingIincnt")),
                cum_out=_as_int(item.get("parkingIoutcnt")),
                src_ts=f"{date_part} {time_part}".strip(),
            )
        )
    return readings


def representative_ts(readings: list[LotReading]) -> str:
    """대표 원천 타임스탬프.

    실측 결과 같은 응답 안에서도 주차장마다 초가 1초씩 다르다(10:13:03 / :04).
    행 순서에 흔들리지 않도록 최댓값을 쓴다.
    """
    if not readings:
        raise ApiError("empty response")
    return max(r.src_ts for r in readings)


def fetch(service_key: str, timeout: float = 15.0) -> list[LotReading]:
    """API를 1회 호출한다. schAirportCode를 생략해 25개 전량을 1회에 받는다."""
    key = service_key if "%" in service_key else urllib.parse.quote(service_key, safe="")
    query = urllib.parse.urlencode({"pageNo": 1, "numOfRows": 100, "type": "json"})
    url = f"{ENDPOINT}?serviceKey={key}&{query}"

    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (OSError, http.client.HTTPException) as exc:
        raise ApiError(f"network: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(f"non-JSON response: {raw[:200]}") from exc

    return parse(payload)
