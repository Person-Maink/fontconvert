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
- Validates that all glyph images share the same pixel dimensions before
  generating any output.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

try:
    from importlib.resources.abc import Traversable  # Python 3.11+
except ImportError:
    from importlib.abc import Traversable  # Python 3.10

import ufoLib2

from .build import _ensure_notdef, _run, load_ascii_mapping
from .manifest import load_manifest


def _load_image_grayscale(img_path: Path) -> tuple[int, int, object]:
    """Return a (width, height, pixels) tuple where pixels[col, row] is 0-255.

    Transparent pixels are composited onto a white background before
    converting to grayscale so that transparent-background PNGs work
    correctly alongside solid-background ones.
    """
    from PIL import Image

    img = Image.open(img_path).convert("RGBA")
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    bg.alpha_composite(img)
    gray = bg.convert("L")
    return gray.width, gray.height, gray.load()


def _pixels_to_contours(
    img_path: Path,
    img_width: int,
    img_height: int,
    scale: float,
    pen,
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
    """
    width, height, pixels = _load_image_grayscale(img_path)
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
    ValueError
        If the glyph images are not all the same size.
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
    # Validate that all images share the same pixel dimensions.
    # ------------------------------------------------------------------
    sizes: dict[str, tuple[int, int]] = {}
    for name, img_path in glyph_images.items():
        with Image.open(img_path) as img:
            sizes[name] = img.size  # (width, height)

    unique_sizes = set(sizes.values())
    if len(unique_sizes) > 1:
        size_groups: dict[tuple[int, int], list[str]] = {}
        for name, sz in sizes.items():
            size_groups.setdefault(sz, []).append(name)
        details = "; ".join(
            f"{sz[0]}×{sz[1]} → {sorted(names)}"
            for sz, names in sorted(size_groups.items(), key=lambda item: len(item[1]), reverse=True)
        )
        raise ValueError(
            "--force requires all letter images to be the same size, "
            f"but found {len(unique_sizes)} different sizes.\n{details}"
        )

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
