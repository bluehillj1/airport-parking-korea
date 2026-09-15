# 공항 주차장 실시간 현황·추세 앱 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 김포·김해·제주공항 주차장의 실시간 잔여면수와 추세를 휴대폰에서 3초 안에 확인할 수 있는 정적 웹앱을 만든다.

**Architecture:** GitHub Actions가 2분마다 한국공항공사 API를 호출해 `raw/`에 원본을 쌓고, 같은 실행에서 집계해 `public/data/`에 앱용 경량 JSON을 내보낸다. GitHub Pages가 `public/`을 서빙하고, 휴대폰 브라우저는 정적 JSON만 읽는다. 서비스키는 Actions Secrets에만 존재하며 브라우저로 나가지 않는다.

**Tech Stack:** Python 3.12+ (런타임은 표준 라이브러리만, 테스트는 pytest), 바닐라 HTML/CSS/JS (빌드 도구 없음), GitHub Actions, GitHub Pages.

**설계 문서:** `docs/superpowers/specs/2026-09-15-airport-parking-app-design.md`

---

## 파일 구조

```
collector/
  __init__.py
  api.py         API 호출·응답 파싱. 네트워크 경계를 여기로 격리한다
  access.py      data/lot_access.json 로딩. 공항코드 매핑과 여객 주차장 필터
  store.py       raw JSONL 읽기/쓰기. src_ts 기준 중복 제거
  grading.py     등급·추세·다운샘플. 순수 함수만. 앱 표시 규칙의 단일 출처
  collect.py     CLI 진입점: 주기적으로 호출해 raw에 적재
  aggregate.py   CLI 진입점: raw → public/data/*.json

tests/
  conftest.py
  fixtures/sample_response.json
  test_api.py
  test_access.py
  test_store.py
  test_grading.py
  test_aggregate.py

public/
  index.html     앱 화면 (단일 페이지)
  app.js         데이터 로딩·렌더
  style.css
  data/          생성물 — latest.json, today-GMP.json, today-PUS.json, today-CJU.json

raw/YYYY-MM-DD/HHMM.jsonl    생성물 — 실행 1회당 파일 1개

.github/workflows/
  collect.yml    30분마다 트리거, 35분간 2분 간격 수집 후 커밋
  pages.yml      public/ 변경 시 Pages 배포
```

**왜 이렇게 나누는가**

- `api.py`만 네트워크를 안다. 나머지는 전부 순수 함수라 픽스처로 테스트된다
- `grading.py`는 등급·추세 규칙의 단일 출처다. 서버에서 계산해 JSON에 담으므로 웹앱은 규칙을 몰라도 되고, 규칙 변경은 파이썬 테스트로 검증된다
- raw는 **실행 1회당 새 파일**을 쓴다. 하나의 큰 파일에 append하면 커밋마다 전체 blob이 다시 저장되어 git이 급속히 비대해진다

**날짜 기준 주의:** 파일 경로의 날짜는 **반드시 API 응답의 `parkingGetdate`(KST)를 쓴다.** Actions 러너는 UTC라 러너 시계를 쓰면 매일 09:00 KST에 날짜가 어긋난다.

---

## Task 1: 프로젝트 골격과 테스트 픽스처

**Files:**
- Create: `collector/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/sample_response.json`
- Create: `pytest.ini`
- Create: `requirements-dev.txt`

- [ ] **Step 1: 패키지와 설정 파일 만들기**

`collector/__init__.py` — 빈 파일.

`requirements-dev.txt`:
```
pytest>=8.0
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q
```

- [ ] **Step 2: 실측 응답 픽스처 만들기**

`tests/fixtures/sample_response.json` — 2026-09-15 실측 응답을 축약한 것. 대상 3개 공항 + 경계 사례(전체 면수 0)를 포함한다.

```json
{
  "response": {
    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
    "body": {
      "numOfRows": 100,
      "pageNo": 1,
      "totalCount": 7,
      "items": {
        "item": [
          {"parkingGetdate": "2026-09-15", "parkingGettime": "10:13:03", "parkingFullSpace": "2279", "aprKor": "김포국제공항", "aprEng": "GIMPO INTERNATIONAL AIRPORT", "parkingAirportCodeName": "국내선 제1주차장", "parkingIincnt": "1833", "parkingIoutcnt": "1179", "parkingIstay": "2279"},
          {"parkingGetdate": "2026-09-15", "parkingGettime": "10:13:03", "parkingFullSpace": "1733", "aprKor": "김포국제공항", "aprEng": "GIMPO INTERNATIONAL AIRPORT", "parkingAirportCodeName": "국내선 제2주차장", "parkingIincnt": "1024", "parkingIoutcnt": "623", "parkingIstay": "1629"},
          {"parkingGetdate": "2026-09-15", "parkingGettime": "10:13:04", "parkingFullSpace": "567", "aprKor": "김포국제공항", "aprEng": "GIMPO INTERNATIONAL AIRPORT", "parkingAirportCodeName": "국제선 주차빌딩", "parkingIincnt": "681", "parkingIoutcnt": "556", "parkingIstay": "406"},
          {"parkingGetdate": "2026-09-15", "parkingGettime": "10:13:03", "parkingFullSpace": "737", "aprKor": "김포국제공항", "aprEng": "GIMPO INTERNATIONAL AIRPORT", "parkingAirportCodeName": "화물청사", "parkingIincnt": "2859", "parkingIoutcnt": "2481", "parkingIstay": "647"},
          {"parkingGetdate": "2026-09-15", "parkingGettime": "10:13:03", "parkingFullSpace": "2453", "aprKor": "김해국제공항", "aprEng": "GIMHAE INTERNATIONAL AIRPORT", "parkingAirportCodeName": "P2 여객주차장", "parkingIincnt": "1174", "parkingIoutcnt": "1006", "parkingIstay": "2443"},
          {"parkingGetdate": "2026-09-15", "parkingGettime": "10:13:03", "parkingFullSpace": "1763", "aprKor": "제주국제공항", "aprEng": "JEJU INTERNATIONAL AIRPORT", "parkingAirportCodeName": "P1주차장", "parkingIincnt": "4023", "parkingIoutcnt": "3335", "parkingIstay": "1695"},
          {"parkingGetdate": "2026-09-15", "parkingGettime": "10:13:03", "parkingFullSpace": "0", "aprKor": "청주국제공항", "aprEng": "CHEONGJU INTERNATIONAL AIRPORT", "parkingAirportCodeName": "여객 제3주차장", "parkingIincnt": "0", "parkingIoutcnt": "0", "parkingIstay": "0"}
        ]
      }
    }
  }
}
```

