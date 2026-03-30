from __future__ import annotations

import argparse
from importlib.resources import files as _pkg_files
from pathlib import Path

from .build import build

_BUNDLED_MAPPING = _pkg_files("fontconvert").joinpath("ASCII_MAPPING.tsv")


def main() -> None:
    p = argparse.ArgumentParser(prog="fontconvert")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build font from SVG inputs via UFO pipeline")
    b.add_argument("--manifest", type=Path, default=Path("glyphs/manifest.yaml"))
    b.add_argument("--mapping", type=Path, default=None,
                   help="Path to glyph-to-codepoint TSV mapping file "
                        "(default: bundled ASCII_MAPPING.tsv)")
    b.add_argument("--out-dir", type=Path, default=Path("dist"))
    b.add_argument("--ttf", action="store_true", help="Build TTF (default)")
    b.add_argument("--otf", action="store_true", help="Also build OTF")

    args = p.parse_args()

    if args.cmd == "build":
        build_ttf = args.ttf or not args.otf
        build_otf = args.otf
        mapping = args.mapping if args.mapping is not None else _BUNDLED_MAPPING
        outs = build(
            manifest_path=args.manifest,
            mapping_path=mapping,
            out_dir=args.out_dir,
            build_ttf=build_ttf,
            build_otf=build_otf,
        )
        for o in outs:
            print(o)
