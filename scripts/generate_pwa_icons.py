"""Generate the PWA icons (`frontend/public/`) (task #192, ADR-0028; artwork in ADR-0057).

This script (colors and shape coordinates) is the source of truth for the icons, and the outputs are committed
as generated results. PNGs are written with the standard library only, so no extra dependencies or external
rasterizer are needed (same result in CI and locally). Built the same way as the template's (fastapitemplate)
`scripts/generate_pwa_icons.py`. Only the artwork and colors differ.

    python3 scripts/generate_pwa_icons.py

Artwork: a Gantt chart. A date ruler on top, with 3 bars below stepping to the right (task #548; it used to be a WBS tree but
looked like an org chart). The color stays the screen's primary blue. Distinguished from Tracker (teal stopwatch) and Scheduler (purple calendar).

Outputs:
    favicon.svg                  for browser tabs (rounded corners, vector)
    pwa-192x192.png              regular manifest icon
    pwa-512x512.png              same (large)
    pwa-maskable-512x512.png     maskable (fully filled, smaller shape within the safe zone)
    apple-touch-icon.png         iOS home screen (fully filled, since the OS rounds the corners)

The in-screen mark (sign-in screen, top of the menu; `frontend/src/components/AppMark.tsx`) also
reads favicon.svg as is (ADR-0040). To change the artwork or colors, fix only this file and regenerate;
do not redraw the same picture on the screen side. ⚠ When changing colors, also align the ds.primary family in `frontend/src/theme.ts`,
theme-color in `frontend/index.html`, and the manifest's theme_color.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import NamedTuple

# Output directory. Served as static assets of the frontend.
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public"

# Colors: a diagonal gradient around the screen's primary color (ds.primary = #0017C1 in `frontend/src/theme.ts`;
# the manifest's theme_color). The end color is ds.primaryHover.
GRADIENT_START = (0x1F, 0x3A, 0xE0)
GRADIENT_END = (0x00, 0x0E, 0xA5)
MARK_COLOR = (0xFF, 0xFF, 0xFF)

# Corner radius (as a ratio of the side length).
CORNER_RADIUS_RATIO = 0.22


class Box(NamedTuple):
    """Artwork part: a rounded rectangle (100x100 coordinate system)."""

    x0: float
    y0: float
    x1: float
    y1: float
    radius: float = 0.0
    color: tuple[int, int, int] = MARK_COLOR


class Ring(NamedTuple):
    """Artwork part: a ring (a filled circle when inner is 0)."""

    cx: float
    cy: float
    outer: float
    inner: float = 0.0
    color: tuple[int, int, int] = MARK_COLOR


class Bar(NamedTuple):
    """Artwork part: a bar with round ends (the segment from (x0, y0) to (x1, y1) thickened by half_width)."""

    x0: float
    y0: float
    x1: float
    y1: float
    half_width: float
    color: tuple[int, int, int] = MARK_COLOR


Shape = Box | Ring | Bar

# Gantt chart. Defined in a 100x100 coordinate system; the bounding box is scaled to each icon size.
MARK_SHAPES: tuple[Shape, ...] = (
    Box(10.0, 12.0, 90.0, 18.0, 3.0),  # date ruler
    Bar(18.0, 34.0, 52.0, 34.0, 7.0),  # bar (first task)
    Bar(38.0, 56.0, 74.0, 56.0, 7.0),  # bar (second)
    Bar(56.0, 78.0, 86.0, 78.0, 7.0),  # bar (third)
)

# Samples per pixel (supersampling for anti-aliasing).
SAMPLES_PER_AXIS = 4


class IconSpec(NamedTuple):
    """Spec of one PNG to generate."""

    filename: str
    size: int
    # Share of the icon side taken by the artwork's long side (width)
    mark_width_ratio: float
    rounded: bool


ICONS = (
    # Regular icon: rounded with transparent corners.
    IconSpec("pwa-192x192.png", 192, 0.72, rounded=True),
    IconSpec("pwa-512x512.png", 512, 0.72, rounded=True),
    # maskable: the OS crops it to a circle etc. Fit the shape in the central safe circle (80% diameter) and fill the background fully.
    IconSpec("pwa-maskable-512x512.png", 512, 0.52, rounded=False),
    # iOS rounds the corners itself, so no transparent corners.
    IconSpec("apple-touch-icon.png", 180, 0.66, rounded=False),
)


def _bounds(shape: Shape) -> tuple[float, float, float, float]:
    """Bounding box (x0, y0, x1, y1) of a part."""
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
    """Bounding box of the whole artwork."""
    corners = [_bounds(shape) for shape in MARK_SHAPES]
    return (
        min(corner[0] for corner in corners),
        min(corner[1] for corner in corners),
        max(corner[2] for corner in corners),
        max(corner[3] for corner in corners),
    )


def _scaled_mark(size: int, width_ratio: float) -> tuple[Shape, ...]:
    """Transform artwork parts to coordinates centered in an icon of side *size* (long side scaled to width_ratio)."""
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
    """Whether point (*x*, *y*) is inside the rounded rectangle *box*."""
    if not (box.x0 <= x <= box.x1 and box.y0 <= y <= box.y1):
        return False
    if box.radius <= 0:
        return True
    near_x = min(max(x, box.x0 + box.radius), box.x1 - box.radius)
    near_y = min(max(y, box.y0 + box.radius), box.y1 - box.radius)
    return (x - near_x) ** 2 + (y - near_y) ** 2 <= box.radius**2


def _inside(shape: Shape, x: float, y: float) -> bool:
    """Whether point (*x*, *y*) is inside part *shape*."""
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
    """Whether point (*x*, *y*) is inside a rounded square of side *size* and corner radius *radius*."""
    return _inside_box(Box(0.0, 0.0, float(size), float(size), radius), x, y)


def _mix(start: int, end: int, ratio: float) -> int:
    return round(start + (end - start) * ratio)


def _background_color(size: int, x: float, y: float) -> tuple[int, int, int]:
    """Diagonal gradient color: GRADIENT_START at top-left, GRADIENT_END at bottom-right."""
    ratio = (x + y) / (size * 2)
    return (
        _mix(GRADIENT_START[0], GRADIENT_END[0], ratio),
        _mix(GRADIENT_START[1], GRADIENT_END[1], ratio),
        _mix(GRADIENT_START[2], GRADIENT_END[2], ratio),
    )


def _sample(spec: IconSpec, mark: tuple[Shape, ...], x: float, y: float) -> tuple[int, int, int, int]:
    """Color of one sample: transparent outside the background, part color inside the artwork (later parts on top)."""
    if spec.rounded and not _inside_rounded_square(spec.size, spec.size * CORNER_RADIUS_RATIO, x, y):
        return (0, 0, 0, 0)
    for shape in reversed(mark):
        if _inside(shape, x, y):
            return (*shape.color, 255)
    return (*_background_color(spec.size, x, y), 255)


# Sample positions within a pixel (a grid offset from the center).
_SAMPLE_OFFSETS = tuple((index + 0.5) / SAMPLES_PER_AXIS for index in range(SAMPLES_PER_AXIS))


def _pixel(spec: IconSpec, mark: tuple[Shape, ...], column: int, row: int) -> bytes:
    """RGBA of one pixel. Anti-aliased by averaging the samples."""
    red = green = blue = alpha = 0
    for offset_y in _SAMPLE_OFFSETS:
        for offset_x in _SAMPLE_OFFSETS:
            # Sum with premultiplied alpha (so the color of transparent areas does not bleed into edges).
            sample = _sample(spec, mark, column + offset_x, row + offset_y)
            red += sample[0] * sample[3]
            green += sample[1] * sample[3]
            blue += sample[2] * sample[3]
            alpha += sample[3]
    if alpha == 0:
        return bytes(4)
    return bytes((round(red / alpha), round(green / alpha), round(blue / alpha), round(alpha / SAMPLES_PER_AXIS**2)))


def _pixel_row(spec: IconSpec, mark: tuple[Shape, ...], row: int) -> bytearray:
    """RGBA bytes of one row."""
    line = bytearray()
    for column in range(spec.size):
        line += _pixel(spec, mark, column, row)
    return line


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    """A PNG chunk (length + type + data + CRC)."""
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _write_png(path: Path, size: int, rows: list[bytearray]) -> None:
    """Write RGBA row data as an 8 bit/channel PNG."""
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(row) for row in rows)  # filter type of each row is 0 (None)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def _render(spec: IconSpec) -> None:
    """Generate and write one icon."""
    mark = _scaled_mark(spec.size, spec.mark_width_ratio)
    rows = [_pixel_row(spec, mark, row) for row in range(spec.size)]
    _write_png(OUTPUT_DIR / spec.filename, spec.size, rows)
    print(f"[icons] {spec.filename} ({spec.size}x{spec.size})")


def _hex_color(color: tuple[int, int, int]) -> str:
    red, green, blue = color
    return f"#{red:02x}{green:02x}{blue:02x}"


def _svg_element(shape: Shape) -> str:
    """Turn one part into an SVG element."""
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
    """favicon.svg for tabs. Writes the same colors, shapes and layout as the PNGs, as vectors."""
    canvas = 512
    width_ratio = ICONS[0].mark_width_ratio  # match the size of the regular icon
    elements = "\n".join(_svg_element(shape) for shape in _scaled_mark(canvas, width_ratio))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas} {canvas}">
  <!-- Generated by scripts/generate_pwa_icons.py. Do not edit by hand. -->
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
