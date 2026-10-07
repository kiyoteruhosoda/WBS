"""PWA アイコン（`frontend/public/`）を生成する（task #192・ADR-0028）。

アイコンの正本はこのスクリプト（配色と図形の座標）であり、出力物は生成結果として
コミットする。標準ライブラリだけで PNG を書き出すため、追加の依存や外部の
ラスタライザは要らない（CI・手元のどちらでも同じ結果になる）。雛形（fastapitemplate）の
`scripts/generate_pwa_icons.py` と同じ作り。図柄だけが違う。

    python3 scripts/generate_pwa_icons.py

図柄: WBS（作業分解図）の木。上に 1 つの箱、線で下の 3 つの箱へ分かれる。

出力:
    favicon.svg                  ブラウザのタブ用（角丸・ベクタ）
    pwa-192x192.png              マニフェストの通常アイコン
    pwa-512x512.png              同（大）
    pwa-maskable-512x512.png     maskable 用（全面塗り・セーフゾーンを取った小さめの図形）
    apple-touch-icon.png         iOS ホーム画面用（OS 側で角丸に切られるため全面塗り）

画面の中の像（ログイン画面・メニューの上。`frontend/src/components/AppMark.tsx`）も
favicon.svg をそのまま読む（ADR-0040）。図柄や色を変えるときはここだけを直して出力し直せばよく、
画面側に同じ絵を書き起こさない。
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import NamedTuple

# 出力先。frontend の静的アセットとして配信される。
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public"

# 配色。画面の主色（`frontend/src/theme.ts` の ds.primary = #0017C1。manifest の theme_color）を
# 挟む形の対角グラデーション。
GRADIENT_START = (0x1F, 0x3A, 0xE0)
GRADIENT_END = (0x00, 0x0E, 0xA5)
MARK_COLOR = (0xFF, 0xFF, 0xFF)

# 角丸の半径（辺の長さに対する比）。
CORNER_RADIUS_RATIO = 0.22


class Box(NamedTuple):
    """図柄の部品 1 つ（100x100 の座標系の矩形と、その角の半径）。"""

    x0: float
    y0: float
    x1: float
    y1: float
    radius: float = 0.0


# WBS の木。100x100 の座標系で定義し、各アイコンの大きさへ拡大縮小する。
MARK_BOXES = (
    Box(33.0, 12.0, 67.0, 34.0, 4.0),  # 上の箱（プロジェクト）
    Box(48.0, 33.0, 52.0, 47.0),  # 上の箱から下ろす線
    Box(18.0, 45.0, 82.0, 49.0),  # 横に渡す線
    Box(18.0, 47.0, 22.0, 63.0),  # 左へ下ろす線
    Box(48.0, 47.0, 52.0, 63.0),  # 中へ下ろす線
    Box(78.0, 47.0, 82.0, 63.0),  # 右へ下ろす線
    Box(6.0, 62.0, 34.0, 84.0, 4.0),  # 下の箱（左）
    Box(36.0, 62.0, 64.0, 84.0, 4.0),  # 下の箱（中）
    Box(66.0, 62.0, 94.0, 84.0, 4.0),  # 下の箱（右）
)
MARK_BOUNDS = (6.0, 12.0, 94.0, 84.0)  # 上の部品の外接矩形 (x0, y0, x1, y1)

# 1 ピクセルあたりの走査点数（アンチエイリアス用のスーパーサンプリング）。
SAMPLES_PER_AXIS = 4


class IconSpec(NamedTuple):
    """生成する PNG 1 枚の仕様。"""

    filename: str
    size: int
    # 図柄の長い辺（幅）がアイコンの一辺に占める割合
    mark_width_ratio: float
    rounded: bool


ICONS = (
    # 通常アイコン: 角を透明にした角丸。
    IconSpec("pwa-192x192.png", 192, 0.72, rounded=True),
    IconSpec("pwa-512x512.png", 512, 0.72, rounded=True),
    # maskable: OS が円などに切り抜く。図形を中央の安全な円（直径 80%）に収め、背景は全面塗りにする。
    IconSpec("pwa-maskable-512x512.png", 512, 0.52, rounded=False),
    # iOS は独自に角丸へ切るため、透明な角を持たせない。
    IconSpec("apple-touch-icon.png", 180, 0.66, rounded=False),
)


def _scaled_mark(size: int, width_ratio: float) -> tuple[Box, ...]:
    """図柄の部品を、一辺 *size* のアイコン中央に置いた座標へ変換する。"""
    bound_x0, bound_y0, bound_x1, bound_y1 = MARK_BOUNDS
    scale = size * width_ratio / (bound_x1 - bound_x0)
    offset_x = (size - (bound_x1 - bound_x0) * scale) / 2 - bound_x0 * scale
    offset_y = (size - (bound_y1 - bound_y0) * scale) / 2 - bound_y0 * scale
    return tuple(
        Box(
            box.x0 * scale + offset_x,
            box.y0 * scale + offset_y,
            box.x1 * scale + offset_x,
            box.y1 * scale + offset_y,
            box.radius * scale,
        )
        for box in MARK_BOXES
    )


def _inside_box(box: Box, x: float, y: float) -> bool:
    """点 (*x*, *y*) が角丸の矩形 *box* の内側にあるか。"""
    if not (box.x0 <= x <= box.x1 and box.y0 <= y <= box.y1):
        return False
    if box.radius <= 0:
        return True
    near_x = min(max(x, box.x0 + box.radius), box.x1 - box.radius)
    near_y = min(max(y, box.y0 + box.radius), box.y1 - box.radius)
    return (x - near_x) ** 2 + (y - near_y) ** 2 <= box.radius**2


def _inside_rounded_square(size: int, radius: float, x: float, y: float) -> bool:
    """点 (*x*, *y*) が一辺 *size*・角半径 *radius* の角丸正方形の内側にあるか。"""
    return _inside_box(Box(0.0, 0.0, float(size), float(size), radius), x, y)


def _mix(start: int, end: int, ratio: float) -> int:
    return round(start + (end - start) * ratio)


def _background_color(size: int, x: float, y: float) -> tuple[int, int, int]:
    """対角グラデーションの色。左上を GRADIENT_START、右下を GRADIENT_END にする。"""
    ratio = (x + y) / (size * 2)
    return (
        _mix(GRADIENT_START[0], GRADIENT_END[0], ratio),
        _mix(GRADIENT_START[1], GRADIENT_END[1], ratio),
        _mix(GRADIENT_START[2], GRADIENT_END[2], ratio),
    )


def _sample(spec: IconSpec, mark: tuple[Box, ...], x: float, y: float) -> tuple[int, int, int, int]:
    """1 走査点の色。背景の外側は透明、図柄の内側は白。"""
    if spec.rounded and not _inside_rounded_square(spec.size, spec.size * CORNER_RADIUS_RATIO, x, y):
        return (0, 0, 0, 0)
    if any(_inside_box(box, x, y) for box in mark):
        return (*MARK_COLOR, 255)
    return (*_background_color(spec.size, x, y), 255)


# 1 ピクセル内の走査点の位置（中心をずらした格子）。
_SAMPLE_OFFSETS = tuple((index + 0.5) / SAMPLES_PER_AXIS for index in range(SAMPLES_PER_AXIS))


def _pixel(spec: IconSpec, mark: tuple[Box, ...], column: int, row: int) -> bytes:
    """1 ピクセルの RGBA。走査点の平均を取ってアンチエイリアスする。"""
    red = green = blue = alpha = 0
    for offset_y in _SAMPLE_OFFSETS:
        for offset_x in _SAMPLE_OFFSETS:
            # アルファを乗算した色で足し合わせる（透明部分の色が縁へ滲まないようにする）。
            sample = _sample(spec, mark, column + offset_x, row + offset_y)
            red += sample[0] * sample[3]
            green += sample[1] * sample[3]
            blue += sample[2] * sample[3]
            alpha += sample[3]
    if alpha == 0:
        return bytes(4)
    return bytes((round(red / alpha), round(green / alpha), round(blue / alpha), round(alpha / SAMPLES_PER_AXIS**2)))


def _pixel_row(spec: IconSpec, mark: tuple[Box, ...], row: int) -> bytearray:
    """1 行分の RGBA バイト列。"""
    line = bytearray()
    for column in range(spec.size):
        line += _pixel(spec, mark, column, row)
    return line


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    """PNG チャンク（長さ + 種別 + 中身 + CRC）。"""
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _write_png(path: Path, size: int, rows: list[bytearray]) -> None:
    """RGBA の行データを 8bit/channel の PNG として書き出す。"""
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(row) for row in rows)  # 各行のフィルタ種別は 0（None）
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def _render(spec: IconSpec) -> None:
    """アイコン 1 枚を生成して書き出す。"""
    mark = _scaled_mark(spec.size, spec.mark_width_ratio)
    rows = [_pixel_row(spec, mark, row) for row in range(spec.size)]
    _write_png(OUTPUT_DIR / spec.filename, spec.size, rows)
    print(f"[icons] {spec.filename} ({spec.size}x{spec.size})")


def _hex_color(color: tuple[int, int, int]) -> str:
    red, green, blue = color
    return f"#{red:02x}{green:02x}{blue:02x}"


def _write_favicon_svg() -> None:
    """タブ用の favicon.svg。PNG と同じ配色・同じ図形・同じ配置をベクタで書き出す。"""
    canvas = 512
    width_ratio = ICONS[0].mark_width_ratio  # 通常アイコンと同じ大きさに合わせる
    rects = "\n".join(
        f'  <rect x="{box.x0:.1f}" y="{box.y0:.1f}" width="{box.x1 - box.x0:.1f}" height="{box.y1 - box.y0:.1f}"'
        f' rx="{box.radius:.1f}" fill="{_hex_color(MARK_COLOR)}"/>'
        for box in _scaled_mark(canvas, width_ratio)
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas} {canvas}">
  <!-- scripts/generate_pwa_icons.py が生成する。手で編集しない。 -->
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{_hex_color(GRADIENT_START)}"/>
      <stop offset="1" stop-color="{_hex_color(GRADIENT_END)}"/>
    </linearGradient>
  </defs>
  <rect width="{canvas}" height="{canvas}" rx="{round(canvas * CORNER_RADIUS_RATIO)}" fill="url(#bg)"/>
{rects}
</svg>
"""
    (OUTPUT_DIR / "favicon.svg").write_text(svg, encoding="utf-8")
    print("[icons] favicon.svg")


def main() -> None:
    for spec in ICONS:
        _render(spec)
    _write_favicon_svg()


if __name__ == "__main__":
    main()
