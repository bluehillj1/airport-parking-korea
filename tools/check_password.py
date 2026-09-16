"""해시와 암호가 실제로 맞는지 이 PC에서 즉시 확인한다.

Vercel에 넣고 재배포해야만 알 수 있으면 한 번 확인하는 데 몇 분이 걸리고,
틀렸을 때 원인이 해시인지 암호인지도 알 수 없다. 여기서 '일치'가 나온 조합만
올리면 그 왕복이 사라진다.

    python tools/check_password.py

암호는 인자로 받지 않는다. 명령줄에 쓰면 PowerShell 기록에 영구히 남는다.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.auth import (  # noqa: E402
    describe_encoded,
    fingerprint,
    verify_password,
)


def main() -> int:
    encoded = input("APP_PASSWORD_HASH 값을 붙여넣으세요: ").strip()
    print(f"  형태: {describe_encoded(encoded)}")
    print(f"  지문: fp={fingerprint(encoded)}   ← 서버 로그의 fp 와 같아야 합니다")
    if "algo_ok=True" not in describe_encoded(encoded):
        print("\n해시 형식이 아닙니다. pbkdf2_sha256$ 로 시작하는 값이어야 합니다.",
              file=sys.stderr)
        return 1

    password = getpass.getpass("암호: ")
    print(f"  입력 길이: {len(password)}자")

    if verify_password(password, encoded):
        print("\n일치합니다. 이 해시를 Vercel에 넣으시면 됩니다.")
        return 0
    print("\n일치하지 않습니다. 같은 실행에서 나온 해시인지, 한/영과 "
          "Caps Lock 상태가 같은지 확인하세요.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
