"""홈 화면 아이콘(PNG)을 만든다.

외부 패키지를 쓰지 않는다. 아이콘 세 장 때문에 이미지 라이브러리를 의존성에
추가하면, 다시는 실행하지 않을 코드를 위해 설치와 취약점 관리를 떠안게 된다.
PNG는 zlib(표준 라이브러리)만으로 충분히 쓸 수 있다.

    python tools/make_icons.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "public"

# 앱의 이름 상자와 같은 파랑. 등급(빨강·주황·초록)과 겹치지 않는 계열이다.
BACKGROUND = (30, 64, 175)
FOREGROUND = (255, 255, 255)

# 안드로이드 적응형 아이콘이 보장하는 영역은 캔버스의 가운데 66/108 뿐이다.
# 즉 중심에서 반지름 0.3056 바깥은 마스크에 잘려나갈 수 있는데, 기본 P는 기둥
# 모서리가 0.3176 까지 나간다. 마스커블용으로는 0.8배로 줄여 여백을 둔다.
#
# 일반 아이콘까지 줄이지는 않는다. iOS와 옛 안드로이드는 자르지 않고 그대로
# 쓰므로, 줄이면 그쪽에서 괜히 작아 보인다.
MASKABLE_SCALE = 0.80

# 이름, 한 변, P 축소율
ICONS = (
    ("icon-192.png", 192, 1.0),
    ("icon-512.png", 512, 1.0),
    ("apple-touch-icon.png", 180, 1.0),
    ("icon-maskable-512.png", 512, MASKABLE_SCALE),
)


def _in_letter_p(x: float, y: float) -> bool:
    """주차장 기호 P. 기둥 사각형과 고리를 합친 모양이다.

    가로로 0.35~0.655 를 차지해 가운데(0.5)에 놓인다.
    """
    if 0.35 <= x <= 0.47 and 0.22 <= y <= 0.78:
        return True
    # 고리의 왼쪽 절반은 기둥에 묻히므로 잘라낸다. 안 자르면 기둥 왼쪽으로
    # 삐져나와 P가 아니라 이상한 글자가 된다.
    if x < 0.41:
        return False
    dx, dy = x - 0.47, y - 0.38
    return 0.085 <= (dx * dx + dy * dy) ** 0.5 <= 0.185


def _pixel(x: float, y: float, scale: float) -> tuple[int, int, int]:
    # 모서리를 둥글리지 않는다. iOS는 제 방식대로 깎아내고 안드로이드도 적응형
    # 아이콘으로 마스킹하므로, 미리 둥글리면 두 번 깎여 모서리가 패인다.
    #
    # P를 줄일 때는 글자를 다시 그리는 대신 좌표를 가운데 기준으로 넓혀 준다.
    # 바탕은 캔버스를 가득 채운 채 글자만 작아진다.
    if scale != 1.0:
        x = 0.5 + (x - 0.5) / scale
        y = 0.5 + (y - 0.5) / scale
    return FOREGROUND if _in_letter_p(x, y) else BACKGROUND


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))


def render(size: int, scale: float = 1.0) -> bytes:
    rows = bytearray()
    for row in range(size):
        rows.append(0)             # 필터 없음
        y = (row + 0.5) / size
        for column in range(size):
            rows.extend(_pixel((column + 0.5) / size, y, scale))

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(bytes(rows), 9))
            + _chunk(b"IEND", b""))


def main() -> int:
    for name, size, scale in ICONS:
        data = render(size, scale)
        (OUT / name).write_bytes(data)
        note = "" if scale == 1.0 else f"  P {scale:.0%}"
        print(f"{name:<24} {size}x{size}  {len(data):,} bytes{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
