from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import yaml


InputsMode = Literal["directory", "combined"]


@dataclass(frozen=True)
class Manifest:
    family_name: str
    style_name: str
    units_per_em: int
    mode: InputsMode
    svg_dir: Path | None
    combined_svg: Path | None
    monospace_enabled: bool
    monospace_width: int
    glyphs: list[dict[str, Any]]  # reserved: explicit overrides later


def load_manifest(path: Path) -> Manifest:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    glyphs_dir = path.parent

    family_name = str(data.get("family_name", "Untitled Font"))
    style_name = str(data.get("style_name", "Regular"))
    units_per_em = int(data.get("units_per_em", 1000))

    mode = str(data.get("mode", "directory"))
    if mode not in ("directory", "combined"):
        raise ValueError("manifest.mode must be 'directory' or 'combined'")

    inputs = data.get("inputs", {}) or {}
    dir_cfg = inputs.get("directory", {}) or {}
    comb_cfg = inputs.get("combined", {}) or {}

    svg_dir = (glyphs_dir / str(dir_cfg.get("svg_dir", "svg"))) if mode == "directory" else None
    combined_svg = (glyphs_dir / str(comb_cfg.get("svg_file", "combined/font.svg"))) if mode == "combined" else None

    mono = data.get("monospace", {}) or {}
    monospace_enabled = bool(mono.get("enabled", True))
    monospace_width = int(mono.get("advance_width", 600))

    glyphs = list(data.get("glyphs") or [])

    return Manifest(
        family_name=family_name,
        style_name=style_name,
        units_per_em=units_per_em,
        mode=cast(InputsMode, mode),
        svg_dir=svg_dir,
        combined_svg=combined_svg,
        monospace_enabled=monospace_enabled,
        monospace_width=monospace_width,
        glyphs=glyphs,
    )
