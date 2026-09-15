"""refresh_log.jsonl을 분석해 원천 갱신주기를 계산한다.

measure_refresh.py가 끝나기를 기다리지 않고 중간 경과를 볼 수 있다.
로그에는 여러 번의 측정 세션이 이어붙어 있으므로, 폴링 간격보다 훨씬 큰
시간 공백을 경계로 세션을 나누고 마지막 세션만 본다.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

LOG = Path(__file__).resolve().parent / "refresh_log.jsonl"


def load_sessions(gap_threshold: float = 180.0) -> list[list[dict]]:
    if not LOG.exists():
        sys.exit("refresh_log.jsonl이 없습니다.")

    records = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        rec["_at"] = datetime.fromisoformat(rec["polled_at"])
        records.append(rec)

    sessions: list[list[dict]] = []
    for rec in records:
        if sessions and (rec["_at"] - sessions[-1][-1]["_at"]).total_seconds() <= gap_threshold:
            sessions[-1].append(rec)
        else:
            sessions.append([rec])
    return sessions


def transitions(session: list[dict], key: str) -> list[tuple[datetime, str]]:
    """key 값이 바뀐 시점들. 첫 관측은 '이미 그 값이던' 상태라 주기 계산에서 제외된다."""
    out: list[tuple[datetime, str]] = []
    previous = None
    for rec in session:
        if not rec.get("ok"):
            continue
        value = rec.get(key)
        if value != previous:
            out.append((rec["_at"], value))
            previous = value
    return out


def describe(label: str, points: list[tuple[datetime, str]]) -> None:
    if len(points) < 2:
        print(f"{label}: 변화 {len(points)}회 — 주기 계산 불가")
        return
    gaps = [
        (points[i][0] - points[i - 1][0]).total_seconds()
        for i in range(1, len(points))
    ]
    avg = sum(gaps) / len(gaps)
    print(f"{label}: 변화 {len(points)}회, "
          f"간격 최소 {min(gaps):.0f}s / 평균 {avg:.0f}s / 최대 {max(gaps):.0f}s")
    print(f"    관측된 간격: {', '.join(f'{g:.0f}' for g in gaps)}")


def main() -> None:
    sessions = load_sessions()
    session = sessions[-1]
    ok = [r for r in session if r.get("ok")]
    span = (session[-1]["_at"] - session[0]["_at"]).total_seconds()

    print(f"세션 {len(sessions)}개 중 마지막 세션 분석")
    print(f"  {session[0]['_at']:%H:%M:%S} ~ {session[-1]['_at']:%H:%M:%S} "
          f"({span / 60:.1f}분), 호출 {len(session)}회 (실패 {len(session) - len(ok)}회)\n")

    src = transitions(session, "src_ts")
    val = transitions(session, "fingerprint")
    describe("원천 타임스탬프", src)
    print()
    describe("실제 주차대수", val)

    if len(src) >= 3:
        gaps = [(src[i][0] - src[i - 1][0]).total_seconds() for i in range(1, len(src))]
        avg = sum(gaps) / len(gaps)
        print(f"\n[해석] 원천은 약 {avg:.0f}초({avg / 60:.1f}분)마다 갱신됩니다.")
        print(f"       이보다 자주 호출해도 같은 값만 더 받습니다.")


if __name__ == "__main__":
    main()
