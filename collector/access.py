"""주차장 접근성 메타데이터.

실시간 API로 오지 않는 정적 정보다. 조인 키는 (공항 국문명, 주차장명)이며
한 글자라도 다르면 접근성 정보가 조용히 사라진다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Access:
    airports: dict          # 공항코드 -> {name_kor, terminals, shuttle}
    lots: list[dict]        # lot_access.json의 lots 배열 그대로

    def code_for(self, airport_kor: str) -> str | None:
        for code, airport in self.airports.items():
            if airport["name_kor"] == airport_kor:
                return code
        return None

    def lot_meta(self, code: str, lot_name: str) -> dict | None:
        for lot in self.lots:
            if lot["airport"] == code and lot["name"] == lot_name:
                return lot
        return None

    def is_passenger_lot(self, code: str, lot_name: str) -> bool:
        meta = self.lot_meta(code, lot_name)
        return bool(meta and meta["passenger_use"])

    def passenger_lots(self) -> list[dict]:
        return [lot for lot in self.lots if lot["passenger_use"]]

    def shuttle_for(self, code: str) -> dict | None:
        return self.airports.get(code, {}).get("shuttle")


REQUIRED_LOT_KEYS = ("airport", "name", "terminal", "passenger_use", "confidence")


def _validate(airports, lots) -> None:
    """어긋난 곳을 여기서 이름 붙여 터뜨린다.

    lot 의 airport 가 airports 에 없으면 build_live 가 KeyError 로 죽는데, 그건
    api/parking.py 의 어떤 except 에도 걸리지 않는다. 사용자는 빈 500을 받고
    로그에는 스택트레이스만 남아, 원인이 '주차장 한 곳의 공항 코드 오타'라는
    사실을 아무도 알 수 없다. 불러오는 자리에서 확인하면 한 줄로 끝난다.
    """
    if not isinstance(airports, dict) or not airports:
        raise ValueError("airports 가 비어 있거나 객체가 아니다")
    if not isinstance(lots, list) or not lots:
        raise ValueError("lots 가 비어 있거나 배열이 아니다")

    for code, airport in airports.items():
        if not isinstance(airport, dict) or not airport.get("name_kor"):
            raise ValueError(f"공항 {code} 에 name_kor 이 없다")

    for index, lot in enumerate(lots):
        if not isinstance(lot, dict):
            raise ValueError(f"lots[{index}] 가 객체가 아니다")
        missing = [key for key in REQUIRED_LOT_KEYS if key not in lot]
        if missing:
            raise ValueError(f"lots[{index}] 에 빠진 항목: {', '.join(missing)}")
        if lot["airport"] not in airports:
            raise ValueError(f"lots[{index}] ({lot['name']}) 의 airport "
                             f"'{lot['airport']}' 가 airports 에 없다")


def load_access(path: Path) -> Access:
    """읽고, 검증하고, 통과한 것만 돌려준다.

    형식이 깨졌으면 ValueError 다. json.JSONDecodeError 도 ValueError 라서
    부르는 쪽은 한 종류만 잡으면 된다.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "airports" not in raw or "lots" not in raw:
        raise ValueError("lot_access.json 에 airports·lots 가 모두 있어야 한다")
    _validate(raw["airports"], raw["lots"])
    return Access(airports=raw["airports"], lots=raw["lots"])
