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
            "(one {glyph_name}.png per glyph).  If images have different "
            "sizes, a warning is printed and all images are cropped/padded "
            "to the most common size so the build can continue.  "
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
    b.add_argument(
        "--downscale",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Downscale glyph images by integer factor N before tracing "
            "(e.g. --downscale 2 halves both dimensions).  Only used with "
            "--force.  Default: 1 (no downscaling)."
        ),
    )

    args = p.parse_args()

    if args.cmd == "build":
        mapping = args.mapping if args.mapping is not None else _BUNDLED_MAPPING

        if args.force:
            if args.downscale <= 0:
                print("error: --downscale must be a positive integer (≥ 1)", file=sys.stderr)
                sys.exit(1)
            try:
                out = build_bitmap(
                    images_dir=args.images_dir,
                    mapping_path=mapping,
                    manifest_path=args.manifest,
                    out_dir=args.out_dir,
                    downscale=args.downscale,
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