- [ ] **Step 3: conftest에 픽스처 로더 추가**

`tests/conftest.py`:
```python
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_payload() -> dict:
    return json.loads((FIXTURES / "sample_response.json").read_text(encoding="utf-8"))


@pytest.fixture
def access_path() -> Path:
    return Path(__file__).parent.parent / "data" / "lot_access.json"
```

- [ ] **Step 4: 테스트가 수집되는지 확인**

Run: `python -m pytest --collect-only`
Expected: `no tests ran` (에러 없이 0건 수집). `collected 0 items`가 보이면 정상.

- [ ] **Step 5: 커밋**

```bash
git add collector/__init__.py tests/ pytest.ini requirements-dev.txt
git commit -m "chore: 프로젝트 골격과 실측 기반 테스트 픽스처 추가"
```

---

## Task 2: 응답 파싱 (`collector/api.py`)

**Files:**
- Create: `collector/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_api.py`:
```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'collector.api'`

- [ ] **Step 3: 구현**

`collector/api.py`:
```python
"""한국공항공사 전국공항 실시간 주차정보 API.

네트워크를 아는 유일한 모듈이다. 나머지 모듈은 LotReading 리스트만 다룬다.
"""

from __future__ import annotations

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

    response = payload.get("response", {})
    header = response.get("header", {})
    if header.get("resultCode") != "00":
        raise ApiError(header.get("resultMsg", "unknown error"))

    items = response.get("body", {}).get("items") or {}
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):  # 1건일 때 dict로 오는 경우
        items = [items]

    return [
        LotReading(
            airport_kor=item.get("aprKor", ""),
            lot=item.get("parkingAirportCodeName", ""),
            total=_as_int(item.get("parkingFullSpace")),
            stay=_as_int(item.get("parkingIstay")),
            cum_in=_as_int(item.get("parkingIincnt")),
            cum_out=_as_int(item.get("parkingIoutcnt")),
            src_ts=f"{item.get('parkingGetdate')} {item.get('parkingGettime')}",
        )
        for item in items
    ]


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
    except urllib.error.URLError as exc:
        raise ApiError(f"network: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(f"non-JSON response: {raw[:200]}") from exc

    return parse(payload)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_api.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: 커밋**

```bash
git add collector/api.py tests/test_api.py
git commit -m "feat: API 응답 파서. 대표 타임스탬프는 최댓값 사용"
```

---

## Task 3: 접근성 메타데이터 로딩 (`collector/access.py`)

**Files:**
- Create: `collector/access.py`
- Test: `tests/test_access.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_access.py`:
```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_access.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'collector.access'`

- [ ] **Step 3: 구현**

`collector/access.py`:
```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_access.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: 커밋**

```bash
git add collector/access.py tests/test_access.py
git commit -m "feat: 접근성 메타데이터 로딩과 여객 주차장 필터"
```

---

## Task 4: 원본 저장과 중복 제거 (`collector/store.py`)

**Files:**
- Create: `collector/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_store.py`:
```python
from collector.api import LotReading
from collector.store import append_snapshot, load_day, run_file


def reading(lot: str, stay: int, ts: str = "2026-09-15 10:13:03") -> LotReading:
    return LotReading(airport_kor="김포국제공항", lot=lot, total=2279,
                      stay=stay, cum_in=0, cum_out=0, src_ts=ts)


def test_run_file_path_uses_source_date_not_runner_clock(tmp_path):
    """러너는 UTC다. 원천의 KST 날짜를 써야 09시에 날짜가 어긋나지 않는다."""
    path = run_file(tmp_path, "2026-09-15 10:13:03", run_id="1013")
    assert path == tmp_path / "2026-09-15" / "1013.jsonl"


def test_append_writes_one_line_per_snapshot(tmp_path):
    path = run_file(tmp_path, "2026-09-15 10:13:03", run_id="1013")
    assert append_snapshot(path, [reading("국내선 제1주차장", 2279)]) is True
    assert append_snapshot(path, [reading("국내선 제1주차장", 2270,
                                          ts="2026-09-15 10:15:03")]) is True
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_append_skips_duplicate_src_ts(tmp_path):
    """원천은 60초마다 갱신되는데 그보다 자주 폴링하면 같은 스냅샷이 온다."""
    path = run_file(tmp_path, "2026-09-15 10:13:03", run_id="1013")
    assert append_snapshot(path, [reading("국내선 제1주차장", 2279)]) is True
    assert append_snapshot(path, [reading("국내선 제1주차장", 2279)]) is False
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_load_day_dedupes_across_run_files(tmp_path):
    """실행이 겹치면 다른 파일에 같은 스냅샷이 들어간다. 로드 시 제거한다."""
    first = run_file(tmp_path, "2026-09-15 10:13:03", run_id="1000")
    second = run_file(tmp_path, "2026-09-15 10:13:03", run_id="1030")
    append_snapshot(first, [reading("국내선 제1주차장", 2279)])
    append_snapshot(second, [reading("국내선 제1주차장", 2279)])
    append_snapshot(second, [reading("국내선 제1주차장", 2270,
                                     ts="2026-09-15 10:15:03")])

    day = load_day(tmp_path, "2026-09-15")
    assert sorted(day) == ["2026-09-15 10:13:03", "2026-09-15 10:15:03"]


def test_load_day_returns_empty_when_missing(tmp_path):
    assert load_day(tmp_path, "2026-01-01") == {}
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'collector.store'`

