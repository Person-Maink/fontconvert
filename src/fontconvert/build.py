from __future__ import annotations

import csv
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

import re
import ufoLib2

from .manifest import load_manifest


@dataclass(frozen=True)
class GlyphMapping:
    glyph_name: str
    codepoint: int
    char: str


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def load_ascii_mapping(tsv_path: Path) -> list[GlyphMapping]:
    if not tsv_path.exists():
        raise FileNotFoundError(f"Missing mapping file: {tsv_path}")

    out: list[GlyphMapping] = []
    with tsv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        for row in reader:
            glyph_name = (row.get("glyph_name") or "").strip()
            codepoint_hex = (row.get("codepoint_hex") or "").strip()
            ch = row.get("char")
            if ch is None:
                ch = ""
            if glyph_name == "" or codepoint_hex == "":
                continue
            cp = int(codepoint_hex, 16)
            out.append(GlyphMapping(glyph_name=glyph_name, codepoint=cp, char=ch))
    return out


def _ensure_notdef(ufo: ufoLib2.Font, width: int | None) -> None:
    if ".notdef" not in ufo:
        g = ufo.newGlyph(".notdef")
        if width is not None:
            g.width = width


def _stage_svgs_from_directory(svg_dir: Path, staged_svgs: Path, mappings: list[GlyphMapping]) -> None:
    if not svg_dir.exists():
        raise FileNotFoundError(f"Missing svg_dir: {svg_dir}")

    for m in mappings:
        src = svg_dir / f"{m.glyph_name}.svg"
        if not src.exists():
            raise FileNotFoundError(
                f"Missing SVG for glyph '{m.glyph_name}'. Expected: {src}"
            )
        dst = staged_svgs / f"{m.glyph_name}.svg"
        shutil.copyfile(src, dst)


def _stage_svgs_from_combined(combined_svg: Path, staged_svgs: Path, mappings: list[GlyphMapping]) -> None:
    """
    Combined SVG contract:
      - Each glyph is a <g id="glyph_name"> ... </g>
      - glyph_name must match ASCII_MAPPING.tsv glyph_name entries
    """
    if not combined_svg.exists():
        raise FileNotFoundError(f"Missing combined SVG: {combined_svg}")

    tree = ET.parse(combined_svg)
    root = tree.getroot()

    wanted = {m.glyph_name for m in mappings}

    found: dict[str, ET.Element] = {}
    for el in root.iter():
        if el.tag.endswith("g"):
            gid = el.attrib.get("id")
            if gid in wanted:
                found[gid] = el

    missing = sorted(wanted - set(found.keys()))
    if missing:
        raise ValueError(
            "Combined SVG is missing groups for glyph(s): " + ", ".join(missing)
            + "\nExpected groups like: <g id=\"A\">...</g>"
        )

    for name, group in found.items():
        svg = ET.Element(
            "svg",
            attrib={"xmlns": "http://www.w3.org/2000/svg", "version": "1.1"},
        )
        svg.append(group)
        out = staged_svgs / f"{name}.svg"
        ET.ElementTree(svg).write(out, encoding="utf-8", xml_declaration=True)


def _build_one(manifest_path: Path, mapping_path: Path, out_dir: Path, out_format: str) -> Path:
    mf = load_manifest(manifest_path)
    mappings = load_ascii_mapping(mapping_path)

    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        safe_family = re.sub(r"[^\w\-]", "_", mf.family_name)
        safe_style = re.sub(r"[^\w\-]", "_", mf.style_name)
        ufo_path = tmp / f"{safe_family}-{safe_style}.ufo"

        # UFO skeleton
        ufo = ufoLib2.Font()
        ufo.info.familyName = mf.family_name
        ufo.info.styleName = mf.style_name
        ufo.info.unitsPerEm = mf.units_per_em
        ufo.info.ascender = int(mf.units_per_em * 0.8)
        ufo.info.descender = -int(mf.units_per_em * 0.2)

        mono_width = mf.monospace_width if mf.monospace_enabled else None

        for m in mappings:
            g = ufo.newGlyph(m.glyph_name)
            g.unicodes = [m.codepoint]
            if mono_width is not None:
                g.width = mono_width

        _ensure_notdef(ufo, mono_width)
        ufo.save(ufo_path)

        staged_svgs = tmp / "svgs"
        staged_svgs.mkdir(parents=True, exist_ok=True)

        if mf.mode == "directory":
            assert mf.svg_dir is not None
            _stage_svgs_from_directory(mf.svg_dir, staged_svgs, mappings)
        else:
            assert mf.combined_svg is not None
            _stage_svgs_from_combined(mf.combined_svg, staged_svgs, mappings)

        # Import outlines, then compile
        import_dir = tmp / "import"
        import_dir.mkdir(parents=True, exist_ok=True)

        _run(
            [
                "fontmake",
                "-u",
                str(ufo_path),
                "--import-outline",
                "--svg-dir",
                str(staged_svgs),
                "--output-dir",
                str(import_dir),
            ]
        )

        _run(
            [
                "fontmake",
                "-u",
                str(ufo_path),
                "-o",
                out_format,
                "--output-dir",
                str(out_dir),
            ]
        )

    produced = sorted(out_dir.glob(f"*.{out_format}"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not produced:
        raise RuntimeError(f"No .{out_format} produced in {out_dir}")
    return produced[0]


def build(manifest_path: Path, mapping_path: Path, out_dir: Path, build_ttf: bool, build_otf: bool) -> list[Path]:
    outs: list[Path] = []
    if build_ttf:
        outs.append(_build_one(manifest_path, mapping_path, out_dir, out_format="ttf"))
    if build_otf:
        outs.append(_build_one(manifest_path, mapping_path, out_dir, out_format="otf"))
    return outs
