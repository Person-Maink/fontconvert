from __future__ import annotations

import argparse
import sys
from importlib.resources import files as _pkg_files
from pathlib import Path

from .build import build
from .bitmap import build_bitmap

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
    b.add_argument(
        "--force",
        action="store_true",
        help=(
            "Build a bitmap-based monospace TTF from PNG letter images "
            "(one {glyph_name}.png per glyph).  All images must be the same "
            "size; the build fails with an error otherwise.  "
            "--otf is ignored when --force is used."
        ),
    )
    b.add_argument(
        "--images-dir",
        type=Path,
        default=Path("glyphs/png"),
        metavar="PATH",
        help=(
            "Directory containing PNG glyph images used with --force "
            "(default: glyphs/png)"
        ),
    )

    args = p.parse_args()

    if args.cmd == "build":
        mapping = args.mapping if args.mapping is not None else _BUNDLED_MAPPING

        if args.force:
            try:
                out = build_bitmap(
                    images_dir=args.images_dir,
                    mapping_path=mapping,
                    manifest_path=args.manifest,
                    out_dir=args.out_dir,
                )
            except (FileNotFoundError, ValueError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                sys.exit(1)
            print(out)
        else:
            build_ttf = args.ttf or not args.otf
            build_otf = args.otf
            outs = build(
                manifest_path=args.manifest,
                mapping_path=mapping,
                out_dir=args.out_dir,
                build_ttf=build_ttf,
                build_otf=build_otf,
            )
            for o in outs:
                print(o)