- [ ] **Step 3: 구현**

`collector/store.py`:
```python
"""원본 스냅샷 저장소.

실행 1회당 파일 1개를 쓴다. 하나의 큰 파일에 append하면 커밋마다 전체 blob이
다시 저장되어 git이 급격히 커진다.

중복 제거 키는 원천이 스스로 찍은 타임스탬프(src_ts)다. 덕분에 수집기를
겹쳐 돌려도 데이터가 오염되지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

from collector.api import LotReading, representative_ts


def run_file(root: Path, src_ts: str, run_id: str) -> Path:
    """raw/YYYY-MM-DD/HHMM.jsonl

    날짜는 반드시 원천 타임스탬프(KST)에서 가져온다. Actions 러너는 UTC라
    러너 시계를 쓰면 매일 09:00 KST에 날짜가 하루 어긋난다.
    """
    day = src_ts.split(" ")[0]
    return Path(root) / day / f"{run_id}.jsonl"


def append_snapshot(path: Path, readings: list[LotReading]) -> bool:
    """스냅샷 1건을 한 줄로 덧붙인다. 이미 있는 src_ts면 건너뛰고 False를 반환한다."""
    if not readings:
        return False
    src_ts = representative_ts(readings)

    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and json.loads(line)["src_ts"] == src_ts:
                return False

    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "src_ts": src_ts,
        "rows": [
            [r.airport_kor, r.lot, r.total, r.stay, r.cum_in, r.cum_out]
            for r in readings
        ],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return True


def load_day(root: Path, day: str) -> dict[str, list[LotReading]]:
    """그날의 모든 실행 파일을 읽어 src_ts로 중복 제거한 스냅샷 맵을 돌려준다."""
    directory = Path(root) / day
    if not directory.is_dir():
        return {}

    snapshots: dict[str, list[LotReading]] = {}
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            snapshots[record["src_ts"]] = [
                LotReading(airport_kor=row[0], lot=row[1], total=row[2],
                           stay=row[3], cum_in=row[4], cum_out=row[5],
                           src_ts=record["src_ts"])
                for row in record["rows"]
            ]
    return snapshots
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_store.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: 커밋**

```bash
git add collector/store.py tests/test_store.py
git commit -m "feat: 원본 저장소. src_ts 기준 중복 제거로 겹침 수집 안전화"
```

---

## Task 5: 등급·추세 규칙 (`collector/grading.py`)

**Files:**
- Create: `collector/grading.py`
- Test: `tests/test_grading.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_grading.py`:
```python
import pytest

from collector.grading import compute_trend, downsample, grade


@pytest.mark.parametrize("free,total,expected", [
    (0, 2279, "만차"),
    (-3, 2279, "만차"),        # 음수 방어
    (1, 2279, "혼잡"),
    (30, 2279, "혼잡"),
    (31, 2279, "혼잡"),        # 31면이어도 점유율 98.6%라 혼잡
    (200, 1000, "보통"),       # 점유율 80%. 면수도 비율도 혼잡 기준에 못 미친다
    (31, 200, "보통"),         # 점유율 84.5%
    (100, 200, "여유"),        # 점유율 50%
])
def test_grade_boundaries(free, total, expected):
    assert grade(free, total) == expected


def test_grade_handles_zero_total():
    """청주 여객 제3주차장은 전체 면수가 0이다(실측). 0으로 나누면 안 된다."""
    assert grade(0, 0) == "정보 없음"


def test_trend_reports_direction_when_significant():
    trend = compute_trend(series=[1500, 1520, 1560], total=1733, span_minutes=60)
    assert trend["direction"] == "up"
    assert trend["delta"] == 60
    assert trend["significant"] is True


def test_trend_is_insignificant_below_one_percent():
    """2005면 주차장의 12대 증가(0.6%)를 상승 추세로 보여주면 없는 추세를 만든다."""
    trend = compute_trend(series=[1900, 1912], total=2005, span_minutes=60)
    assert trend["significant"] is False
    assert trend["direction"] == "flat"


def test_trend_minimum_absolute_threshold():
    """작은 주차장에서 1%는 1~2대다. 최소 3대는 움직여야 방향을 말한다."""
    trend = compute_trend(series=[100, 102], total=200, span_minutes=60)
    assert trend["significant"] is False


def test_trend_is_none_with_single_point():
    """수집 시작 직후에는 추세가 없다."""
    assert compute_trend(series=[1500], total=1733, span_minutes=60) is None


def test_downsample_keeps_last_value_in_each_bucket():
    points = [("10:00", 10), ("10:02", 11), ("10:04", 12), ("10:06", 20)]
    assert downsample(points, interval_min=5) == [("10:00", 12), ("10:05", 20)]


def test_downsample_keeps_final_bucket():
    """마지막 값이 누락되면 지금 상황이 화면에서 빠진다."""
    points = [("10:00", 10), ("10:07", 25)]
    assert downsample(points, interval_min=5)[-1] == ("10:05", 25)
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_grading.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'collector.grading'`

- [ ] **Step 3: 구현**

`collector/grading.py`:
```python
"""등급·추세 계산. 표시 규칙의 단일 출처다.

서버에서 계산해 JSON에 담으므로 웹앱은 규칙을 알 필요가 없고, 규칙 변경은
파이썬 테스트로 검증된다.
"""

