"""Golden-image pixel diff harness (§10.2) — WP-9 scaffolding.

Flag > PIXEL_DIFF_THRESHOLD (2 %) for human review. Works without Blender:
stub / synthetic RGBA buffers are enough for CI until demo renders exist.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

# Spec §10.2 — flag > 2 % pixel change
PIXEL_DIFF_THRESHOLD = 0.02

PathLike = Union[str, Path]
Buffer = Sequence[int]  # flattened RGBA bytes 0–255


class GoldenCompareError(Exception):
    """Raised when pixel diff exceeds the approved threshold."""

    def __init__(self, message: str, *, fraction: float, threshold: float):
        super().__init__(message)
        self.fraction = fraction
        self.threshold = threshold


def _read_png_rgba(path: Path) -> Tuple[int, int, bytes]:
    """Minimal PNG reader (8-bit RGBA or RGB). No external deps."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")

    pos = 8
    width = height = None
    bit_depth = color_type = None
    idat = bytearray()

    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        pos += 4
        ctype = data[pos : pos + 4]
        pos += 4
        chunk = data[pos : pos + length]
        pos += length
        pos += 4  # crc

        if ctype == b"IHDR":
            width, height, bit_depth, color_type, *_ = struct.unpack(">IIBBBBB", chunk)
        elif ctype == b"IDAT":
            idat.extend(chunk)
        elif ctype == b"IEND":
            break

    if width is None or height is None:
        raise ValueError(f"missing IHDR: {path}")
    if bit_depth != 8:
        raise ValueError(f"only 8-bit PNG supported: {path}")

    raw = zlib.decompress(bytes(idat))
    if color_type == 6:  # RGBA
        bpp = 4
    elif color_type == 2:  # RGB
        bpp = 3
    else:
        raise ValueError(f"unsupported PNG color type {color_type}: {path}")

    stride = width * bpp
    out = bytearray(width * height * 4)
    i = 0
    o = 0
    for _y in range(height):
        # filter byte — assume filter 0 (None) for approved baselines / stubs
        filt = raw[i]
        i += 1
        if filt != 0:
            raise ValueError(
                f"PNG filter {filt} not supported in stub harness (use filter-None PNG): {path}"
            )
        row = raw[i : i + stride]
        i += stride
        if bpp == 4:
            out[o : o + stride] = row
            o += stride
        else:
            for px in range(0, stride, 3):
                out[o : o + 3] = row[px : px + 3]
                out[o + 3] = 255
                o += 4

    return width, height, bytes(out)


def write_stub_png(path: PathLike, width: int, height: int, rgba: bytes) -> Path:
    """Write an uncompressed-filter PNG (RGBA) for scaffolding / CI stubs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(rgba) != width * height * 4:
        raise ValueError("rgba length must be width*height*4")

    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter None
        raw.extend(rgba[y * stride : (y + 1) * stride])

    compressed = zlib.compress(bytes(raw), 9)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(
        b"IEND", b""
    )
    path.write_bytes(png)
    return path


def solid_rgba(width: int, height: int, color: Tuple[int, int, int, int]) -> bytes:
    r, g, b, a = color
    return bytes([r, g, b, a]) * (width * height)


def pixel_diff_fraction(
    a: bytes,
    b: bytes,
    *,
    width: int,
    height: int,
    per_channel_tol: int = 1,
) -> float:
    """Fraction of pixels that differ (any channel beyond tol)."""
    n = width * height
    if len(a) != n * 4 or len(b) != n * 4:
        raise ValueError("buffer size mismatch")
    changed = 0
    for i in range(0, n * 4, 4):
        if (
            abs(a[i] - b[i]) > per_channel_tol
            or abs(a[i + 1] - b[i + 1]) > per_channel_tol
            or abs(a[i + 2] - b[i + 2]) > per_channel_tol
            or abs(a[i + 3] - b[i + 3]) > per_channel_tol
        ):
            changed += 1
    return changed / float(n)


def compare_rgba_buffers(
    actual: bytes,
    expected: bytes,
    *,
    width: int,
    height: int,
    threshold: float = PIXEL_DIFF_THRESHOLD,
    per_channel_tol: int = 1,
) -> float:
    """Return diff fraction; raise GoldenCompareError if above threshold."""
    frac = pixel_diff_fraction(
        actual, expected, width=width, height=height, per_channel_tol=per_channel_tol
    )
    if frac > threshold:
        raise GoldenCompareError(
            f"pixel diff {frac:.4%} exceeds threshold {threshold:.2%}",
            fraction=frac,
            threshold=threshold,
        )
    return frac


def compare_png_files(
    actual_path: PathLike,
    expected_path: PathLike,
    *,
    threshold: float = PIXEL_DIFF_THRESHOLD,
    per_channel_tol: int = 1,
) -> float:
    """Compare two PNGs on disk. Returns diff fraction or raises."""
    aw, ah, a = _read_png_rgba(Path(actual_path))
    ew, eh, e = _read_png_rgba(Path(expected_path))
    if (aw, ah) != (ew, eh):
        raise GoldenCompareError(
            f"size mismatch actual={aw}x{ah} expected={ew}x{eh}",
            fraction=1.0,
            threshold=threshold,
        )
    return compare_rgba_buffers(
        a, e, width=aw, height=ah, threshold=threshold, per_channel_tol=per_channel_tol
    )


def blender_available() -> bool:
    """True when running inside Blender's Python (bpy importable)."""
    try:
        import bpy  # noqa: F401

        return True
    except ImportError:
        return False


def render_or_stub(
    *,
    building_id: str,
    camera_name: str,
    out_path: PathLike,
    stub_color: Tuple[int, int, int, int] = (128, 128, 140, 255),
    stub_size: Tuple[int, int] = (64, 64),
) -> Path:
    """Render from Blender when available; otherwise write a stub PNG.

    Real camera renders land when the add-on / WP-5 demo buildings exist.
    """
    out_path = Path(out_path)
    if blender_available():
        # Placeholder hook — WP-7/WP-5 will wire real viewport/camera render.
        # For now still emit a stub so CI paths stay stable.
        pass
    w, h = stub_size
    return write_stub_png(out_path, w, h, solid_rgba(w, h, stub_color))
