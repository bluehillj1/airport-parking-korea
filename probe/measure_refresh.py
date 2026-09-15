"""KAC 전국공항 실시간 주차정보 API 갱신주기 측정 프로브.

앱을 구현하기 전에 "원천 데이터가 실제로 몇 분마다 바뀌는가"를 실측하기 위한
일회성 도구다. 가이드 문서의 '데이터 갱신주기' 항목이 N/A로 비어 있어서,
수집 주기를 정하려면 직접 재는 수밖에 없다.

응답의 parkingGettime(원천이 스스로 찍은 시각)이 바뀌는 간격을 측정한다.
우리가 몇 초마다 호출했는지가 아니라 원천이 몇 초마다 갱신되는지가 상한이다.

표준 라이브러리만 사용한다 (pip 설치 불필요).

사용법:
    python probe/measure_refresh.py --once      # 키 검증 + 25개 주차장 전체 목록 덤프
    python probe/measure_refresh.py             # 20초 간격 40분 측정
    python probe/measure_refresh.py --interval 30 --minutes 60
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ENDPOINT = "https://apis.data.go.kr/B551178/parking-realtime-status/info"
PROBE_DIR = Path(__file__).resolve().parent
LOG_PATH = PROBE_DIR / "refresh_log.jsonl"


def load_service_key() -> str:
    """환경변수 또는 probe/.env에서 서비스키를 읽는다.

    공공데이터포털은 '인코딩 키'와 '디코딩 키' 두 벌을 준다. 디코딩 키에는
    '+' '/' '=' 같은 문자가 들어 있어 그대로 쿼리에 붙이면 깨지므로,
    키에 '%'가 없으면 인코딩해서 쓴다.
    """
    key = os.environ.get("KAC_SERVICE_KEY", "").strip()
    if not key:
        env_file = PROBE_DIR / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                if name.strip() == "KAC_SERVICE_KEY":
                    key = value.strip().strip("'\"")
                    break
    if not key:
        sys.exit(
            "서비스키가 없습니다.\n"
            f"  {PROBE_DIR / '.env'} 파일에 KAC_SERVICE_KEY=발급받은키 를 넣거나\n"
            "  환경변수 KAC_SERVICE_KEY 를 설정하세요."
        )
    return key if "%" in key else urllib.parse.quote(key, safe="")


def fetch(service_key: str, timeout: float = 15.0) -> dict:
    """API를 1회 호출하고 결과를 정규화해서 돌려준다.

    serviceKey는 이미 인코딩된 상태라 urlencode에 맡기지 않고 직접 붙인다.
    """
    params = urllib.parse.urlencode(
        {"pageNo": 1, "numOfRows": 100, "type": "json"}
    )
    url = f"{ENDPOINT}?serviceKey={service_key}&{params}"

    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.code}", "latency_ms": None}
    except Exception as exc:  # 네트워크 단절 등 — 측정은 계속되어야 한다
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "latency_ms": None}
    latency_ms = round((time.monotonic() - started) * 1000)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # 키 오류 시 XML로 떨어지는 경우가 있다
        return {"ok": False, "error": f"non-JSON (status {status}): {raw[:200]}",
                "latency_ms": latency_ms}

    # 인증 실패는 OpenAPI_ServiceResponse 봉투로 온다
    if "OpenAPI_ServiceResponse" in payload:
        hdr = payload["OpenAPI_ServiceResponse"].get("cmmMsgHeader", {})
        return {"ok": False, "error": hdr.get("errMsg", "unknown"),
                "latency_ms": latency_ms}

    body = payload.get("response", {}).get("body", {}) or {}
    header = payload.get("response", {}).get("header", {}) or {}
    items = (body.get("items") or {})
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):  # 1건일 때 dict로 오는 경우 방어
        items = [items]

    rows = [
        {
            "airport": it.get("aprKor"),
            "lot": it.get("parkingAirportCodeName"),
            "total": _as_int(it.get("parkingFullSpace")),
            "stay": _as_int(it.get("parkingIstay")),
            "in": _as_int(it.get("parkingIincnt")),
            "out": _as_int(it.get("parkingIoutcnt")),
            "src_ts": f"{it.get('parkingGetdate')} {it.get('parkingGettime')}",
        }
        for it in items
    ]
    return {
        "ok": header.get("resultCode") == "00",
        "error": None if header.get("resultCode") == "00" else header.get("resultMsg"),
        "latency_ms": latency_ms,
        "total_count": body.get("totalCount"),
        "rows": rows,
        "src_ts": _src_ts(rows),
        "fingerprint": _fingerprint(rows),
    }


def _src_ts(rows: list[dict]) -> str | None:
    """대표 원천 타임스탬프.

    실측해보니 같은 응답 안에서도 주차장마다 초가 1초씩 다르다(10:13:03 / :04).
    rows[0]을 쓰면 행 순서가 바뀔 때 갱신이 없어도 변화로 오인하므로 최댓값을 쓴다.
    """
    stamps = [r["src_ts"] for r in rows if r.get("src_ts")]
    return max(stamps) if stamps else None


def _fingerprint(rows: list[dict]) -> str:
    """주차 대수 전체의 지문.

    타임스탬프만 바뀌고 값은 그대로인 경우를 구분하기 위해 따로 본다.
    더 자주 호출해서 실익이 있는지는 '값'이 언제 바뀌는지가 말해준다.
    """
    packed = ";".join(
        f"{r['lot']}={r['stay']}" for r in sorted(rows, key=lambda r: r["lot"] or "")
    )
    return hashlib.sha1(packed.encode("utf-8")).hexdigest()[:12]


def _as_int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def dump_once(service_key: str) -> None:
    """키를 검증하고 전국 주차장 전체 목록을 보여준다."""
    result = fetch(service_key)
    if not result["ok"]:
        sys.exit(f"호출 실패: {result['error']}")

    rows = result["rows"]
    print(f"응답 OK  ({result['latency_ms']}ms)  totalCount={result['total_count']}  "
          f"수신 {len(rows)}건")

    src_stamps = {r["src_ts"] for r in rows}
    print(f"원천 타임스탬프: {', '.join(sorted(src_stamps))}"
          f"{'  (전 주차장 동일 = 배치 갱신)' if len(src_stamps) == 1 else '  (주차장마다 다름!)'}")
    print()

    header = f"{'공항':<12} {'주차장':<20} {'전체':>6} {'주차':>6} {'잔여':>6} {'점유율':>7}"
    print(header)
    print("-" * len(header))
    current_airport = None
    for row in sorted(rows, key=lambda r: (r["airport"] or "", r["lot"] or "")):
        total, stay = row["total"], row["stay"]
        free = total - stay if total is not None and stay is not None else None
        pct = f"{stay / total * 100:6.1f}%" if total else "     -"
        airport = row["airport"] if row["airport"] != current_airport else ""
        current_airport = row["airport"]
        print(f"{airport:<12} {row['lot']:<20} {total:>6} {stay:>6} "
              f"{free if free is not None else '-':>6} {pct:>7}")


def measure(service_key: str, interval: int, minutes: int) -> None:
    """원천 타임스탬프가 바뀌는 간격을 측정한다."""
    deadline = time.monotonic() + minutes * 60
    changes: list[tuple[datetime, str]] = []       # 원천 타임스탬프가 바뀐 시점
    value_changes: list[datetime] = []             # 실제 주차 대수가 바뀐 시점
    last_src_ts: str | None = None
    last_fingerprint: str | None = None
    # 항상 만차로 보이는 주차장이 진짜 만차인지 센서 고정인지 판별하기 위한 관측
    stay_seen: dict[str, set[int]] = {}
    polls = failures = 0

    print(f"측정 시작 — {interval}초 간격, {minutes}분간 (Ctrl+C로 조기 종료 후 분석)")
    print(f"로그: {LOG_PATH}\n")

    try:
        with LOG_PATH.open("a", encoding="utf-8") as log:
            while time.monotonic() < deadline:
                now = datetime.now()
                result = fetch(service_key)
                polls += 1

                log.write(json.dumps(
                    {"polled_at": now.isoformat(timespec="seconds"), **result},
                    ensure_ascii=False) + "\n")
                log.flush()

                if not result["ok"]:
                    failures += 1
                    print(f"{now:%H:%M:%S}  실패: {result['error']}")
                else:
                    for row in result["rows"]:
                        if row["stay"] is not None:
                            stay_seen.setdefault(
                                f"{row['airport']} {row['lot']}", set()
                            ).add(row["stay"])

                    src_ts = result["src_ts"]
                    if src_ts != last_src_ts:
                        gap = ""
                        if changes:
                            delta = (now - changes[-1][0]).total_seconds()
                            gap = f"   <- 직전 변화로부터 {delta:.0f}초"
                        changes.append((now, src_ts))
                        print(f"{now:%H:%M:%S}  원천 갱신: {src_ts}{gap}")
                        last_src_ts = src_ts

                    if result["fingerprint"] != last_fingerprint:
                        if last_fingerprint is not None:
                            value_changes.append(now)
                        last_fingerprint = result["fingerprint"]

                sleep_for = interval - (time.monotonic() % interval)
                time.sleep(max(1.0, min(sleep_for, interval)))
    except KeyboardInterrupt:
        print("\n중단됨 — 지금까지의 결과로 분석합니다.\n")

    report(changes, value_changes, stay_seen, polls, failures, interval)


def report(changes, value_changes, stay_seen, polls: int, failures: int,
           interval: int) -> None:
    print("\n" + "=" * 58)
    print(f"호출 {polls}회 (실패 {failures}회), 원천 갱신 {len(changes)}회 관측")
    print(f"주차 대수가 실제로 바뀐 횟수: {len(value_changes)}회")

    # 갱신이 몇 번 일어난 뒤라야 '안 변했다'가 의미를 갖는다.
    # 관측이 짧으면 전 주차장이 고정으로 보이는 게 당연하다.
    frozen = sorted(k for k, v in stay_seen.items() if len(v) == 1)
    if frozen and len(changes) >= 3:
        print(f"\n[값이 한 번도 안 변한 주차장 {len(frozen)}곳]")
        for name in frozen:
            print(f"  {name}  (항상 {next(iter(stay_seen[name]))}대)")
        print("  → 진짜 만차/공차일 수도, 센서가 고정된 것일 수도 있습니다.")
        print("    앱에서 '만차'와 '정보 이상'을 구분할 근거로 씁니다.")

    if len(changes) < 3:
        print("\n갱신 관측이 3회 미만입니다. 더 오래 돌려야 주기를 판단할 수 있습니다.")
        print("갱신주기가 측정시간보다 길 가능성이 있습니다.")
        return

    # 첫 변화는 '측정 시작 시점에 이미 있던 값'이라 주기 계산에서 뺀다
    gaps = [
        (changes[i][0] - changes[i - 1][0]).total_seconds()
        for i in range(1, len(changes))
    ]
    lo, hi = min(gaps), max(gaps)
    avg = sum(gaps) / len(gaps)
    print(f"갱신 간격: 최소 {lo:.0f}초 / 평균 {avg:.0f}초 / 최대 {hi:.0f}초")
    print(f"           ({avg / 60:.1f}분 주기)")

    if hi - lo > interval * 1.5:
        print("\n간격이 들쭉날쭉합니다. 측정 간격을 더 좁혀서 재확인하세요.")

    print("\n[권고]")
    period = avg / 60
    if period >= 4.5:
        print(f"  원천이 약 {period:.0f}분마다 갱신됩니다. 그보다 자주 호출해도 얻는 게 없습니다.")
        print(f"  수집 주기 {max(5, round(period))}분 → GitHub Actions cron으로 충분합니다.")
    elif period >= 1.5:
        print(f"  원천이 약 {period:.1f}분마다 갱신됩니다.")
        print("  GitHub Actions cron(최소 5분)으로는 놓칩니다. 루프형 워크플로 또는")
        print("  Cloudflare Workers cron(최소 1분)을 검토하세요.")
    else:
        print(f"  원천이 {avg:.0f}초마다 갱신되어 상당히 빠릅니다.")
        print("  다만 1단계 추세(방향 + 오늘 곡선)에는 과합니다. 일일 호출 한도와")
        print("  저장 비용을 감안해 1~2분 주기가 현실적인 타협점입니다.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true",
                        help="1회만 호출하고 주차장 전체 목록을 출력")
    parser.add_argument("--interval", type=int, default=20,
                        help="폴링 간격(초), 기본 20")
    parser.add_argument("--minutes", type=int, default=40,
                        help="측정 시간(분), 기본 40")
    args = parser.parse_args()

    service_key = load_service_key()
    if args.once:
        dump_once(service_key)
    else:
        measure(service_key, args.interval, args.minutes)


if __name__ == "__main__":
    main()
