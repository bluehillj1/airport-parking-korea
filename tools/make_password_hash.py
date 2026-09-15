"""앱 접속 암호의 해시와 세션 비밀키를 만든다.

이 PC에서만 실행하고, 출력된 값을 Vercel 환경변수에 손으로 붙여넣는다.

암호는 인자로 받지 않는다. 명령줄에 쓰면 PowerShell 기록(ConsoleHost_history.txt)
에 영구히 남기 때문이다. 화면에도 찍히지 않는다.

    python tools/make_password_hash.py
"""

from __future__ import annotations

import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.auth import hash_password  # noqa: E402


def main() -> int:
    password = getpass.getpass("앱 접속 암호: ")
    if len(password) < 8:
        print("8자 이상으로 정하세요.", file=sys.stderr)
        return 1
    if password != getpass.getpass("한 번 더: "):
        print("두 입력이 다릅니다.", file=sys.stderr)
        return 1

    # 'NAME=value' 한 줄로 찍으면 통째로 복사해 값 칸에 넣기 쉽다. 그러면 저장된
    # 값이 'APP_PASSWORD_HASH=pbkdf2_...' 가 되어 검증이 실패하고, 화면에는
    # '암호가 틀렸다'고만 나와 원인을 찾기 어렵다. 이름과 값을 떼어 놓는다.
    print("\nVercel → Settings → Environment Variables\n")
    for name, value in (("APP_PASSWORD_HASH", hash_password(password)),
                        ("SESSION_SECRET", secrets.token_urlsafe(32))):
        print(f"  Key   {name}")
        print(f"  Value {value}\n")
    print("Value 칸에는 뒤쪽 값만 넣으세요. 이름은 Key 칸에 따로 들어갑니다.")
    print("(암호 자체는 어디에도 저장되지 않습니다. 잊으면 다시 만드세요.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
