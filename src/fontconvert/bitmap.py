"""bitmap.py – Build a monospace TTF from individual PNG glyph images.

This module ports the approach from benob/png_font_to_ttf (draw each
foreground pixel as a filled square contour) into the existing ufoLib2 +
fontmake pipeline used by the rest of fontconvert.

Key differences from the original script:
- Works with **individual PNG files** (one per glyph) rather than a single
  sprite sheet.
- Uses ufoLib2 + fontmake instead of fontforge.
- Reuses the manifest for font metadata (family name, style, UPM, etc.).
- Enforces monospace: advance width is computed from the image dimensions and
  applied identically to every glyph.
- When glyph images have differing pixel dimensions, warns and crops/pads all
  images to the most common size so the build can continue.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

try:
    from importlib.resources.abc import Traversable  # Python 3.11+
except ImportError:
    from importlib.abc import Traversable  # Python 3.10

import ufoLib2

from .build import _ensure_notdef, _run, load_ascii_mapping
from .manifest import load_manifest


def _load_image_grayscale(
    img_path: Path,
    target_size: tuple[int, int] | None = None,
) -> tuple[int, int, object]:
    """Return a (width, height, pixels) tuple where pixels[col, row] is 0-255.

    Transparent pixels are composited onto a white background before
    converting to grayscale so that transparent-background PNGs work
    correctly alongside solid-background ones.

    If *target_size* is given as ``(width, height)``, the image is
    center-cropped (if larger) or center-padded with white (if smaller) so
    that the returned dimensions always equal *target_size*.
    """
    from PIL import Image

    img = Image.open(img_path).convert("RGBA")
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    bg.alpha_composite(img)
    gray = bg.convert("L")

    if target_size is not None and gray.size != target_size:
        gray = _fit_to_size(gray, target_size)

    return gray.width, gray.height, gray.load()


def _fit_to_size(img: object, target_size: tuple[int, int]) -> object:
    """Return *img* cropped or padded with white to exactly *target_size*.

    The image content is centered within the target canvas so that equal
    amounts are removed/added from each side.

    Parameters
    ----------
    img:
        A :class:`PIL.Image.Image` instance (any mode).
    target_size:
        ``(target_width, target_height)`` in pixels.
    """
    from PIL import Image

    tw, th = target_size
    sw, sh = img.size

    # Create a white canvas of the target size.
    # A fill of 255 means white for "L" (grayscale) mode, which is the only
    # mode used internally; PIL broadcasts the scalar to all channels when
    # the image has multiple channels.
    canvas = Image.new(img.mode, (tw, th), 255)

    # Offset for centering: positive → paste starts away from edge (padding);
    # negative → source starts away from its own edge (cropping).
    offset_x = (tw - sw) // 2
    offset_y = (th - sh) // 2

    # Source region to copy from *img* (handles cropping case).
    src_x = max(0, -offset_x)
    src_y = max(0, -offset_y)
    src_x2 = src_x + min(sw, tw)
    src_y2 = src_y + min(sh, th)

    # Destination position on the canvas (handles padding case).
    dst_x = max(0, offset_x)
    dst_y = max(0, offset_y)

    region = img.crop((src_x, src_y, src_x2, src_y2))
    canvas.paste(region, (dst_x, dst_y))
    return canvas


def _most_common_size(
    sizes: dict[str, tuple[int, int]],
) -> tuple[int, int]:
    """Return the most common ``(width, height)`` in *sizes*.

    Ties are broken by preferring the largest area, then the largest width.
    """
    counts: dict[tuple[int, int], int] = {}
    for sz in sizes.values():
        counts[sz] = counts.get(sz, 0) + 1
    return max(counts, key=lambda sz: (counts[sz], sz[0] * sz[1], sz[0]))


def _pixels_to_contours(
    img_path: Path,
    img_width: int,
    img_height: int,
    scale: float,
    pen,
    target_size: tuple[int, int] | None = None,
) -> None:
    """Draw one closed square contour per foreground pixel into *pen*.

    Foreground pixels are those whose grayscale value is <= 127 (dark).
    Squares are drawn counter-clockwise (outer contour direction for UFO/PS).

    The pixel at screen coordinates (col, row) — where row=0 is the top —
    maps to font coordinates:
        x0 = col  * scale
        y0 = (img_height - row - 1) * scale   (Y-flip: screen→font)
        x1 = x0 + scale
        y1 = y0 + scale

    If *target_size* is given, the image is fitted to that size before
    tracing (see :func:`_load_image_grayscale`).
    """
    width, height, pixels = _load_image_grayscale(img_path, target_size=target_size)
    for row in range(height):
        for col in range(width):
            if pixels[col, row] <= 127:  # foreground / ink pixel
                x0 = col * scale
                y0 = (height - row - 1) * scale
                x1 = x0 + scale
                y1 = y0 + scale
                # Counter-clockwise square: bottom-left → bottom-right → top-right → top-left
                pen.moveTo((x0, y0))
                pen.lineTo((x1, y0))
                pen.lineTo((x1, y1))
                pen.lineTo((x0, y1))
                pen.closePath()


def build_bitmap(
    images_dir: Path,
    mapping_path: Path | Traversable,
    manifest_path: Path,
    out_dir: Path,
) -> Path:
    """Build a monospace TTF from PNG glyph images.

    Parameters
    ----------
    images_dir:
        Directory containing one ``{glyph_name}.png`` file per glyph listed
        in *mapping_path*.
    mapping_path:
        Path (or importlib Traversable) to the glyph-to-codepoint TSV file.
    manifest_path:
        Path to the ``manifest.yaml`` file used for font metadata.
    out_dir:
        Directory where the generated TTF will be written.

    Returns
    -------
    Path
        Absolute path to the generated ``.ttf`` file.

    Raises
    ------
    FileNotFoundError
        If *images_dir* does not exist, or if any expected glyph image is
        missing.
    RuntimeError
        If fontmake does not produce a TTF file.
    """
    from PIL import Image

    mf = load_manifest(manifest_path)
    mappings = load_ascii_mapping(mapping_path)

    if not images_dir.exists():
        raise FileNotFoundError(f"Images directory not found: {images_dir}")

    # ------------------------------------------------------------------
    # Collect image paths and validate that every glyph has an image file.
    # ------------------------------------------------------------------
    glyph_images: dict[str, Path] = {}
    for m in mappings:
        img_path = images_dir / f"{m.glyph_name}.png"
        if not img_path.exists():
            raise FileNotFoundError(
                f"Missing image for glyph '{m.glyph_name}'. Expected: {img_path}"
            )
        glyph_images[m.glyph_name] = img_path

    # ------------------------------------------------------------------
    # Check image sizes; warn and auto-fit if they differ.
    # ------------------------------------------------------------------
    sizes: dict[str, tuple[int, int]] = {}
    for name, img_path in glyph_images.items():
        with Image.open(img_path) as img:
            sizes[name] = img.size  # (width, height)

    unique_sizes = set(sizes.values())
    canonical_size: tuple[int, int] | None = None
    if len(unique_sizes) > 1:
        size_groups: dict[tuple[int, int], list[str]] = {}
        for name, sz in sizes.items():
            size_groups.setdefault(sz, []).append(name)
        canonical_size = _most_common_size(sizes)
        lines = [
            f"warning: images have {len(unique_sizes)} different sizes — "
            f"all will be cropped/padded to "
            f"{canonical_size[0]}×{canonical_size[1]} px (most common size).",
        ]
        for sz, names in sorted(size_groups.items(), key=lambda item: len(item[1]), reverse=True):
            lines.append(f"  {sz[0]}×{sz[1]} px → {sorted(names)}")
        print("\n".join(lines), file=sys.stderr)
        img_width, img_height = canonical_size
    else:
        img_width, img_height = next(iter(unique_sizes))

    # Scale so that img_height == units_per_em in font coordinates.
    scale: float = mf.units_per_em / img_height
    advance_width = int(img_width * scale)

    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        safe_family = re.sub(r"[^\w\-]", "_", mf.family_name)
        safe_style = re.sub(r"[^\w\-]", "_", mf.style_name)
        ufo_path = tmp / f"{safe_family}-{safe_style}.ufo"

        ufo = ufoLib2.Font()
        ufo.info.familyName = mf.family_name
        ufo.info.styleName = mf.style_name
        ufo.info.unitsPerEm = mf.units_per_em
        ufo.info.ascender = int(mf.units_per_em * 0.8)
        ufo.info.descender = -int(mf.units_per_em * 0.2)

        for m in mappings:
            g = ufo.newGlyph(m.glyph_name)
            g.unicodes = [m.codepoint]
            g.width = advance_width  # identical for every glyph → monospace

            _pixels_to_contours(
                glyph_images[m.glyph_name],
                img_width,
                img_height,
                scale,
                g.getPen(),
                target_size=canonical_size,
            )

        _ensure_notdef(ufo, advance_width)
        ufo.save(ufo_path)

        _run(
            [
                "fontmake",
                "-u",
                str(ufo_path),
                "-o",
                "ttf",
                "--output-dir",
                str(out_dir),
            ]
        )

    produced = sorted(
        out_dir.glob("*.ttf"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not produced:
        raise RuntimeError(f"No .ttf file produced in {out_dir}")
    return produced[0]
