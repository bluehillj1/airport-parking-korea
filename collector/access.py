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


def load_access(path: Path) -> Access:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Access(airports=raw["airports"], lots=raw["lots"])