from __future__ import annotations

UNKNOWN = "정보 없음"


def grade(free: int, total: int) -> str:
    """면수와 비율을 함께 본다.

    비율만 쓰면 작은 주차장이 여유해 보이고, 면수만 쓰면 큰 주차장이 과대평가된다.
    """
    if total <= 0:
        return UNKNOWN
    if free <= 0:
        return "만차"
    occupancy = (total - free) / total * 100
    if free <= 30 or occupancy >= 95:
        return "혼잡"
    if occupancy >= 80:
        return "보통"
    return "여유"


def is_significant(delta: int, total: int) -> bool:
    """규모 대비 1% 미만(최소 3대)의 변화는 방향을 단정하지 않는다."""
    return abs(delta) >= max(3, total * 0.01)


def compute_trend(series: list[int], total: int, span_minutes: int) -> dict | None:
    """최근 구간의 순증감. 데이터가 1점뿐이면 None."""
    if len(series) < 2:
        return None
    delta = series[-1] - series[0]
    significant = is_significant(delta, total)
    if not significant:
        direction = "flat"
    else:
        direction = "up" if delta > 0 else "down"
    return {
        "delta": delta,
        "direction": direction,
        "significant": significant,
        "span_minutes": span_minutes,
    }


def downsample(points: list[tuple[str, int]], interval_min: int) -> list[tuple[str, int]]:
    """HH:MM 격자로 내려 각 구간의 마지막 값을 남긴다.

    수집은 촘촘하게 하고 앱에 내보낼 때만 성기게 한다. 휴대폰이 받는 용량을
    줄이면서 곡선 모양은 유지된다.
    """
    buckets: dict[str, int] = {}
    for stamp, value in points:
        hour, minute = (int(part) for part in stamp.split(":")[:2])
        bucket_min = minute - (minute % interval_min)
        buckets[f"{hour:02d}:{bucket_min:02d}"] = value
    return sorted(buckets.items())
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_grading.py -v`
Expected: PASS — 15 passed

- [ ] **Step 5: 커밋**

```bash
git add collector/grading.py tests/test_grading.py
git commit -m "feat: 등급·추세·다운샘플 규칙. 미미한 변화는 방향 미표시"
```

---

## Task 6: 수집 진입점 (`collector/collect.py`)

**Files:**
- Create: `collector/collect.py`

- [ ] **Step 1: 구현**

이 모듈은 네트워크와 시계만 다루는 얇은 조립층이라 단위 테스트 대신 다음 단계의 수동 실행으로 검증한다.

`collector/collect.py`:
```python
"""수집 진입점.

GitHub Actions의 schedule은 5분 미만 간격을 지원하지 않고 지연도 잦다.
그래서 한 번 실행되면 지정한 시간 동안 내부 루프를 돌며 수집한다.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collector.api import ApiError, fetch, representative_ts
from collector.store import append_snapshot, run_file

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=int, default=35, help="수집 지속 시간(분)")
    parser.add_argument("--interval", type=int, default=120, help="수집 간격(초)")
    parser.add_argument("--raw-dir", default=str(ROOT / "raw"))
    args = parser.parse_args()

    service_key = os.environ.get("KAC_SERVICE_KEY", "").strip()
    if not service_key:
        print("KAC_SERVICE_KEY 환경변수가 없습니다.", file=sys.stderr)
        return 1

    run_id = datetime.now(KST).strftime("%H%M")
    deadline = time.monotonic() + args.minutes * 60
    written = skipped = failed = 0

    while time.monotonic() < deadline:
        try:
            readings = fetch(service_key)
            path = run_file(Path(args.raw_dir), representative_ts(readings), run_id)
            if append_snapshot(path, readings):
                written += 1
            else:
                skipped += 1
        except ApiError as exc:
            failed += 1
            print(f"수집 실패: {exc}", file=sys.stderr)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(args.interval, remaining))

    print(f"수집 완료 — 신규 {written}건, 중복 {skipped}건, 실패 {failed}건")
    # 한 건도 못 받았으면 실패로 끝내 워크플로가 빨간불이 되게 한다
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 짧게 실제 실행해 확인**

Run (PowerShell, `probe\.env`의 키를 환경변수로 옮겨 실행):
```powershell
$env:KAC_SERVICE_KEY = (Get-Content probe\.env | Select-String '^KAC_SERVICE_KEY=').ToString().Split('=')[1]
python -m collector.collect --minutes 3 --interval 60
```
Expected: `수집 완료 — 신규 3건, 중복 0건, 실패 0건` 근처의 출력 (원천이 60초 주기라 3분이면 약 3건).

- [ ] **Step 3: 저장 결과 확인**

Run: `Get-ChildItem -Recurse raw`
Expected: `raw/<오늘날짜>/<HHMM>.jsonl` 파일 1개, 줄 수는 신규 건수와 일치.

- [ ] **Step 4: 커밋 (생성된 raw 데이터는 제외)**

```bash
git add collector/collect.py
git commit -m "feat: 수집 진입점. 내부 루프로 Actions cron 5분 하한 회피"
```

---

## Task 7: 수집 워크플로 (`.github/workflows/collect.yml`)

**Files:**
- Create: `.github/workflows/collect.yml`

- [ ] **Step 1: 워크플로 작성**

`.github/workflows/collect.yml`:
```yaml
name: collect

on:
  schedule:
    # 30분마다 트리거하고 각 실행은 35분간 수집한다. 의도적으로 겹쳐서
    # 스케줄 지연이 데이터 공백으로 이어지지 않게 한다.
    - cron: '0,30 * * * *'
  workflow_dispatch:

concurrency:
  group: collect
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  collect:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Collect
        env:
          KAC_SERVICE_KEY: ${{ secrets.KAC_SERVICE_KEY }}
        run: python -m collector.collect --minutes 35 --interval 120

      - name: Commit and push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add raw
          if git diff --staged --quiet; then
            echo "변경 없음"
            exit 0
          fi
          git commit -m "data: collect $(TZ=Asia/Seoul date +%Y-%m-%dT%H:%M)"
          git pull --rebase --autostash origin main
          git push
```

- [ ] **Step 2: 커밋 및 푸시**

```bash
git add .github/workflows/collect.yml
git commit -m "ci: 수집 워크플로. 30분 트리거 + 35분 실행으로 겹침 수집"
git push
```

- [ ] **Step 3: Secret 등록 확인**

Run: `gh secret list`
Expected: `KAC_SERVICE_KEY` 가 목록에 있음. 없으면 `gh secret set KAC_SERVICE_KEY` 실행.

- [ ] **Step 4: 수동 실행으로 검증**

Run: `gh workflow run collect.yml`
5분 뒤: `gh run list --workflow=collect.yml --limit 1`
Expected: 상태가 `in_progress`. 35분 뒤 `completed / success`.

- [ ] **Step 5: 데이터가 올라왔는지 확인**

Run: `git pull; Get-ChildItem -Recurse raw`
Expected: 오늘 날짜 폴더에 `.jsonl` 파일이 있고, 약 17건(35분 ÷ 2분)의 스냅샷이 들어 있다.

---

## Task 8: 집계와 내보내기 (`collector/aggregate.py`)

**Files:**
- Create: `collector/aggregate.py`
- Test: `tests/test_aggregate.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_aggregate.py`:
```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_aggregate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'collector.aggregate'`

- [ ] **Step 3: 구현**

`collector/aggregate.py`:
```python
"""raw 스냅샷을 앱용 경량 JSON으로 집계한다.

