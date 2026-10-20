"""PWA アイコン（`frontend/public/`）を生成する（task #192・ADR-0028。図柄は ADR-0057）。

アイコンの正本はこのスクリプト（配色と図形の座標）であり、出力物は生成結果として
コミットする。標準ライブラリだけで PNG を書き出すため、追加の依存や外部の
ラスタライザは要らない（CI・手元のどちらでも同じ結果になる）。雛形（fastapitemplate）の
`scripts/generate_pwa_icons.py` と同じ作り。図柄と色だけが違う。

    python3 scripts/generate_pwa_icons.py

図柄: ガントチャート。上に日付の目盛り、その下に段々に右へずれる帯 3 本（task #548。前は WBS の木だったが
組織図に見えた）。色は画面の主色の青のまま。Tracker（緑青のストップウォッチ）・Scheduler（紫のカレンダー）と見分ける。

出力:
    favicon.svg                  ブラウザのタブ用（角丸・ベクタ）
    pwa-192x192.png              マニフェストの通常アイコン
    pwa-512x512.png              同（大）
    pwa-maskable-512x512.png     maskable 用（全面塗り・セーフゾーンを取った小さめの図形）
    apple-touch-icon.png         iOS ホーム画面用（OS 側で角丸に切られるため全面塗り）

画面の中の像（ログイン画面・メニューの上。`frontend/src/components/AppMark.tsx`）も
favicon.svg をそのまま読む（ADR-0040）。図柄や色を変えるときはここだけを直して出力し直せばよく、
画面側に同じ絵を書き起こさない。⚠ 色を変えるときは `frontend/src/theme.ts` の ds.primary 系・
`frontend/index.html` の theme-color・manifest の theme_color も揃える。
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import NamedTuple

# 出力先。frontend の静的アセットとして配信される。
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public"

# 配色。画面の主色（`frontend/src/theme.ts` の ds.primary = #0017C1。manifest の theme_color）を
# 挟む形の対角グラデーション。終わりの色は ds.primaryHover。
GRADIENT_START = (0x1F, 0x3A, 0xE0)
GRADIENT_END = (0x00, 0x0E, 0xA5)
MARK_COLOR = (0xFF, 0xFF, 0xFF)

# 角丸の半径（辺の長さに対する比）。
CORNER_RADIUS_RATIO = 0.22


class Box(NamedTuple):
    """図柄の部品: 角丸の矩形（100x100 の座標系）。"""

    x0: float
    y0: float
    x1: float
    y1: float
    radius: float = 0.0
    color: tuple[int, int, int] = MARK_COLOR


class Ring(NamedTuple):
    """図柄の部品: 輪（inner が 0 なら塗りつぶしの円）。"""

    cx: float
    cy: float
    outer: float
    inner: float = 0.0
    color: tuple[int, int, int] = MARK_COLOR


class Bar(NamedTuple):
    """図柄の部品: 両端の丸い棒（(x0, y0) と (x1, y1) を結ぶ線分を half_width だけ太らせたもの）。"""

    x0: float
    y0: float
    x1: float
    y1: float
    half_width: float
    color: tuple[int, int, int] = MARK_COLOR


Shape = Box | Ring | Bar

# ガントチャート。100x100 の座標系で定義し、外接矩形を各アイコンの大きさへ拡大縮小する。
MARK_SHAPES: tuple[Shape, ...] = (
    Box(10.0, 12.0, 90.0, 18.0, 3.0),  # 日付の目盛り
    Bar(18.0, 34.0, 52.0, 34.0, 7.0),  # 帯（1 つ目のタスク）
    Bar(38.0, 56.0, 74.0, 56.0, 7.0),  # 帯（2 つ目）
    Bar(56.0, 78.0, 86.0, 78.0, 7.0),  # 帯（3 つ目）
)

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


def _bounds(shape: Shape) -> tuple[float, float, float, float]:
    """部品の外接矩形 (x0, y0, x1, y1)。"""
    if isinstance(shape, Ring):
        return (shape.cx - shape.outer, shape.cy - shape.outer, shape.cx + shape.outer, shape.cy + shape.outer)
    if isinstance(shape, Bar):
        width = shape.half_width
        return (
            min(shape.x0, shape.x1) - width,
            min(shape.y0, shape.y1) - width,
            max(shape.x0, shape.x1) + width,
            max(shape.y0, shape.y1) + width,
        )
    return (shape.x0, shape.y0, shape.x1, shape.y1)


def _mark_bounds() -> tuple[float, float, float, float]:
    """図柄全体の外接矩形。"""
    corners = [_bounds(shape) for shape in MARK_SHAPES]
    return (
        min(corner[0] for corner in corners),
        min(corner[1] for corner in corners),
        max(corner[2] for corner in corners),
        max(corner[3] for corner in corners),
    )


def _scaled_mark(size: int, width_ratio: float) -> tuple[Shape, ...]:
    """図柄の部品を、一辺 *size* のアイコン中央に置いた座標へ変換する（長い辺を width_ratio に合わせる）。"""
    bound_x0, bound_y0, bound_x1, bound_y1 = _mark_bounds()
    scale = size * width_ratio / max(bound_x1 - bound_x0, bound_y1 - bound_y0)
    offset_x = (size - (bound_x1 - bound_x0) * scale) / 2 - bound_x0 * scale
    offset_y = (size - (bound_y1 - bound_y0) * scale) / 2 - bound_y0 * scale

    def point(x: float, y: float) -> tuple[float, float]:
        return (x * scale + offset_x, y * scale + offset_y)

    scaled: list[Shape] = []
    for shape in MARK_SHAPES:
        if isinstance(shape, Ring):
            scaled.append(Ring(*point(shape.cx, shape.cy), shape.outer * scale, shape.inner * scale, shape.color))
        elif isinstance(shape, Bar):
            scaled.append(
                Bar(*point(shape.x0, shape.y0), *point(shape.x1, shape.y1), shape.half_width * scale, shape.color)
            )
        else:
            scaled.append(Box(*point(shape.x0, shape.y0), *point(shape.x1, shape.y1), shape.radius * scale, shape.color))
    return tuple(scaled)


def _inside_box(box: Box, x: float, y: float) -> bool:
    """点 (*x*, *y*) が角丸の矩形 *box* の内側にあるか。"""
    if not (box.x0 <= x <= box.x1 and box.y0 <= y <= box.y1):
        return False
    if box.radius <= 0:
        return True
    near_x = min(max(x, box.x0 + box.radius), box.x1 - box.radius)
    near_y = min(max(y, box.y0 + box.radius), box.y1 - box.radius)
    return (x - near_x) ** 2 + (y - near_y) ** 2 <= box.radius**2


def _inside(shape: Shape, x: float, y: float) -> bool:
    """点 (*x*, *y*) が部品 *shape* の内側にあるか。"""
    if isinstance(shape, Ring):
        distance = (x - shape.cx) ** 2 + (y - shape.cy) ** 2
        return shape.inner**2 <= distance <= shape.outer**2
    if isinstance(shape, Bar):
        dx, dy = shape.x1 - shape.x0, shape.y1 - shape.y0
        length = dx * dx + dy * dy
        ratio = 0.0 if length == 0 else min(max(((x - shape.x0) * dx + (y - shape.y0) * dy) / length, 0.0), 1.0)
        near_x, near_y = shape.x0 + dx * ratio, shape.y0 + dy * ratio
        return (x - near_x) ** 2 + (y - near_y) ** 2 <= shape.half_width**2
    return _inside_box(shape, x, y)


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


def _sample(spec: IconSpec, mark: tuple[Shape, ...], x: float, y: float) -> tuple[int, int, int, int]:
    """1 走査点の色。背景の外側は透明、図柄の内側は部品の色（後に並べた部品が上）。"""
    if spec.rounded and not _inside_rounded_square(spec.size, spec.size * CORNER_RADIUS_RATIO, x, y):
        return (0, 0, 0, 0)
    for shape in reversed(mark):
        if _inside(shape, x, y):
            return (*shape.color, 255)
    return (*_background_color(spec.size, x, y), 255)


# 1 ピクセル内の走査点の位置（中心をずらした格子）。
_SAMPLE_OFFSETS = tuple((index + 0.5) / SAMPLES_PER_AXIS for index in range(SAMPLES_PER_AXIS))


def _pixel(spec: IconSpec, mark: tuple[Shape, ...], column: int, row: int) -> bytes:
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


def _pixel_row(spec: IconSpec, mark: tuple[Shape, ...], row: int) -> bytearray:
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


def _svg_element(shape: Shape) -> str:
    """部品 1 つを SVG の要素にする。"""
    fill = _hex_color(shape.color)
    if isinstance(shape, Ring):
        if shape.inner <= 0:
            return f'  <circle cx="{shape.cx:.1f}" cy="{shape.cy:.1f}" r="{shape.outer:.1f}" fill="{fill}"/>'
        middle = (shape.outer + shape.inner) / 2
        return (
            f'  <circle cx="{shape.cx:.1f}" cy="{shape.cy:.1f}" r="{middle:.1f}" fill="none"'
            f' stroke="{fill}" stroke-width="{shape.outer - shape.inner:.1f}"/>'
        )
    if isinstance(shape, Bar):
        return (
            f'  <line x1="{shape.x0:.1f}" y1="{shape.y0:.1f}" x2="{shape.x1:.1f}" y2="{shape.y1:.1f}"'
            f' stroke="{fill}" stroke-width="{shape.half_width * 2:.1f}" stroke-linecap="round"/>'
        )
    return (
        f'  <rect x="{shape.x0:.1f}" y="{shape.y0:.1f}" width="{shape.x1 - shape.x0:.1f}"'
        f' height="{shape.y1 - shape.y0:.1f}" rx="{shape.radius:.1f}" fill="{fill}"/>'
    )


def _write_favicon_svg() -> None:
    """タブ用の favicon.svg。PNG と同じ配色・同じ図形・同じ配置をベクタで書き出す。"""
    canvas = 512
    width_ratio = ICONS[0].mark_width_ratio  # 通常アイコンと同じ大きさに合わせる
    elements = "\n".join(_svg_element(shape) for shape in _scaled_mark(canvas, width_ratio))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas} {canvas}">
  <!-- scripts/generate_pwa_icons.py が生成する。手で編集しない。 -->
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{_hex_color(GRADIENT_START)}"/>
      <stop offset="1" stop-color="{_hex_color(GRADIENT_END)}"/>
    </linearGradient>
  </defs>
  <rect width="{canvas}" height="{canvas}" rx="{round(canvas * CORNER_RADIUS_RATIO)}" fill="url(#bg)"/>
{elements}
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