수집은 촘촘하게(2분) 하되 앱에 내보낼 때는 5분 격자로 내리고 3개 공항의
여객 주차장만 남긴다. 휴대폰이 받는 용량을 한 자릿수 KB로 유지하기 위해서다.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collector.access import load_access
from collector.grading import compute_trend, downsample, grade
from collector.store import load_day

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
INTERVAL_MIN = 5
TREND_SPAN_MIN = 60


def _series_for(snapshots: dict, airport_kor: str, lot: str) -> list[tuple[str, int]]:
    """(HH:MM, 주차대수) 시계열. 원천 타임스탬프 순으로 정렬한다."""
    points = []
    for src_ts in sorted(snapshots):
        for reading in snapshots[src_ts]:
            if reading.airport_kor == airport_kor and reading.lot == lot:
                points.append((src_ts.split(" ")[1][:5], reading.stay))
    return points


def build_latest(raw_dir: Path, day: str, access_path: Path) -> dict:
    access = load_access(access_path)
    snapshots = load_day(raw_dir, day)
    if not snapshots:
        return {"generated_at": datetime.now(KST).isoformat(timespec="seconds"),
                "source_ts": None, "airports": {}}

    newest = max(snapshots)
    # 응답에 온 것이 아니라 '있어야 할' 주차장을 기준으로 순회한다.
    # 수신된 것만 내보내면 API가 한 곳을 빠뜨렸을 때 앱에서 조용히 사라져
    # 사용자가 그 주차장의 존재 자체를 모르게 된다 (명세 §7).
    received = {(r.airport_kor, r.lot): r for r in snapshots[newest]}
    airports: dict[str, dict] = {}

    for meta in access.passenger_lots():
        code = meta["airport"]
        airport_kor = access.airports[code]["name_kor"]
        reading = received.get((airport_kor, meta["name"]))

        if reading is None or reading.total <= 0:
            total = occupied = free = None
            lot_grade = "정보 없음"
            trend = None
        else:
            total, occupied = reading.total, reading.stay
            free = total - occupied
            lot_grade = grade(free, total)
            # 만차는 카운터가 고정되어 추세를 신뢰할 수 없다
            trend = None
            if lot_grade != "만차":
                series = _series_for(snapshots, airport_kor, meta["name"])
                window = [value for _, value in series][-(TREND_SPAN_MIN // 2) - 1:]
                trend = compute_trend(window, total, TREND_SPAN_MIN)

        airports.setdefault(code, {
            "name": airport_kor,
            "shuttle": access.shuttle_for(code),
            "lots": [],
        })["lots"].append({
            "name": meta["name"],
            "terminal": meta["terminal"],
            "total": total,
            "occupied": occupied,
            "free": free,
            "grade": lot_grade,
            "access": {
                "walk_min": meta.get("walk_min"),
                "requires_shuttle": bool(meta.get("requires_shuttle")),
                "confidence": meta["confidence"],
            },
            "trend": trend,
        })

    return {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source_ts": newest,
        "airports": airports,
    }


def build_today(raw_dir: Path, day: str, code: str, access_path: Path) -> dict:
    access = load_access(access_path)
    snapshots = load_day(raw_dir, day)
    airport_kor = access.airports[code]["name_kor"]

    lots: dict[str, dict] = {}
    all_times: set[str] = set()
    for meta in access.passenger_lots():
        if meta["airport"] != code:
            continue
        points = downsample(_series_for(snapshots, airport_kor, meta["name"]),
                            INTERVAL_MIN)
        if not points:
            continue
        total = next(
            (r.total for ts in sorted(snapshots) for r in snapshots[ts]
             if r.airport_kor == airport_kor and r.lot == meta["name"]), 0)
        lots[meta["name"]] = {"total": total, "_points": dict(points)}
        all_times.update(stamp for stamp, _ in points)

    times = sorted(all_times)
    for lot in lots.values():
        lot["occupied"] = [lot["_points"].get(stamp) for stamp in times]
        del lot["_points"]

    return {"date": day, "interval_min": INTERVAL_MIN, "times": times, "lots": lots}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", default=str(ROOT / "raw"))
    parser.add_argument("--out-dir", default=str(ROOT / "public" / "data"))
    parser.add_argument("--access", default=str(ROOT / "data" / "lot_access.json"))
    parser.add_argument("--day", default=datetime.now(KST).strftime("%Y-%m-%d"))
    args = parser.parse_args()

    raw_dir, out_dir = Path(args.raw_dir), Path(args.out_dir)
    access_path = Path(args.access)
    out_dir.mkdir(parents=True, exist_ok=True)

    latest = build_latest(raw_dir, args.day, access_path)
    (out_dir / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=1), encoding="utf-8")

    for code in load_access(access_path).airports:
        today = build_today(raw_dir, args.day, code, access_path)
        (out_dir / f"today-{code}.json").write_text(
            json.dumps(today, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")

    print(f"집계 완료 — {args.day}, 공항 {len(latest['airports'])}곳")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_aggregate.py -v`
Expected: PASS — 9 passed

- [ ] **Step 5: 실제 데이터로 실행**

Run: `python -m collector.aggregate`
Expected: `집계 완료 — <오늘>, 공항 3곳`, 그리고 `public/data/`에 4개 JSON 생성.

- [ ] **Step 6: 전체 테스트 통과 확인 후 커밋**

Run: `python -m pytest`
Expected: 모두 통과

```bash
git add collector/aggregate.py tests/test_aggregate.py
git commit -m "feat: 집계·내보내기. 만차는 추세 제외, 5분 격자로 다운샘플"
```

---

## Task 9: 워크플로에 집계 단계 연결

**Files:**
- Modify: `.github/workflows/collect.yml`

- [ ] **Step 1: 집계 단계 추가**

`.github/workflows/collect.yml`의 `Collect` 단계와 `Commit and push` 단계 사이에 넣는다:

```yaml
      - name: Aggregate
        run: python -m collector.aggregate
```

그리고 `Commit and push` 단계의 `git add raw` 를 다음으로 바꾼다:

```yaml
          git add raw public/data
```

- [ ] **Step 2: 커밋 및 푸시**

```bash
git add .github/workflows/collect.yml
git commit -m "ci: 수집 후 집계 단계 연결"
git push
```

- [ ] **Step 3: 수동 실행으로 확인**

Run: `gh workflow run collect.yml`
35분 뒤: `git pull; Get-Content public/data/latest.json -TotalCount 20`
Expected: `source_ts`와 3개 공항의 주차장 목록이 보인다.

---

## Task 10: 앱 화면 골격과 데이터 로딩

**Files:**
- Create: `public/index.html`
- Create: `public/style.css`
- Create: `public/app.js`

- [ ] **Step 1: HTML 골격 작성**

`public/index.html`:
```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>공항 주차장</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header>
  <nav id="airports" aria-label="공항 선택"></nav>
  <p id="freshness" role="status"></p>
</header>
<main id="lots"></main>
<script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 스타일 작성**

`public/style.css`:
```css
:root { --bg:#fff; --fg:#111; --muted:#666; --line:#e3e3e3; --warn:#c2410c; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#111; --fg:#f2f2f2; --muted:#999; --line:#2c2c2c; --warn:#fb923c; }
}
* { box-sizing: border-box; }
body {
  margin:0; background:var(--bg); color:var(--fg);
  font-family: system-ui, -apple-system, "Malgun Gothic", sans-serif;
  padding: env(safe-area-inset-top) 0 env(safe-area-inset-bottom);
}
header { padding:12px 16px 8px; border-bottom:1px solid var(--line); }
#airports { display:flex; gap:8px; }
#airports button {
  flex:1; padding:10px; font-size:15px; border:1px solid var(--line);
  border-radius:8px; background:transparent; color:var(--fg);
}
#airports button[aria-pressed="true"] { background:var(--fg); color:var(--bg); }
#freshness { margin:8px 0 0; font-size:13px; color:var(--muted); }
#freshness.stale { color:var(--warn); font-weight:600; }

.terminal { margin:16px 16px 4px; font-size:13px; color:var(--muted); }
.lot { padding:14px 16px; border-bottom:1px solid var(--line); }
.lot-head { display:flex; justify-content:space-between; align-items:baseline; }
.lot-name { font-size:16px; }
.grade { font-size:13px; padding:2px 8px; border-radius:99px; border:1px solid var(--line); }
.grade.만차 { background:#dc2626; color:#fff; border-color:#dc2626; }
.grade.혼잡 { background:#f59e0b; color:#111; border-color:#f59e0b; }
.free { font-size:28px; font-weight:700; margin:6px 0 2px; }
.free small { font-size:14px; font-weight:400; color:var(--muted); margin-left:6px; }
.meta { font-size:13px; color:var(--muted); }
.spark { font-family:ui-monospace, monospace; letter-spacing:-1px; }
.empty { padding:32px 16px; color:var(--muted); text-align:center; }
```

- [ ] **Step 3: 데이터 로딩과 신선도 배너 구현**

`public/app.js`:
```javascript
'use strict';

const AIRPORTS = [['GMP', '김포'], ['PUS', '김해'], ['CJU', '제주']];
const STALE_MINUTES = 15;

let latest = null;
let current = localStorage.getItem('airport') || 'GMP';

async function loadJson(path) {
  const res = await fetch(`${path}?t=${Date.now()}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

function minutesSince(sourceTs) {
  // "2026-09-15 10:13:03" (KST) -> 경과 분
  const iso = sourceTs.replace(' ', 'T') + '+09:00';
  return Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
}

function renderFreshness() {
  const el = document.getElementById('freshness');
  if (!latest || !latest.source_ts) {
    el.textContent = '정보를 불러오지 못했습니다';
    el.classList.add('stale');
    return;
  }
  const mins = minutesSince(latest.source_ts);
  el.textContent = mins <= 1 ? '방금 전 정보' : `${mins}분 전 정보`;
  el.classList.toggle('stale', mins >= STALE_MINUTES);
  if (mins >= STALE_MINUTES) {
    el.textContent += ' — 갱신이 멈췄을 수 있습니다';
  }
}

function renderTabs() {
  const nav = document.getElementById('airports');
  nav.innerHTML = '';
  for (const [code, label] of AIRPORTS) {
    const button = document.createElement('button');
    button.textContent = label;
    button.setAttribute('aria-pressed', String(code === current));
    button.addEventListener('click', () => {
      current = code;
      localStorage.setItem('airport', code);
      renderTabs();
      renderLots();
    });
    nav.appendChild(button);
  }
}

async function init() {
  renderTabs();
  try {
    latest = await loadJson('data/latest.json');
  } catch (err) {
    console.error(err);
  }
  renderFreshness();
  renderLots();
  setInterval(init, 120000);
}

init();
```

- [ ] **Step 4: `renderLots` 자리표시자 추가**

Task 11에서 채운다. 지금은 `app.js` 끝에 다음을 추가해 화면이 뜨는지만 확인한다:

```javascript
function renderLots() {
  const main = document.getElementById('lots');
  const airport = latest && latest.airports && latest.airports[current];
  main.innerHTML = airport
    ? `<p class="empty">${airport.lots.length}곳 수신</p>`
    : '<p class="empty">데이터 없음</p>';
}
```

- [ ] **Step 5: 로컬에서 확인**

Run: `python -m http.server 8000 --directory public --bind 127.0.0.1`
브라우저에서 `http://127.0.0.1:8000` 접속.
Expected: 김포/김해/제주 탭이 보이고, "N분 전 정보"와 "N곳 수신"이 표시된다.

- [ ] **Step 6: 커밋**

```bash
git add public/index.html public/style.css public/app.js
git commit -m "feat: 앱 골격. 공항 탭, 신선도 배너, 2분 자동 갱신"
```

---

## Task 11: 주차장 카드 렌더

**Files:**
- Modify: `public/app.js`

- [ ] **Step 1: `renderLots` 자리표시자를 실제 구현으로 교체**

`public/app.js`의 Task 10 Step 4에서 넣은 `renderLots` 전체를 다음으로 바꾼다:

```javascript
const SPARK = '▁▂▃▄▅▆▇█';

function sparkline(values, total) {
  const clean = values.filter((v) => v !== null);
  if (clean.length < 2) return '';
  let lo = Math.min(...clean);
  let hi = Math.max(...clean);
  // 규모 대비 최소 진폭을 둔다. 자기 min/max로 정규화하면 1763면 중 15대
  // 변화가 화면 가득 출렁여서 없는 추세를 만들어낸다.
  const floor = Math.max(2, total * 0.05);
  if (hi - lo < floor) {
    const mid = (lo + hi) / 2;
    lo = mid - floor / 2;
    hi = mid + floor / 2;
  }
  return clean.slice(-24)
    .map((v) => SPARK[Math.round(((v - lo) / (hi - lo)) * (SPARK.length - 1))])
    .join('');
}

function accessLabel(lot, shuttle) {
  if (lot.access.requires_shuttle) {
    if (shuttle && shuttle.headway_min) {
      const [lo, hi] = shuttle.headway_min;
      return lo === hi ? `셔틀 ${lo}분 간격` : `셔틀 ${lo}~${hi}분 간격`;
    }
    return '셔틀 이용';
  }
  if (lot.access.walk_min) {
    const [lo, hi] = lot.access.walk_min;
    return `도보 ${lo}~${hi}분`;
  }
  return '도보권';   // confidence가 unverified면 분 단위를 말하지 않는다
}

const isKnown = (lot) => lot.free !== null && lot.free !== undefined;

function trendLabel(lot) {
  if (!isKnown(lot)) return '정보를 받지 못했습니다';
  if (lot.grade === '만차') return '만차 — 입출차 정보 없음';
  if (!lot.trend) return '추세 집계 중';
  if (!lot.trend.significant) return '→ 큰 변화 없음';
  const arrow = lot.trend.direction === 'up' ? '↗' : '↘';
  const sign = lot.trend.delta > 0 ? '+' : '';
  return `${arrow} ${lot.trend.span_minutes}분 ${sign}${lot.trend.delta}대`;
}

function sortLots(lots) {
  // 접근성이 먼저다. 도보권이 비어 있으면 셔틀 주차장은 볼 이유가 없다.
  // 만차는 선택지가 아니라 뒤로, 정보 없음은 그보다 더 뒤로 보낸다.
  const unknown = (l) => (isKnown(l) ? 0 : 1);
  const full = (l) => (isKnown(l) && l.free <= 0 ? 1 : 0);
  return [...lots].sort((a, b) =>
    unknown(a) - unknown(b)
    || full(a) - full(b)
    || a.access.requires_shuttle - b.access.requires_shuttle
    || (b.free ?? -1) - (a.free ?? -1));
}

function lotCard(lot, shuttle, curve) {
  const card = document.createElement('section');
  card.className = 'lot';
  const known = isKnown(lot);
  const pct = known && lot.total > 0
    ? Math.round((lot.occupied / lot.total) * 100) : null;
  const spark = known && curve ? sparkline(curve.occupied, lot.total) : '';
  card.innerHTML = `
    <div class="lot-head">
      <span class="lot-name"></span>
      <span class="grade"></span>
    </div>
    <p class="free"><span></span><small></small></p>
    <p class="meta"></p>
    <p class="meta"><span class="spark"></span> <span class="trend"></span></p>`;
  card.querySelector('.lot-name').textContent = lot.name;
  const grade = card.querySelector('.grade');
  grade.textContent = lot.grade;
  grade.classList.add(lot.grade);
  card.querySelector('.free span').textContent = known ? `${lot.free}면` : '—';
  card.querySelector('.free small').textContent = known ? `${pct}%` : '';
  card.querySelector('.meta').textContent = accessLabel(lot, shuttle);
  card.querySelector('.spark').textContent = spark;
  card.querySelector('.trend').textContent = trendLabel(lot);
  return card;
}

let todayCache = {};

async function renderLots() {
  const main = document.getElementById('lots');
  main.innerHTML = '';
  const airport = latest && latest.airports && latest.airports[current];
  if (!airport) {
    main.innerHTML = '<p class="empty">데이터가 아직 없습니다</p>';
    return;
  }

  if (!todayCache[current]) {
    try {
      todayCache[current] = await loadJson(`data/today-${current}.json`);
    } catch (err) {
      todayCache[current] = { lots: {} };
    }
  }
  const curves = todayCache[current].lots || {};

  // 청사가 여럿이면 섹션으로 나눈다. 청사가 다르면 셔틀을 타야 하므로
  // 같은 목록에 세우면 도보권과 구분되지 않는다.
  const terminals = [...new Set(airport.lots.map((l) => l.terminal))];
  for (const terminal of terminals) {
    if (terminals.length > 1) {
      const heading = document.createElement('p');
      heading.className = 'terminal';
      const needsShuttle = terminal !== '국내선';
      heading.textContent = needsShuttle && airport.shuttle
        ? `${terminal}청사 — ${airport.shuttle.name}`
        : `${terminal}청사`;
      main.appendChild(heading);
    }
    for (const lot of sortLots(airport.lots.filter((l) => l.terminal === terminal))) {
      main.appendChild(lotCard(lot, airport.shuttle, curves[lot.name]));
    }
  }
}
```

그리고 `init()` 안의 `renderLots();` 앞에 캐시 무효화를 추가한다:

```javascript
  todayCache = {};
```

- [ ] **Step 2: 로컬에서 확인**

Run: `python -m http.server 8000 --directory public --bind 127.0.0.1`
Expected:
- 김포 탭에서 국내선청사·국제선청사 섹션이 분리되어 보인다
- 만차 주차장은 맨 아래에 있고 "만차 — 입출차 정보 없음"이 표시된다
- 셔틀 주차장이 도보권 주차장보다 위로 올라오지 않는다

- [ ] **Step 3: 커밋**

```bash
git add public/app.js
git commit -m "feat: 주차장 카드 렌더. 접근성 우선 정렬, 만차는 추세 숨김"
```

---

## Task 12: Pages 배포 워크플로

**Files:**
- Create: `.github/workflows/pages.yml`

- [ ] **Step 1: 워크플로 작성**

`.github/workflows/pages.yml`:
```yaml
name: pages

on:
  push:
    branches: [main]
    paths:
      - 'public/**'
      - '.github/workflows/pages.yml'
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: public
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: 저장소 Pages 설정을 Actions로 변경**

Run: `gh repo view --web`
브라우저에서 **Settings → Pages → Source**를 **GitHub Actions**로 바꾼다. (`Deploy from a branch`가 아니다.)

- [ ] **Step 3: 커밋 및 푸시**

```bash
git add .github/workflows/pages.yml
git commit -m "ci: public/ 을 GitHub Pages로 배포"
git push
```

- [ ] **Step 4: 배포 확인**

Run: `gh run list --workflow=pages.yml --limit 1`
Expected: `completed / success`

Run: `gh repo view --json homepageUrl -q .homepageUrl`
또는 Settings → Pages에 표시된 URL을 휴대폰에서 연다.
Expected: 공항 탭과 주차장 카드가 보인다.

- [ ] **Step 5: 휴대폰에서 최종 확인**

휴대폰 브라우저로 Pages URL 접속.
Expected:
- 탭 전환이 동작하고 선택이 기억된다
- "N분 전 정보"가 실제 경과 시간과 맞는다
- 카드가 세로로 읽히고 가로 스크롤이 생기지 않는다

---

## 완료 기준

- [ ] `python -m pytest` 전부 통과
- [ ] `python probe\check_join.py` 통과 — 실제 응답의 모든 주차장이 `lot_access.json`과 조인된다. 주차장명이 한 글자라도 바뀌면 접근성 정보가 조용히 사라지므로, 공사가 명칭을 바꿨는지 감지하는 안전장치다
- [ ] `collect.yml`이 30분마다 자동 실행되고 `raw/`에 데이터가 쌓인다
- [ ] `public/data/latest.json`의 `source_ts`가 10분 이내로 유지된다
- [ ] Pages URL이 휴대폰에서 열리고 9개 여객 주차장이 보인다
- [ ] 만차 주차장에 추세가 표시되지 않는다
- [ ] 화물 주차장이 목록에 나타나지 않는다
- [ ] 김포에서 셔틀 주차장(국제선)이 도보권 주차장(국내선)보다 위로 올라오지 않는다 — 자동 테스트가 없는 JS 정렬 로직이라 눈으로 확인한다

## 이 계획에서 의도적으로 하지 않는 것

- **주차요금 비교** — 별도 API가 필요하고 판단 영향이 잔여면수·접근성보다 작다
- **도착시각 예측** — 요일·시간대 패턴이 쌓인 뒤의 과제다
- **인천공항** — 별도 기관의 다른 API가 필요하다
- **raw 보관 정리(90일)** — 데이터가 쌓인 뒤에 추가한다. 지금 넣으면 검증할 대상이 없다
- **`history/` 5분 영구 보관** — 2단계 착수 시점에 `raw/`에서 생성한다
